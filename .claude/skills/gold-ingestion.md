---
name: Gold Ingestion
description: Use when designing or building Gold layer tables — covers the full analyse-validate-plan-confirm-implement cycle using business requirements (KPIs, joins, aggregations, business rules, target grain, dimensions and measures). Applies when the user provides requirements OR when auto-analysis from Silver schemas is needed.
---

# Gold Ingestion — ClaudeDataPipeline

## Purpose

Gold is the **business-facing, analytics-ready layer**. Every Gold table answers a specific business question. It is produced by joining and aggregating Silver tables — never by touching Bronze or raw sources directly.

---

## Lifecycle: Analyse → Validate → Plan → Confirm → Implement

Gold tables must NEVER be created speculatively. Follow this five-phase gate:

1. **Analyse** — understand the business requirement and map it to Silver schemas
2. **Validate** — verify every column, join key, and aggregation is traceable
3. **Plan** — produce a detailed table plan (see format below) for user review
4. **Confirm** — wait for explicit user approval; ask about any ambiguities
5. **Implement** — generate and run the PySpark code only after confirmation

### How this is wired in the Pipeline Runner UI

The UI enforces this lifecycle through four interactive steps in Phase 2:

1. **Requirements input** — optional text area with structured placeholder (KPIs, grain, dimensions, measures, joins, rules, destination table names). User fills in what they know; blank = auto-generate from Silver schema.
2. **🔍 Analyse & Generate Plan** button — runs `src/analyse_gold.py` as a subprocess (uses pyarrow, no Spark startup). Reads Silver Parquet schemas, parses requirements text, outputs a JSON plan.
3. **Plan display** — per destination table: grain, group_by, aggregations table, output schema table. Open questions (column not found, ambiguous grouping) shown as `st.error` blocks. Warnings (auto-resolved but worth checking) shown as `st.warning`. If open questions exist, the **Confirm** checkbox is hidden and the user must fix requirements + re-analyse.
4. **✅ Confirm + ▶ Run Gold** — confirm checkbox only appears when zero open questions remain. Run Gold button only appears after checkbox is ticked.

**Session state keys**: `gold_requirements` (text), `gold_plan` (dict), `gold_plan_confirmed` (bool). All three are cleared when Phase 1 re-runs.

---

## Phase 1 — Analyse Business Requirements

### When the user provides requirements

Extract and capture all of the following:

| Requirement type | Questions to answer |
|---|---|
| **KPIs** | What metric(s) are being measured? (revenue, volume, margin, rate) |
| **Target grain** | One row = what? (one order, one product-day, one customer-month) |
| **Dimensions** | What can the metric be sliced by? (category, region, date, customer segment) |
| **Measures** | What is summed / averaged / counted? (quantity, revenue, cost, duration) |
| **Joins** | Which Silver tables need to be joined? What are the join keys and types? |
| **Aggregations** | `SUM`, `AVG`, `COUNT`, `COUNT DISTINCT`, `MAX`, `MIN`, window functions |
| **Business rules** | Filters (active orders only), derived metrics (margin = revenue - cost), exclusions |
| **Output table name** | What is the destination Gold table name? |

### When the user provides no requirements

Read every Silver table's schema and infer:

```python
# Read Silver schemas
for table in silver_tables:
    df = spark.read.parquet(f"data/silver/{table}")
    # Identify:
    # - String columns → dimension candidates
    # - Numeric columns → measure candidates
    # - Date/timestamp columns → time dimension candidates
    # - Columns ending in _id → join key candidates
```

Propose 2–3 Gold table ideas based on what the data can answer. Present them to the user and ask which to build.

---

## Phase 2 — Validate Mappings

Before writing a plan, verify:

1. Every source column referenced in the plan exists in the Silver schema
2. Every join key has matching types on both sides (`int ↔ int`, not `int ↔ string`)
3. Every aggregation makes business sense (don't `SUM` a percentage column)
4. The target grain is achievable with the available keys
5. No Silver column needed is nullable at a rate that would silently distort aggregations

If any of these cannot be confirmed, **stop and ask the user** before proceeding.

---

## Phase 3 — Plan (required before any code)

Present a structured plan in this exact format:

```
## Gold Table Plan: <destination_table_name>

**Business question answered:** <one sentence>
**Target grain:** one row = <description>
**Output path:** data/gold/<destination_table_name>/

### Source Tables
| Silver Table | Role | Join Key |
|---|---|---|
| order_items  | fact | order_item_id |
| products     | dimension | product_id |
| orders       | dimension | order_id |

### Join Strategy
order_items LEFT JOIN products ON order_items.product_id = products.product_id
order_items LEFT JOIN orders   ON order_items.order_id   = orders.order_id

(Left join from fact table — never inner join, preserves all order_items)

### Output Schema
| Column | Type | Source / Logic |
|---|---|---|
| order_date    | date    | orders.order_date |
| category      | string  | products.category |
| total_quantity | long   | SUM(order_items.quantity) |
| total_revenue  | double | SUM(order_items.line_total) |
| avg_unit_price | double | AVG(order_items.unit_price) |
| order_count    | long   | COUNT(DISTINCT order_items.order_id) |

### Business Rules Applied
- Exclude orders with order_date IS NULL
- Only include order_items where quantity > 0

### Aggregation
groupBy(order_date, category)
→ SUM(quantity), SUM(line_total), AVG(unit_price), COUNT DISTINCT(order_id)
→ ORDER BY order_date DESC, total_revenue DESC
```

---

## Phase 4 — Confirm

After presenting the plan, ask:

> "Does this plan match your expectation? Reply **yes** to implement, or describe what needs to change."

Do NOT proceed to code until the user confirms. If the user replies with corrections, update the plan and present it again. Repeat until confirmed.

If during analysis you cannot map a destination column to any Silver source:

> "I can't find a Silver column to populate `<column_name>`. Could you clarify the source or the calculation logic?"

---

## Phase 5 — Implement

Only after explicit confirmation, generate PySpark code following these patterns:

### Standard Gold aggregation

```python
from pyspark.sql import functions as F

fact = spark.read.parquet("data/silver/order_items")
products = spark.read.parquet("data/silver/products")
orders = spark.read.parquet("data/silver/orders")

df = (
    fact
    .join(products, on="product_id", how="left")
    .join(orders,   on="order_id",   how="left")
    .filter(F.col("order_date").isNotNull())
    .filter(F.col("quantity") > 0)
    .groupBy("order_date", "category")
    .agg(
        F.sum("quantity").alias("total_quantity"),
        F.sum("line_total").alias("total_revenue"),
        F.avg("unit_price").alias("avg_unit_price"),
        F.countDistinct("order_id").alias("order_count"),
    )
    .orderBy(F.col("order_date").desc(), F.col("total_revenue").desc())
)

df.coalesce(1).write.mode("overwrite").parquet("data/gold/daily_sales_by_category")
print(f"[Gold] SUCCESS: daily_sales_by_category ({df.count()} rows)")
```

### Window function (e.g. running totals, rankings)

```python
from pyspark.sql import Window

w = Window.partitionBy("category").orderBy("order_date").rowsBetween(Window.unboundedPreceding, 0)
df = df.withColumn("cumulative_revenue", F.sum("total_revenue").over(w))
```

### Derived metric (margin, rate, ratio)

```python
df = df.withColumn("avg_order_value", F.col("total_revenue") / F.col("order_count"))
# Guard against divide-by-zero
df = df.withColumn(
    "avg_order_value",
    F.when(F.col("order_count") > 0, F.col("total_revenue") / F.col("order_count")).otherwise(None)
)
```

---

## Join Rules

- **Always LEFT join from the fact table** — this preserves all fact rows even when a dimension has no match
- **Never INNER join** — an inner join silently drops unmatched fact rows, distorting aggregations
- **Join key types must match** — cast before joining if needed: `F.col("product_id").cast("int")`
- If a dimension table is missing rows, log a warning but don't fail the pipeline

---

## Naming Conventions

| Pattern | Example |
|---|---|
| Aggregated summary | `<fact>_summary` → `order_items_summary` |
| Grouped by time + dim | `<dim>_<metric>_by_<time>` → `category_sales_by_day` |
| KPI table | `<metric>_<scope>` → `product_performance`, `customer_ltv` |
| Cohort / segment | `<entity>_<segment>` → `customer_by_country` |

---

## Output Path

```
data/gold/<table_name>/
```

Always `coalesce(1)` for local dev. Never carry to production.

---

## What NOT to Do in Gold

- No row-level transformations — that is Silver's job
- No type casting of Silver columns — Silver schema is already clean
- No `select("*")` — always explicit column selection
- No direct reads from Bronze
- No `inner` joins from the fact table — always `left`
- No hardcoded values for business thresholds — accept them as parameters or config
- No `df.show()` — use `print()` with the `[Gold]` prefix
- Do not create a Gold table when the Silver data is insufficient — surface the gap to the user
