---
name: Data Quality
description: Use when implementing data quality checks, validating layer outputs, writing DQ assertions in tests, or diagnosing unexpected null/duplicate/referential integrity issues in the pipeline.
---

# Data Quality — ClaudeDataPipeline

## DQ Contract Per Layer

| Layer | Contract |
|---|---|
| Bronze | Non-empty (at least 1 row per ingested table) |
| Silver | PK null rate = 0%, no duplicate PKs, non-negative measures |
| Gold | Monetary totals reconcile to Silver within 0.01 tolerance |

---

## DQ Check Implementations

### 1. Completeness — Null Rate Per Column

```python
from pyspark.sql import functions as F

def null_rate_report(df):
    total = df.count()
    null_counts = df.select([
        F.count(F.when(F.col(c).isNull(), c)).alias(c)
        for c in df.columns
    ]).collect()[0].asDict()
    return {col: round(count / total * 100, 2) for col, count in null_counts.items()}
```

**Silver PK columns must have 0% null rate**: `product_id`, `customer_id`, `order_id`, `order_item_id`

### 2. Uniqueness — Duplicate PK Detection

```python
def find_duplicate_pks(df, pk_col):
    return df.groupBy(pk_col) \
             .count() \
             .filter(F.col("count") > 1)

# Usage
dupes = find_duplicate_pks(silver_products, "product_id")
if dupes.count() > 0:
    logger.error(f"Duplicate product_ids found: {dupes.count()} groups")
```

### 3. Validity — Value Range Checks

```python
# Prices and quantities must be positive
invalid_prices = silver_order_items.filter(
    (F.col("unit_price") <= 0) | F.col("unit_price").isNull()
)
invalid_quantities = silver_order_items.filter(F.col("quantity") < 1)

# Dates must be non-null
null_dates = silver_orders.filter(F.col("order_date").isNull())
```

### 4. Referential Integrity — FK Checks

```python
# Every customer_id in orders must exist in customers
orphaned_orders = silver_orders.join(
    silver_customers, "customer_id", "left_anti"
)
if orphaned_orders.count() > 0:
    logger.warning(f"Orders with invalid customer_id: {orphaned_orders.count()}")

# Every product_id in order_items must exist in products
orphaned_items = silver_order_items.join(
    silver_products, "product_id", "left_anti"
)

# Every order_id in order_items must exist in orders
orphaned_order_items = silver_order_items.join(
    silver_orders, "order_id", "left_anti"
)
```

### 5. Gold ↔ Silver Reconciliation

```python
# Total revenue in gold must match sum of line_total in silver
silver_total = silver_order_items.agg(
    F.round(F.sum("line_total"), 2).alias("total")
).collect()[0]["total"]

gold_total = gold_product_performance.agg(
    F.round(F.sum("total_revenue"), 2).alias("total")
).collect()[0]["total"]

tolerance = 0.01
assert abs(silver_total - gold_total) < tolerance, \
    f"Revenue mismatch: Silver={silver_total}, Gold={gold_total}"
```

---

## Layer Transition Gates

Insert these checks between layer transitions in `main.py`:

```python
# Gate: Bronze must be non-empty before running Silver
bronze_counts = {
    table: spark.read.parquet(f"data/bronze/{table}").count()
    for table in ["products", "customers", "orders", "order_items"]
}
if any(count == 0 for count in bronze_counts.values()):
    raise ValueError(f"Bronze layer empty for some tables: {bronze_counts}")

# Gate: Silver PK null rate must be 0 before running Gold
pk_nulls = silver_order_items.filter(F.col("order_item_id").isNull()).count()
if pk_nulls > 0:
    raise ValueError(f"Silver order_items has {pk_nulls} null PKs — Gold aborted")
```

---

## DQ Scoring

Use a percentage-based DQ score per table:

```python
def dq_score(checks: dict) -> float:
    """checks = {"check_name": bool_passed}"""
    passed = sum(1 for v in checks.values() if v)
    return round(passed / len(checks) * 100, 1)

# Example
score = dq_score({
    "pk_not_null": products_pk_nulls == 0,
    "no_duplicate_pks": products_dupes == 0,
    "unit_price_positive": invalid_prices == 0,
    "non_empty": products_count > 0,
})
logger.info(f"Products DQ score: {score}%")
```

---

## Future: DataQualityChecker Class

When formalizing DQ, create `src/utils/dq_checker.py`:

```python
class DataQualityError(Exception):
    pass

class DataQualityChecker:
    def __init__(self, spark, logger):
        self.spark = spark
        self.logger = logger

    def assert_non_empty(self, df, table_name):
        count = df.count()
        if count == 0:
            raise DataQualityError(f"{table_name} is empty after ingestion")
        self.logger.info(f"{table_name}: {count} rows OK")

    def assert_pk_no_nulls(self, df, pk_col, table_name):
        null_count = df.filter(F.col(pk_col).isNull()).count()
        if null_count > 0:
            raise DataQualityError(f"{table_name}.{pk_col} has {null_count} nulls")

    def assert_no_duplicates(self, df, pk_col, table_name):
        dupes = df.groupBy(pk_col).count().filter(F.col("count") > 1).count()
        if dupes > 0:
            raise DataQualityError(f"{table_name} has {dupes} duplicate {pk_col} values")
```

---

## Test Assertions for DQ

In pytest tests, assert DQ properties directly:

```python
def test_silver_products_no_null_pks(spark):
    # Arrange: input with one null PK
    data = [(1, "Laptop", "Electronics", 999.99), (None, "Bad", "X", 0.0)]
    df = spark.createDataFrame(data, ["ProductID","ProductName","Category","UnitPrice"])
    # Act
    result = SilverLayer(spark, mock_config, mock_logger).transform_products(df)
    # Assert DQ contract
    null_count = result.filter(F.col("product_id").isNull()).count()
    assert null_count == 0, "Silver contract violated: null product_id in output"
    assert result.count() == 1, "Null PK row should have been dropped"
```
