---
description: Run data quality checks — null rates, PK uniqueness, referential integrity, Gold-Silver reconciliation
allowed-tools: Bash, Read
argument-hint: "[bronze|silver|gold] — omit to check all layers"
---

## Context

Current data state:
!`python -c "import os; [print(f'data/{l}:', os.listdir(f'data/{l}') if os.path.exists(f'data/{l}') else 'EMPTY') for l in ['bronze','silver','gold']]" 2>&1`

DQ skill reference: @.claude/skills/data-quality.md

## Task

Run data quality checks on layer: **$ARGUMENTS** (if empty, check all layers).

### DQ Script to Execute

Run the following Python script to perform all checks:

```python
python -c "
from pyspark.sql import SparkSession, functions as F
import os

spark = SparkSession.builder.master('local').appName('dq_check') \
    .config('spark.driver.bindAddress','127.0.0.1') \
    .getOrCreate()

results = []

def check(name, passed, detail=''):
    results.append({'check': name, 'passed': passed, 'detail': detail})
    status = 'PASS' if passed else 'FAIL'
    print(f'  [{status}] {name}' + (f': {detail}' if detail else ''))

# Bronze checks
for tbl in ['products','customers','orders','order_items']:
    path = f'data/bronze/{tbl}'
    if os.path.exists(path):
        df = spark.read.parquet(path)
        count = df.count()
        check(f'bronze.{tbl} non-empty', count > 0, f'{count} rows')

# Silver checks
for tbl, pk in [('products','product_id'),('customers','customer_id'),('orders','order_id'),('order_items','order_item_id')]:
    path = f'data/silver/{tbl}'
    if os.path.exists(path):
        df = spark.read.parquet(path)
        total = df.count()
        null_pks = df.filter(F.col(pk).isNull()).count()
        dupes = df.groupBy(pk).count().filter(F.col('count')>1).count()
        check(f'silver.{tbl} pk_not_null', null_pks==0, f'{null_pks} nulls in {pk}')
        check(f'silver.{tbl} pk_unique', dupes==0, f'{dupes} duplicate {pk} values')

# Silver value range checks
oi_path = 'data/silver/order_items'
if os.path.exists(oi_path):
    oi = spark.read.parquet(oi_path)
    bad_price = oi.filter(F.col('unit_price')<=0).count()
    bad_qty = oi.filter(F.col('quantity')<1).count()
    check('silver.order_items unit_price_positive', bad_price==0, f'{bad_price} invalid prices')
    check('silver.order_items quantity_positive', bad_qty==0, f'{bad_qty} invalid quantities')

# Referential integrity
orders_path = 'data/silver/orders'
customers_path = 'data/silver/customers'
if os.path.exists(orders_path) and os.path.exists(customers_path):
    orders = spark.read.parquet(orders_path)
    customers = spark.read.parquet(customers_path)
    orphans = orders.join(customers,'customer_id','left_anti').count()
    check('silver.orders fk_customer_id_valid', orphans==0, f'{orphans} orphaned orders')

# Gold reconciliation
pp_path = 'data/gold/product_performance'
if os.path.exists(oi_path) and os.path.exists(pp_path):
    oi = spark.read.parquet(oi_path)
    pp = spark.read.parquet(pp_path)
    silver_total = round(oi.agg(F.sum('line_total').alias('t')).collect()[0]['t'] or 0, 2)
    gold_total = round(pp.agg(F.sum('total_revenue').alias('t')).collect()[0]['t'] or 0, 2)
    diff = abs(silver_total - gold_total)
    check('gold_silver_revenue_reconciliation', diff<0.01, f'silver={silver_total}, gold={gold_total}, diff={diff}')

passed = sum(1 for r in results if r['passed'])
total = len(results)
print(f'\nDQ Score: {passed}/{total} checks passed ({round(passed/total*100,1)}%)')
spark.stop()
"
```

### After Running

1. Display the DQ check results in a summary table.
2. For any FAIL: explain what the failure means for pipeline correctness and what fix is needed.
3. If revenue reconciliation fails: check whether `daily_sales_by_category` and `product_performance` join logic in `src/gold/aggregations.py` is using the correct join type (`left`, not `inner`).
4. Write a DQ report summary to `logs/dq_report_<timestamp>.txt`.
5. Report overall DQ health: GREEN (all pass), YELLOW (non-critical warnings), RED (contract violations in Silver or Gold reconciliation failures).
