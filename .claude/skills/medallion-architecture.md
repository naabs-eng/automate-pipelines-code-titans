---
name: Medallion Architecture
description: Use when designing or modifying bronze/silver/gold layer logic, deciding where a transformation belongs, adding new tables, or explaining layer contracts in this pipeline.
---

# Medallion Architecture — ClaudeDataPipeline

## What Medallion Is

Three-layer data lakehouse pattern: Raw → Validated → Aggregated. Each layer adds quality and reduces cardinality. Layers are written as Parquet and are fully re-runnable (overwrite mode = idempotent).

---

## Bronze Layer — "Raw Zone"

**Purpose**: Exact replica of source data. Historian, not processor.

**Rules (enforce strictly)**:
- Zero renaming. Column names match SQL Server source exactly (PascalCase).
- Zero type coercion. Spark infers types from JDBC; do not cast in Bronze.
- Zero filtering. Nulls, bad values, duplicates — all land in Bronze as-is.
- Write mode: `overwrite`. Full load every run.

**In this project**:
- Source: `dbo.Products`, `dbo.Customers`, `dbo.Orders`, `dbo.OrderItems`
- Output: `data/bronze/products/`, `data/bronze/customers/`, `data/bronze/orders/`, `data/bronze/order_items/`
- Class: `BronzeLayer` in `src/bronze/ingestion.py`

**When to add to Bronze**: Only when a new source table is added to `config.yaml tables.source`. Bronze is driven by config, not hardcoded.

---

## Silver Layer — "Validated Zone"

**Purpose**: Clean, typed, snake_case, row-level data. The single source of truth for all downstream work.

**Rules (enforce strictly)**:
- One `transform_<entity>()` method per domain table. No shared transform methods.
- Always rename PascalCase → snake_case via `.alias()`.
- Always cast to explicit types: `int`, `string`, `float`, `timestamp`. Never leave column type as `object` or inferred.
- Primary key null filter is the Silver contract: `df.filter(F.col("pk_column").isNotNull())`. Always last operation before save.
- Row-level derived columns live here: `line_total = quantity * unit_price`.
- No aggregations. No cross-table joins. Row-level only.

**In this project**:
- Output: `data/silver/products/`, `data/silver/customers/`, `data/silver/orders/`, `data/silver/order_items/`
- Class: `SilverLayer` in `src/silver/transformations.py`

**The Silver Contract**: "If a row exists in Silver, its primary key is valid." Every downstream system (Gold, tests, reports) can assume this.

**When to add to Silver**: When Bronze has a new table. One new `transform_<entity>()` method.

---

## Gold Layer — "Business Zone"

**Purpose**: Aggregated, business-ready tables. What analysts, BI tools, and dashboards consume.

**Rules (enforce strictly)**:
- Every Gold table is either a `groupBy().agg()` or a `join()` of Silver tables.
- Always `left` join with `order_items` as the left/fact table. Never `inner` — inner joins silently drop unmatched order items.
- Dimension tables (`products`, `customers`, `orders`) join onto the fact table.
- GroupBy key columns must not be null before aggregation: `.na.drop(subset=["key_col"])`.
- Monetary columns get `F.round(col, 2)` before save.
- No row-level transformation in Gold — that belongs in Silver.

**In this project**:
- `sales_summary`: flat denorm view (order_items LEFT JOIN products LEFT JOIN orders)
- `daily_sales_by_category`: groupBy(order_date, category) → total_quantity, total_sales
- `product_performance`: groupBy(product_id, product_name, category) → total_quantity_sold, total_revenue, avg_price
- Class: `GoldLayer` in `src/gold/aggregations.py`

**When to add a new Gold table**: When a new business question cannot be answered from existing Gold tables. Adding a new Silver table alone does NOT require a new Gold table — it only requires updating existing Gold joins if that table is a new dimension.

---

## Data Flow Between Layers

```
SQL Server (dbo.*)
    ↓  [JDBC read, Parquet write, overwrite mode]
data/bronze/<table>/
    ↓  [Parquet read → type cast + rename + null filter → Parquet write]
data/silver/<table>/
    ↓  [Parquet read → joins + groupBy + agg → Parquet write]
data/gold/<table>/
```

**main.py orchestrates** the full flow: creates SparkSession, constructs all three layer classes, calls methods in order: bronze.ingest_all_tables() → silver.transform_*() + silver.save_*() → gold.create_*() + gold.save_*().

---

## Adding a New Domain Table (checklist)

1. Create SQL DDL in `sql/create_schema.sql` matching `dbo.PascalCase` convention
2. Add insert statements to `sql/insert_sample_data.sql`
3. Add entry to `config.yaml tables.source`: `{name: "dbo.NewTable", bronze_table: "new_table"}`
4. `src/bronze/ingestion.py`: no code change needed — `ingest_all_tables()` reads from config
5. `src/silver/transformations.py`: add `transform_new_table(self, bronze_df)` method
6. `src/gold/aggregations.py`: add `create_<metric>(self, ...)` method if this table is a new fact or needed dimension
7. `src/main.py`: add the bronze read → silver transform + save → gold create + save wiring
8. `tests/`: add test methods to the relevant test files

---

## Idempotency

All three layers use `write.mode("overwrite")`. The pipeline is safe to re-run any number of times and will produce identical output for identical input. No deduplication logic is needed at the output level.
