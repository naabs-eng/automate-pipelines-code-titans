---
name: PySpark Patterns
description: Use when writing PySpark DataFrame code for any of the three pipeline layers, debugging Spark errors, writing PySpark tests, or tuning Spark configuration in this project.
---

# PySpark Patterns — ClaudeDataPipeline

## SparkSession Management

SparkSession is created ONCE in `main.py` and passed to all layer classes. Never create it inside a layer.

```python
# main.py — the only place SparkSession is created
spark = SparkSession.builder \
    .appName(config.get('spark.app_name')) \
    .master(config.get('spark.master')) \
    .config("spark.driver.memory", config.get('spark.memory')) \
    .config("spark.executor.memory", config.get('spark.executor_memory')) \
    .config("spark.jars", config.get('spark.jdbc_driver_path', '')) \
    .getOrCreate()
```

Always stop in the `finally` block of `main.py`:
```python
finally:
    spark.stop()
```

For local dev: `master("local[*]")`. For tests: `master("local[1]")` (deterministic, single-threaded).

---

## JDBC Read Pattern (Bronze Layer)

```python
# Correct JDBC URL for SQL Server with Windows Integrated Auth
jdbc_url = (
    f"jdbc:sqlserver://{server};databaseName={database};"
    "integratedSecurity=true;authenticationScheme=NativeAuthentication"
)

df = spark.read \
    .format("jdbc") \
    .option("url", jdbc_url) \
    .option("dbtable", "dbo.Products") \
    .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
    .load()
```

For SQL auth (user/password), add:
```python
    .option("user", os.getenv("SQL_USER")) \
    .option("password", os.getenv("SQL_PASSWORD")) \
```

Never pass empty strings for user/password with Windows auth — omit them entirely and use `integratedSecurity=true`.

---

## Parquet Write Pattern (All Layers)

```python
# Standard write (all three layers use this)
df.coalesce(1).write.mode("overwrite").parquet(str(output_path))

# Note: coalesce(1) = single output file, fine for local dev
# For production with larger data: use partitionBy instead:
# df.write.mode("overwrite").partitionBy("year", "month").parquet(str(output_path))
```

---

## Parquet Read Pattern (main.py wiring)

```python
from pathlib import Path

bronze_products = spark.read.parquet(
    str(Path(config.get('paths.bronze')) / "products")
)
```

---

## Silver Transform Pattern

Always: explicit select → cast with alias → derived columns → null filter on PK.

```python
from pyspark.sql import functions as F

def transform_order_items(self, bronze_df):
    df = bronze_df.select(
        F.col("OrderItemID").cast("int").alias("order_item_id"),
        F.col("OrderID").cast("int").alias("order_id"),
        F.col("ProductID").cast("int").alias("product_id"),
        F.col("Quantity").cast("int").alias("quantity"),
        F.col("UnitPrice").cast("float").alias("unit_price")
    )
    df = df.withColumn("line_total", F.col("quantity") * F.col("unit_price"))
    df = df.filter(F.col("order_item_id").isNotNull())  # PK null filter always last
    return df
```

---

## Gold Aggregation Pattern

```python
# groupBy + agg
df = silver_order_items.groupBy(
    F.col("order_date"),
    F.col("category")
).agg(
    F.sum("quantity").alias("total_quantity"),
    F.round(F.sum("line_total"), 2).alias("total_sales")
).orderBy("order_date", "category")

# Left join (fact table on left, never inner join)
df = order_items_df.join(products_df, "product_id", "left") \
                   .join(orders_df, "order_id", "left")

# Window function example
from pyspark.sql.window import Window
window = Window.partitionBy("category").orderBy(F.desc("total_revenue"))
df = df.withColumn("rank_in_category", F.rank().over(window))
```

---

## Testing Patterns

```python
# conftest.py — shared fixture (scope="session" so Spark starts once)
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder \
        .master("local[1]") \
        .appName("TestPipeline") \
        .config("spark.sql.shuffle.partitions", "1") \
        .config("spark.driver.bindAddress", "127.0.0.1") \
        .getOrCreate()
```

```python
# Create test DataFrames inline — never read from disk in unit tests
def test_transform_order_items_derives_line_total(spark):
    data = [(1, 10, 5, 3, 9.99)]
    df = spark.createDataFrame(data, ["OrderItemID","OrderID","ProductID","Quantity","UnitPrice"])
    result = SilverLayer(spark, mock_config, mock_logger).transform_order_items(df)
    row = result.collect()[0]
    assert abs(row["line_total"] - 29.97) < 0.001

# Assert schema type (not just column name)
from pyspark.sql.types import IntegerType, FloatType
assert result.schema["product_id"].dataType == IntegerType()
assert result.schema["unit_price"].dataType == FloatType()

# Assert null filter works
def test_transform_products_filters_null_pk(spark):
    data = [(1, "Laptop", "Electronics", 999.99), (None, "Bad", "X", 0.0)]
    df = spark.createDataFrame(data, ["ProductID","ProductName","Category","UnitPrice"])
    result = SilverLayer(spark, mock_config, mock_logger).transform_products(df)
    assert result.count() == 1  # null PK row dropped
```

Use `.collect()` for small DataFrames in assertions, not `.show()`.
Never assert two DataFrames equal directly — compare via `.collect()` with sorted results.

---

## Spark Configuration for Local Dev

Add to `config.yaml`:
```yaml
spark:
  app_name: "SalesDataPipeline"
  master: "local[*]"
  memory: "4g"
  executor_memory: "2g"
  sql_shuffle_partitions: "4"
  jdbc_driver_path: "drivers/mssql-jdbc-12.4.2.jre11.jar"
```

Add to `main.py` SparkSession builder:
```python
.config("spark.sql.shuffle.partitions", config.get('spark.sql_shuffle_partitions', '4'))
.config("spark.driver.bindAddress", "127.0.0.1")
```

`spark.driver.bindAddress=127.0.0.1` prevents PySpark from trying to resolve hostname on Windows — eliminates a common network warning.

---

## Anti-Patterns (Never Use)

| Anti-pattern | Why | Use instead |
|---|---|---|
| `df.toPandas()` | Pulls all data to driver, defeats Spark | Stay in Spark; use `.collect()` for small test data only |
| `df.show()` in production | Side effect, not logged | `logger.info(f"Row count: {df.count()}")` |
| `select("*")` in Silver | Carries PascalCase names downstream | Always explicit `F.col("X").cast().alias("y")` |
| `inner` join in Gold | Silently drops unmatched order items | Always `left` join |
| SparkSession in layer class | One per JVM — multiple breaks things | Create in `main.py`, inject via constructor |
| `coalesce(1)` in production | Bottleneck for large data | Use `partitionBy()` |
| No `.alias()` after cast | Column keeps source name (PascalCase) | Always `.alias("snake_case")` |
