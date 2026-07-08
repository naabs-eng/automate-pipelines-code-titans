import argparse
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


def run_silver(spark, table_name, bronze_path, silver_path):
    print(f"[Silver] Processing {table_name}...")

    df = spark.read.parquet(str(Path(bronze_path) / table_name))
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
    out = Path(silver_path) / table_name
    df.coalesce(1).write.mode("overwrite").parquet(str(out))
    row_count = df.count()
    print(f"[Silver] SUCCESS: {table_name} -> data/silver/{table_name} ({row_count} rows)")
    return df, pk


def run_gold(spark, table_name, silver_path, gold_path, silver_df):
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
        print(f"[Gold] Skipping {table_name} — no suitable dimension/measure columns for aggregation")
        return

    if not group_cols:
        print(f"[Gold] Skipping {table_name} — no dimension columns to group by")
        return

    agg_exprs = [F.count("*").alias("record_count")]
    for col in measure_cols:
        agg_exprs.append(F.sum(col).alias(f"total_{col}"))
        agg_exprs.append(F.avg(col).alias(f"avg_{col}"))

    gold_table = f"{table_name}_summary"
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


def main():
    parser = argparse.ArgumentParser(description="Run Silver and Gold for specified Bronze tables")
    parser.add_argument("--tables", required=True,
                        help="Comma-separated bronze table names (e.g. suppliers,inventory)")
    args = parser.parse_args()

    tables = [t.strip().split(".")[-1] for t in args.tables.split(",") if t.strip()]
    if not tables:
        print("ERROR: No tables specified")
        sys.exit(1)

    config = ConfigManager()
    base = Path(__file__).parent.parent
    pg_driver = str(base / config.get("spark.pg_driver_path"))
    jdbc_driver = str(base / config.get("spark.jdbc_driver_path"))
    all_drivers = f"{jdbc_driver}:{pg_driver}"

    bronze_path = config.get("paths.bronze", "./data/bronze")
    silver_path = config.get("paths.silver", "./data/silver")
    gold_path = config.get("paths.gold", "./data/gold")

    Path(silver_path).mkdir(parents=True, exist_ok=True)
    Path(gold_path).mkdir(parents=True, exist_ok=True)

    spark = (
        SparkSession.builder.appName("SilverGoldRunner")
        .master(config.get("spark.master", "local[*]"))
        .config("spark.driver.memory", config.get("spark.memory", "2g"))
        .config("spark.driver.extraClassPath", all_drivers)
        .config("spark.executor.extraClassPath", all_drivers)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    failed = []
    for table in tables:
        try:
            silver_df, pk = run_silver(spark, table, bronze_path, silver_path)
            run_gold(spark, table, silver_path, gold_path, silver_df)
        except Exception as e:
            print(f"ERROR: {table} — {e}")
            failed.append(table)

    spark.stop()
    print(f"\nDone. {len(tables) - len(failed)} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
