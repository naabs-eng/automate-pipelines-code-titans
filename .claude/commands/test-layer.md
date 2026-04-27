---
description: Generate and run pytest tests for a specific medallion layer
allowed-tools: Read, Bash
argument-hint: "bronze|silver|gold — which layer to test"
---

## Context

Layer to test: **$ARGUMENTS**

Source file for this layer:
!`python -c "layer='$ARGUMENTS'; files={'bronze':'src/bronze/ingestion.py','silver':'src/silver/transformations.py','gold':'src/gold/aggregations.py'}; print(files.get(layer, 'unknown layer'))"`

@src/bronze/ingestion.py
@src/silver/transformations.py
@src/gold/aggregations.py

PySpark testing patterns: @.claude/skills/pyspark-patterns.md
Data quality contracts: @.claude/skills/data-quality.md

Existing tests:
!`find tests/ -name "*.py" 2>/dev/null || echo "No test files yet"`

## Task

Generate a complete pytest test file for the **$ARGUMENTS** layer.

### Step 1 — Check for `tests/conftest.py`

If `tests/conftest.py` does not exist, create it first:

```python
# tests/conftest.py
import pytest
from pyspark.sql import SparkSession
from unittest.mock import MagicMock

@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder \
        .master("local[1]") \
        .appName("TestPipeline") \
        .config("spark.sql.shuffle.partitions", "1") \
        .config("spark.driver.bindAddress", "127.0.0.1") \
        .getOrCreate()

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        'paths.bronze': 'data/bronze',
        'paths.silver': 'data/silver',
        'paths.gold': 'data/gold',
    }.get(key, default)
    return config

@pytest.fixture
def mock_logger():
    return MagicMock()
```

Also create `pytest.ini` if it doesn't exist:
```ini
[pytest]
markers =
    integration: marks tests that require a live SQL Server connection
    unit: marks pure unit tests with no Spark or external dependencies
addopts = -v
```

### Step 2 — Generate Test File

**For `bronze`** → write `tests/test_bronze_ingestion.py`:
- Test `BronzeLayer` initializes and creates output directory
- Test that `ingest_all_tables()` calls `ingest_from_sql_server()` for each table in config
- Mark actual JDBC tests with `@pytest.mark.integration`

**For `silver`** → write `tests/test_silver_transformations.py`:
- For each `transform_<entity>()` method:
  - Test: valid input → correct snake_case column names
  - Test: valid input → correct data types (int, float, string, timestamp)
  - Test: row with null PK → dropped from output (Silver contract)
  - Test: `transform_order_items` → `line_total = quantity * unit_price` is correctly derived
  - Test: empty DataFrame input → returns empty DataFrame (not error)

**For `gold`** → write `tests/test_gold_aggregations.py`:
- For `create_sales_summary()`: verify it joins all three tables and correct columns present
- For `create_daily_sales_by_category()`: verify groupBy produces correct aggregated values
- For `create_product_performance()`: verify `total_revenue` is sum of `line_total`, ordered DESC
- Test: left join preserves order_items even when product is missing (not dropped)

### Step 3 — Run Tests

```bash
pytest tests/test_$ARGUMENTS_*.py -v -m "not integration"
```

### Step 4 — Report Results

Show the pytest output. If any tests fail:
1. Identify whether it's a test bug (wrong expected value) or a source code bug (actual code behavior wrong)
2. If it's a source code bug, show the fix in the relevant layer file
3. If it's a test bug, fix the test assertion
4. Re-run after fixing

Target: all unit tests pass. Integration tests can be marked and skipped in CI.
