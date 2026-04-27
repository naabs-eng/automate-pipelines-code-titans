---
name: Data Modeling
description: Use when designing new tables, deciding where a new entity belongs in the medallion layers, modeling star schema relationships, or evaluating whether to add a new Gold aggregation.
---

# Data Modeling — ClaudeDataPipeline

## Current Data Model

### Star Schema (Silver Layer)

```
             [orders]
              order_id PK
              customer_id FK→customers
              order_date

[customers]              [order_items] ← FACT TABLE
 customer_id PK           order_item_id PK
 customer_name            order_id FK→orders
 email                    product_id FK→products
 country                  quantity
                          unit_price
                          line_total (derived)

             [products]
              product_id PK
              product_name
              category
              unit_price
```

**Fact table**: `order_items` — contains the measurements (quantity, price, revenue)
**Dimension tables**: `products`, `customers`, `orders`

This is a classic star schema. `order_items` is the center; all joins originate from it.

---

## Grain

| Table | Grain (one row per...) |
|---|---|
| `products` | Product SKU |
| `customers` | Customer account |
| `orders` | Sales transaction (header) |
| `order_items` | Line item within a transaction |

**Gold `sales_summary`**: Same grain as `order_items` (denormalized)
**Gold `daily_sales_by_category`**: One row per (day, category) combination
**Gold `product_performance`**: One row per product

---

## Modeling Decisions

### Why `order_items` is the fact table

`order_items` has the additive measures: `quantity` (count), `unit_price` (rate), `line_total` (revenue amount). These are the values you sum and average. `orders` is a transaction header — it provides temporal context (order_date) but no measures.

### Why `line_total` lives in Silver not Gold

`line_total = quantity * unit_price` is a row-level calculation (no aggregation needed). Row-level derivations belong in Silver. Gold receives `line_total` as a pre-computed measure and only performs `SUM(line_total)`.

### Why `unit_price` appears in both `products` and `order_items`

`products.unit_price` is the current catalog price. `order_items.unit_price` is the price at time of sale (historical). These can diverge if prices change. Silver preserves both. Gold uses `order_items.unit_price` for revenue calculations (what was actually charged), not `products.unit_price`.

---

## Adding New Tables — Decision Guide

### New Dimension Table (e.g. `Suppliers`, `Regions`, `Categories`)

1. Does it describe a thing (not a measurement)? → Dimension
2. Has a surrogate or natural PK, few measures, many descriptive attributes
3. In Silver: `transform_<entity>()` method with type casting + snake_case aliasing
4. In Gold: update existing Gold tables' joins to include the new dimension if needed
5. No new Gold table required unless a new business question needs it

### New Fact Table (e.g. `Returns`, `Inventory`, `Shipments`)

1. Does it contain measurements (quantities, amounts, counts)? → Fact
2. Has FK references to existing dimensions
3. In Silver: `transform_<entity>()` with measures as numeric types, FK null checks
4. In Gold: new `create_<metric>()` methods for business questions this fact enables
5. Consider if it joins to existing facts (e.g. `Returns` joins to `order_items`)

### New Derived/Bridge Table (e.g. `ProductCategories` many-to-many)

1. Resolve in Silver — bridge tables join two dimensions
2. In Gold: use the resolved bridge for any aggregations spanning both dimensions

---

## Gold Table Design Checklist

Before creating a new Gold table, answer:

1. **What business question does this answer?** (Be specific: "Which products generated the most revenue this month?")
2. **What is the grain?** (One row per what?)
3. **Which Silver tables does it join?** (Fact first, then dimensions)
4. **What are the groupBy keys?** (The grain-defining columns)
5. **What are the measures?** (SUM, COUNT, AVG, etc.)
6. **Does an existing Gold table already answer this question?** (Avoid duplicates)
7. **Will this be consumed by a BI tool or dashboard?** (If yes, consider column naming for readability)

---

## Naming Conventions for New Tables

| Component | Convention | Example |
|---|---|---|
| SQL Server table | `dbo.PascalSingular` | `dbo.Supplier` |
| Bronze directory | `snake_plural` | `suppliers` |
| Silver method | `transform_<snake_plural>` | `transform_suppliers` |
| Gold method | `create_<metric_name>` | `create_supplier_performance` |
| Gold output dir | `<metric_name>` | `supplier_performance` |
| PK column | `<entity>_id` | `supplier_id` |
| FK column | `<referenced_entity>_id` | `supplier_id` (in products) |
| Timestamp columns | `<event>_at` or `<event>_date` | `ordered_at`, `order_date` |
| Derived columns | descriptive noun | `line_total`, `profit_margin` |
| Aggregated columns | `total_<measure>`, `avg_<measure>`, `count_<thing>` | `total_revenue`, `avg_unit_price` |

---

## Future Model Enhancements

Potential additions that follow naturally from the current model:

| Addition | Type | Purpose |
|---|---|---|
| `dbo.Suppliers` | Dimension | Link products to their suppliers |
| `dbo.Returns` | Fact | Track returned order items, net revenue |
| `dbo.Inventory` | Fact/Snapshot | Daily stock levels per product |
| `dbo.Promotions` | Dimension | Discount codes applied to orders |
| `dbo.Regions` | Dimension | Geographic hierarchy for customer.country |
| `customer_ltv` Gold table | Gold | SUM(line_total) per customer, COUNT(DISTINCT order_id) |
| `monthly_revenue_trend` Gold table | Gold | groupBy(year, month) → total_revenue with MoM growth |
