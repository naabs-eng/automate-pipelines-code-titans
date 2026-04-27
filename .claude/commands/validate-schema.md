---
description: Validate actual Parquet schemas at each layer against expected contracts
allowed-tools: Bash, Read
argument-hint: "[bronze|silver|gold] — omit to check all layers"
---

## Context

Layer source definitions:
@src/bronze/ingestion.py
@src/silver/transformations.py
@src/gold/aggregations.py

Parquet data present:
!`python -c "import os; [print(f'data/{l}:', os.listdir(f'data/{l}') if os.path.exists(f'data/{l}') else 'EMPTY') for l in ['bronze','silver','gold']]" 2>&1`

## Task

Validate actual Parquet schemas against the expected contracts. Layer to check: **$ARGUMENTS** (if empty, check all layers).

### Expected Contracts

**Bronze** (must mirror SQL Server source — PascalCase column names):
- `products`: ProductID, ProductName, Category, UnitPrice
- `customers`: CustomerID, CustomerName, Email, Country
- `orders`: OrderID, CustomerID, OrderDate
- `order_items`: OrderItemID, OrderID, ProductID, Quantity, UnitPrice

**Silver** (snake_case, explicit types):
- `products`: product_id (int), product_name (string), category (string), unit_price (float)
- `customers`: customer_id (int), customer_name (string), email (string), country (string)
- `orders`: order_id (int), customer_id (int), order_date (timestamp)
- `order_items`: order_item_id (int), order_id (int), product_id (int), quantity (int), unit_price (float), line_total (float)

**Gold** (aggregated, numeric measures):
- `sales_summary`: order_date, product_id, product_name, category, quantity, unit_price, line_total
- `daily_sales_by_category`: order_date, category, total_quantity (long), total_sales (double/float)
- `product_performance`: product_id, product_name, category, total_quantity_sold (long), total_revenue (double/float), avg_price (double/float)

### Steps

For each table in the target layer(s):

1. Read the Parquet schema:
   ```python
   spark.read.parquet('data/<layer>/<table>').printSchema()
   ```

2. Compare actual vs. expected:
   - Are all expected columns present?
   - Are types compatible (e.g. int vs. long is often acceptable, but string vs. timestamp is not)?
   - Are there extra unexpected columns?
   - For Silver: are all column names snake_case (no PascalCase remaining)?

3. Report findings as a table:
   | Layer | Table | Column | Expected Type | Actual Type | Status |
   |---|---|---|---|---|---|

4. Flag any Silver table where `line_total` is missing or is string type — this breaks Gold aggregations.

5. Flag any Gold table where revenue/quantity columns are string type — this indicates a failed cast upstream.

6. If all checks pass: report "Schema contracts satisfied for all checked layers."
7. If checks fail: for each violation, identify which source file (`transformations.py` or `aggregations.py`) needs to be updated and what the fix is.
