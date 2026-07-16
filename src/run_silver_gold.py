import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (DateType, DecimalType, DoubleType, FloatType,
                               IntegerType, LongType, StringType, TimestampType)

load_dotenv()

from config.config_manager import ConfigManager


# ── Naming helpers ─────────────────────────────────────────────────────────────

def _silver_name(bronze_name):
    """suppliers_bronze  →  suppliers_silver"""
    if bronze_name.endswith("_bronze"):
        return bronze_name[:-7] + "_silver"
    return bronze_name + "_silver"


def _base_name(table_name):
    """suppliers_bronze or suppliers_silver  →  suppliers"""
    if table_name.endswith("_bronze"):
        return table_name[:-7]
    if table_name.endswith("_silver"):
        return table_name[:-7]
    return table_name


# ── Schema helpers ─────────────────────────────────────────────────────────────

def to_snake_case(name):
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def infer_primary_key(fields):
    for f in fields:
        snake = to_snake_case(f.name)
        if snake.endswith("_id") and not any(x in snake for x in ["foreign", "ref"]):
            return snake
    for f in fields:
        if f.name.lower() == "id":
            return "id"
    return to_snake_case(fields[0].name)


# ── Layer runners ──────────────────────────────────────────────────────────────

def run_silver(spark, bronze_table_name, bronze_path, silver_path):
    silver_table_name = _silver_name(bronze_table_name)
    print(f"[Silver] Processing {bronze_table_name}...")

    df = spark.read.parquet(str(Path(bronze_path) / bronze_table_name))
    fields = df.schema.fields

    pk = infer_primary_key(fields)
    print(f"[Silver] Inferred primary key: {pk}")

    select_cols = []
    for f in fields:
        snake = to_snake_case(f.name)
        dtype = f.dataType
        if isinstance(dtype, (IntegerType, LongType)):
            select_cols.append(F.col(f.name).cast("int").alias(snake))
        elif isinstance(dtype, (FloatType, DoubleType, DecimalType)):
            select_cols.append(F.col(f.name).cast("float").alias(snake))
        elif isinstance(dtype, TimestampType):
            select_cols.append(F.col(f.name).cast("timestamp").alias(snake))
        elif isinstance(dtype, DateType):
            select_cols.append(F.col(f.name).cast("date").alias(snake))
        else:
            select_cols.append(F.col(f.name).cast("string").alias(snake))

    df = df.select(*select_cols).filter(F.col(pk).isNotNull())
    out = Path(silver_path) / silver_table_name
    df.coalesce(1).write.mode("overwrite").parquet(str(out))
    row_count = df.count()
    print(f"[Silver] SUCCESS: {silver_table_name} -> data/silver/{silver_table_name} ({row_count} rows)")
    return df, pk


def run_gold(spark, table_name, silver_path, gold_path, silver_df):
    """table_name may be a _bronze or _silver name; base is derived automatically."""
    base = _base_name(table_name)
    print(f"[Gold] Processing {table_name}...")

    fields = silver_df.schema.fields
    pk_snake = infer_primary_key(fields)

    dim_cols = [
        f.name for f in fields
        if isinstance(f.dataType, StringType)
        and f.name != pk_snake
        and not f.name.endswith("_id")
        and not f.name.endswith("_email")
        and not f.name.endswith("_name")
    ]

    measure_cols = [
        f.name for f in fields
        if isinstance(f.dataType, (IntegerType, LongType, FloatType, DoubleType, DecimalType))
        and not f.name.endswith("_id")
        and f.name != pk_snake
    ]

    date_cols = [
        f.name for f in fields
        if isinstance(f.dataType, (DateType, TimestampType))
    ]

    group_cols = dim_cols[:2] + date_cols[:1] if dim_cols or date_cols else None

    if not group_cols and not measure_cols:
        print(f"[Gold] Skipping {base} — no suitable dimension/measure columns for aggregation")
        return
    if not group_cols:
        print(f"[Gold] Skipping {base} — no dimension columns to group by")
        return

    agg_exprs = [F.count("*").alias("record_count")]
    for col in measure_cols:
        agg_exprs.append(F.sum(col).alias(f"total_{col}"))
        agg_exprs.append(F.avg(col).alias(f"avg_{col}"))

    gold_table = f"{base}_summary"
    df_gold = (
        silver_df
        .groupBy(*group_cols)
        .agg(*agg_exprs)
        .orderBy(F.col("record_count").desc())
    )

    out = Path(gold_path) / gold_table
    df_gold.coalesce(1).write.mode("overwrite").parquet(str(out))
    row_count = df_gold.count()
    print(f"[Gold] SUCCESS: {gold_table} -> data/gold/{gold_table} ({row_count} rows)")


# ── Cross-table joined Gold execution ──────────────────────────────────────────

def run_joined_gold(plan, config, spark):
    """
    Execute a cross-table LEFT JOIN + aggregation from a plan dict produced by
    analyse_gold.py when cross_table_hint.join_confirmed is True.
    """
    hint = plan.get("cross_table_hint", {})
    if not hint or not hint.get("join_confirmed"):
        return False

    tables = hint.get("tables", [])
    join_key = hint.get("suggested_join_key")
    dest = hint.get("destination")

    if len(tables) < 2 or not join_key or not dest:
        print("ERROR: Cross-table plan incomplete — missing tables, join key, or destination name")
        return False

    # Resolve join key from requirements joins spec if more specific
    for tp in plan.get("tables", []):
        for j in tp.get("joins", []):
            if j.get("on"):
                join_key = j["on"]
                break

    silver_path = config.get("paths.silver", "./data/silver")
    gold_path = config.get("paths.gold", "./data/gold")

    print(f"[Gold] Cross-table join: `{'` + `'.join(tables)}` on `{join_key}` → `{dest}`")

    fact_table = tables[0]
    dim_table = tables[1]

    fact_df = spark.read.parquet(str(Path(silver_path) / fact_table))
    dim_df = spark.read.parquet(str(Path(silver_path) / dim_table))

    # Avoid column name collisions on join key
    joined = fact_df.join(dim_df.drop(*(c for c in dim_df.columns if c != join_key and c in fact_df.columns)), join_key, "left")

    # Collect group-by and aggregation specs from all table plans
    group_cols = []
    seen_gb = set()
    agg_exprs = []
    seen_aliases = set()
    for tp in plan.get("tables", []):
        for col in tp.get("group_by", []):
            if col not in seen_gb and col in joined.columns:
                group_cols.append(col)
                seen_gb.add(col)
        for agg in tp.get("aggregations", []):
            alias = agg.get("alias", "")
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            func = agg.get("func", "COUNT").upper()
            col = agg.get("col", "*")
            if func == "COUNT":
                agg_exprs.append(F.count("*").alias(alias))
            elif func == "SUM" and col in joined.columns:
                agg_exprs.append(F.sum(col).alias(alias))
            elif func == "AVG" and col in joined.columns:
                agg_exprs.append(F.avg(col).alias(alias))
            elif func == "MAX" and col in joined.columns:
                agg_exprs.append(F.max(col).alias(alias))
            elif func == "MIN" and col in joined.columns:
                agg_exprs.append(F.min(col).alias(alias))

    if not group_cols:
        print(f"ERROR: No group-by columns resolved for joined Gold table `{dest}`")
        return False
    if not agg_exprs:
        agg_exprs = [F.count("*").alias("record_count")]

    result = joined.groupBy(*group_cols).agg(*agg_exprs)
    out_path = Path(gold_path) / dest
    result.coalesce(1).write.mode("overwrite").parquet(str(out_path))
    row_count = result.count()
    print(f"[Gold] SUCCESS: {dest} -> data/gold/{dest} ({row_count} rows)")
    return True


# ── Agent plan executor ────────────────────────────────────────────────────────

def run_agent_plan(plan, config, spark):
    """Execute a Gold plan produced by the Gold Agent chatbot (src/gold_agent.py)."""
    silver_path = config.get("paths.silver", "./data/silver")
    gold_path = config.get("paths.gold", "./data/gold")

    source_tables = plan["source_tables"]
    joins = plan.get("joins", [])
    group_by = plan["group_by"]
    aggregations = plan["aggregations"]
    derived_columns = plan.get("derived_columns", [])
    filters = plan.get("filters", [])
    destination = plan["destination"]

    print(f"[Gold] Agent plan: {destination} from {source_tables}")

    # Use the fact table from the join spec if present; fall back to source_tables[0]
    fact_table = joins[0].get("fact", source_tables[0]) if joins else source_tables[0]
    df = spark.read.parquet(str(Path(silver_path) / fact_table))
    print(f"[Gold] Fact table: {fact_table}")

    for j in joins:
        dim_df = spark.read.parquet(str(Path(silver_path) / j["dim"]))
        on_raw = j["on"].strip()

        if "=" in on_raw:
            # Agent returned full expression e.g. "table.col = table.col" — extract bare names
            left_side, right_side = [s.strip() for s in on_raw.split("=", 1)]
            left_col  = left_side.split(".")[-1].strip()
            right_col = right_side.split(".")[-1].strip()
            # Drop overlapping columns from dim EXCEPT the join key (needed for join condition)
            overlap = [c for c in dim_df.columns if c in df.columns and c != right_col]
            if overlap:
                dim_df = dim_df.drop(*overlap)
            # Build condition using specific column objects (avoids ambiguity)
            join_cond = df[left_col] == dim_df[right_col]
            df = df.join(dim_df, join_cond, "left")
            # Drop the dim's copy of the key — use column object so Spark picks the right one
            df = df.drop(dim_df[right_col])
        else:
            # Simple column name — PySpark USING syntax deduplicates automatically
            overlap = [c for c in dim_df.columns if c != on_raw and c in df.columns]
            if overlap:
                dim_df = dim_df.drop(*overlap)
            df = df.join(dim_df, on_raw, "left")

    for f_expr in filters:
        df = df.filter(F.expr(f_expr))

    _agg_fn = {"SUM": F.sum, "AVG": F.avg, "MAX": F.max, "MIN": F.min}
    agg_exprs = []
    for agg in aggregations:
        func = agg["func"].upper()
        col = agg["col"]
        alias = agg["alias"]
        if func == "COUNT":
            agg_exprs.append((F.count("*") if col == "*" else F.count(col)).alias(alias))
        elif func in _agg_fn:
            if "(" in col:
                # col is an expression like datediff(end_date, current_date())
                agg_exprs.append(F.expr(f"{func}({col})").alias(alias))
            elif col not in df.columns:
                print(f"[Gold] Warning: skipping {func}({col}) — column not found after join")
                continue
            else:
                agg_exprs.append(_agg_fn[func](col).alias(alias))

    if not agg_exprs:
        agg_exprs = [F.count("*").alias("record_count")]

    result = df.groupBy(*group_by).agg(*agg_exprs)

    for alias_spec in plan.get("column_aliases", []):
        from_col = alias_spec.get("from", "")
        to_col = alias_spec.get("to", "")
        if from_col and to_col and from_col != to_col and from_col in result.columns:
            result = result.withColumnRenamed(from_col, to_col)

    for dc in derived_columns:
        result = result.withColumn(dc["column"], F.expr(dc["expression"]))

    out_path = Path(gold_path) / destination
    result.coalesce(1).write.mode("overwrite").parquet(str(out_path))
    row_count = result.count()
    print(f"[Gold] SUCCESS: {destination} -> data/gold/{destination} ({row_count} rows)")
    return True


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run Silver and/or Gold layers")
    parser.add_argument(
        "--tables", default=None,
        help="Comma-separated bronze table names (e.g. suppliers_bronze,order_items_bronze)",
    )
    parser.add_argument(
        "--silver-tables", default=None,
        help="Comma-separated silver table names for Gold-only runs from Gold Builder "
             "(e.g. suppliers_silver,order_items_silver)",
    )
    parser.add_argument(
        "--layer", default="all", choices=["all", "silver", "gold"],
        help="Which layer(s) to run (default: all)",
    )
    parser.add_argument(
        "--plan-file", default=None,
        help="Path to a Gold plan JSON file (from analyse_gold.py) — enables cross-table join execution",
    )
    parser.add_argument(
        "--agent-plan-file", default=None,
        help="Path to an agent plan JSON file (from Gold Agent chat) — direct execution",
    )
    args = parser.parse_args()

    # ── Agent plan fast-path ──────────────────────────────────────────────────
    if args.agent_plan_file:
        plan_path = Path(args.agent_plan_file)
        if not plan_path.exists():
            print(f"ERROR: Agent plan file not found: {args.agent_plan_file}")
            sys.exit(1)
        agent_plan = json.loads(plan_path.read_text())
        config = ConfigManager()
        base_dir = Path(__file__).parent.parent
        pg_driver = str(base_dir / config.get("spark.pg_driver_path"))
        spark = (
            SparkSession.builder.appName("GoldAgent")
            .master(config.get("spark.master", "local[*]"))
            .config("spark.driver.memory", config.get("spark.memory", "2g"))
            .config("spark.driver.extraClassPath", pg_driver)
            .config("spark.executor.extraClassPath", pg_driver)
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")
        try:
            ok = run_agent_plan(agent_plan, config, spark)
        finally:
            spark.stop()
        if ok:
            print("\nDone. 1 succeeded, 0 failed.")
        else:
            print("\nDone. 0 succeeded, 1 failed.")
            sys.exit(1)
        return

    # Validate argument combinations
    if not args.tables and not args.silver_tables:
        print("ERROR: Provide --tables (bronze names) or --silver-tables (silver names)")
        sys.exit(1)
    if args.silver_tables and args.layer != "gold":
        print("ERROR: --silver-tables can only be used with --layer gold")
        sys.exit(1)

    config = ConfigManager()
    base_dir = Path(__file__).parent.parent
    pg_driver = str(base_dir / config.get("spark.pg_driver_path"))

    bronze_path = config.get("paths.bronze", "./data/bronze")
    silver_path = config.get("paths.silver", "./data/silver")
    gold_path = config.get("paths.gold", "./data/gold")

    Path(silver_path).mkdir(parents=True, exist_ok=True)
    Path(gold_path).mkdir(parents=True, exist_ok=True)

    spark = (
        SparkSession.builder.appName("SilverGoldRunner")
        .master(config.get("spark.master", "local[*]"))
        .config("spark.driver.memory", config.get("spark.memory", "2g"))
        .config("spark.driver.extraClassPath", pg_driver)
        .config("spark.executor.extraClassPath", pg_driver)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    failed = []

    # ── Cross-table joined Gold (--plan-file with confirmed join) ─────────────
    if args.plan_file:
        plan_path = Path(args.plan_file)
        if not plan_path.exists():
            print(f"ERROR: Plan file not found: {args.plan_file}")
            sys.exit(1)
        plan = json.loads(plan_path.read_text())
        hint = plan.get("cross_table_hint") or {}
        if hint.get("join_confirmed"):
            ok = run_joined_gold(plan, config, spark)
            spark.stop()
            if not ok:
                sys.exit(1)
            print(f"\nDone. 1 succeeded, 0 failed.")
            return
        # No join in plan — fall through to normal execution below

    # ── Gold-only from Gold Builder (--silver-tables) ──────────────────────────
    if args.silver_tables:
        silver_tables = [t.strip() for t in args.silver_tables.split(",") if t.strip()]
        for table in silver_tables:
            try:
                silver_df = spark.read.parquet(str(Path(silver_path) / table))
                run_gold(spark, table, silver_path, gold_path, silver_df)
            except Exception as e:
                print(f"ERROR: {table} — {e}")
                failed.append(table)

    # ── Bronze→Silver→Gold from Ingest Pipeline (--tables with bronze names) ──
    else:
        tables = [t.strip().split(".")[-1] for t in args.tables.split(",") if t.strip()]
        if not tables:
            print("ERROR: No tables specified")
            sys.exit(1)

        for table in tables:
            try:
                if args.layer in ("all", "silver"):
                    silver_df, _pk = run_silver(spark, table, bronze_path, silver_path)
                else:
                    # gold-only pass: derive silver name from bronze name
                    sname = _silver_name(table)
                    silver_df = spark.read.parquet(str(Path(silver_path) / sname))

                if args.layer in ("all", "gold"):
                    run_gold(spark, table, silver_path, gold_path, silver_df)
            except Exception as e:
                print(f"ERROR: {table} — {e}")
                failed.append(table)

    spark.stop()
    total = len(args.silver_tables.split(",") if args.silver_tables else args.tables.split(","))
    print(f"\nDone. {total - len(failed)} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
