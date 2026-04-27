---
description: Generate column-level data lineage from SQL Server source through all three medallion layers
allowed-tools: Read, Bash
---

## Context

Source definitions (read all to trace lineage):
@sql/create_schema.sql
@src/bronze/ingestion.py
@src/silver/transformations.py
@src/gold/aggregations.py
@config.yaml

## Task

Generate a complete column-level data lineage report showing how every source column flows from SQL Server through Bronze, Silver, and Gold layers.

### Lineage Trace Method

For each domain entity (Products, Customers, Orders, OrderItems):

1. **Source** (from `sql/create_schema.sql`): SQL Server column name, SQL type
2. **Bronze** (from `ingestion.py` and JDBC behavior): column name (unchanged, PascalCase), inferred Spark type
3. **Silver** (from `transformations.py`): renamed snake_case column, explicit cast type, derived columns
4. **Gold** (from `aggregations.py`): aggregated name, aggregation function, or "dropped" if not used

### Transformation Taxonomy

Label each hop with the transformation applied:
- `pass-through` — same column name and type, no change
- `rename` — name changed (PascalCase → snake_case)
- `cast` — type changed (SQL DECIMAL → Spark float)
- `rename+cast` — both name and type changed
- `derived` — new column computed from others (e.g. `line_total`)
- `aggregated` — column becomes SUM/AVG/COUNT in Gold
- `dropped` — column present in upstream layer but not carried forward

### Output Format

Produce a Markdown table for each entity:

**OrderItems Lineage**:
| SQL Server Column | SQL Type | Bronze Column | Spark Type | Silver Column | Silver Type | Transformation | Gold Column | Gold Aggregation |
|---|---|---|---|---|---|---|---|---|
| OrderItemID | INT | OrderItemID | integer | order_item_id | int | rename+cast | — | dropped (PK only) |
| OrderID | INT | OrderID | integer | order_id | int | rename+cast | order_id | pass-through (join key) |
| ProductID | INT | ProductID | integer | product_id | int | rename+cast | product_id | pass-through (join key) |
| Quantity | INT | Quantity | integer | quantity | int | rename+cast | total_quantity_sold | SUM |
| UnitPrice | DECIMAL(10,2) | UnitPrice | decimal | unit_price | float | rename+cast | avg_price | AVG |
| *(derived)* | — | — | — | line_total | float | derived (qty×price) | total_revenue | SUM |

### Summary Section

After all entity tables, add:

1. **Columns dropped between layers** — list any source columns that don't appear in Gold. Explain whether this is intentional.
2. **Columns added (derived)** — `line_total` and any other derived columns, with the formula
3. **Type changes** — summary of SQL Server type → Spark type mappings used in this pipeline
4. **PK columns in Gold** — note that PK columns (product_id, etc.) appear in Gold as groupBy keys or join keys, not as standalone rows

### Save Report

Write the report to `data/lineage_report.md` (create `data/` if needed, but don't gitignore this file — it's a documentation artifact, not pipeline output).
