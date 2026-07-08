---
description: Dynamically transform any Bronze table to Silver and optionally create Gold aggregations — no pre-written Python files needed
allowed-tools: Read, Bash, Write
argument-hint: "<bronze_table_name> [primary_key=<col>] — e.g. suppliers, inventory primary_key=inventory_id"
---

## Context

Table to process: **$ARGUMENTS**

Read current config to get driver paths and output paths:
@config.yaml

## Task

Dynamically transform the specified Bronze table through Silver (and optionally Gold) using auto-generated PySpark code. No hardcoded transform files — everything is generated from the live Bronze schema.

---

### Step 1 — Parse Arguments

Extract from `$ARGUMENTS`:
- `table_name` — the Bronze table directory name (e.g. `suppliers`)
- `primary_key` — optional, passed as `primary_key=<col>` (e.g. `primary_key=supplier_id`)

---

### Step 2 — Read Bronze Schema

Run this to inspect the Bronze Parquet schema:

```bash
python3 -c "
from pyspark.sql import SparkSession
import os, sys
sys.path.insert(0, 'src')
from config.config_manager import ConfigManager
c = ConfigManager()
pg_driver = str(__import__('pathlib').Path(c.get('spark.pg_driver_path')))
spark = SparkSession.builder.master('local').appName('schema_check') \
    .config('spark.driver.extraClassPath', pg_driver) \
    .getOrCreate()
spark.sparkContext.setLogLevel('ERROR')
df = spark.read.parquet('data/bronze/<TABLE_NAME>')
df.printSchema()
print('Sample:')
df.show(3)
spark.stop()
"
```

Replace `<TABLE_NAME>` with the actual table name. Capture the schema output.

---

### Step 3 — Infer Column Mappings

From the schema output:
1. For each column, generate its `snake_case` name:
   - Already snake_case (e.g. `supplier_id`) → keep as-is
   - PascalCase (e.g. `ProductID`) → convert: insert `_` before uppercase letters, lowercase all → `product_id`
2. Infer `primary_key`:
   - If passed as argument, use it
   - Otherwise pick the first column ending in `_id` or `ID`
   - If ambiguous, ask the user

---

### Step 4 — Generate & Run Silver Transform

Generate a self-contained PySpark script and write it to `/tmp/silver_<table_name>.py`, then execute it.

The script must:
- Start its own SparkSession (local mode, `extraClassPath` for pg driver from config)
- Read from `data/bronze/<table_name>/`
- Select all columns with explicit `.cast(<type>).alias(<snake_name>)` for each
- Filter rows where `primary_key` is null
- Write `coalesce(1)` Parquet to `data/silver/<table_name>/`
- Print row count and schema on success
- Call `spark.stop()`

Run it:
```bash
python3 /tmp/silver_<table_name>.py 2>&1
```

Show the output to the user. If it fails, parse the error and fix the script before retrying (max 2 retries).

---

### Step 5 — Verify Silver Output

After successful run:
```bash
python3 -c "
from pyspark.sql import SparkSession
spark = SparkSession.builder.master('local').appName('verify').getOrCreate()
spark.sparkContext.setLogLevel('ERROR')
df = spark.read.parquet('data/silver/<TABLE_NAME>')
print(f'Rows: {df.count()}')
df.printSchema()
df.show(5)
spark.stop()
"
```

Report the row count and column names to the user.

---

### Step 6 — Offer Gold Aggregations

Ask the user:
> "Silver for `<table_name>` is done (`N` rows). Do you want to create a Gold aggregation table?
> I can auto-generate one based on the schema — e.g. group by category/date columns and sum numeric columns.
> Reply `yes` to proceed or `no` to skip."

If the user says **yes**:

1. Inspect the Silver schema:
   - Identify **dimension columns**: string/date columns (e.g. `category`, `country`, `status`, `shipment_date`)
   - Identify **measure columns**: numeric columns (e.g. `stock_quantity`, `unit_cost`)

2. Generate a Gold script at `/tmp/gold_<table_name>_summary.py`:
   - Read from `data/silver/<table_name>/`
   - `groupBy` the most meaningful dimension columns (pick 1-2, e.g. `category` or `status`)
   - Aggregate: `sum` of numeric columns, `count` of rows
   - Order by the primary aggregate descending
   - Write to `data/gold/<table_name>_summary/`

3. Execute and verify output, show results to user.

---

### Step 7 — Cleanup

Delete the temp scripts:
```bash
rm -f /tmp/silver_<table_name>.py /tmp/gold_<table_name>_summary.py
```

Report what was created:
- `data/silver/<table_name>/` — N rows, M columns
- `data/gold/<table_name>_summary/` — (if created) N rows
