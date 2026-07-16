---
name: Silver Ingestion
description: Use when transforming any Bronze table into a clean, trusted Silver table — covers snake_case renaming, type casting, whitespace trimming, null handling, date standardization, deduplication, surrogate keys, DQ checks, incremental MERGE, and rejected record logging.
---

# Silver Ingestion — ClaudeDataPipeline

## Purpose

Silver produces **clean, typed, trusted data** ready for business use and Gold aggregations. All transformations are row-level — no joins across tables, no aggregations. Every row in Silver must have a non-null primary key.

---

## Transformation Pipeline (apply in this order)

### 1. Rename Columns → snake_case

Apply to all non-audit columns (`_ingestion_timestamp`, `_source_name`, `_load_mode` are untouched):

```python
import re

def to_snake(name):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    s = re.sub(r'[\s\-]+', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.lower().strip('_')

RENAME_MAP = {f.name: to_snake(f.name) for f in df.schema if f.name not in AUDIT_COLS}
for orig, new in RENAME_MAP.items():
    if orig != new:
        df = df.withColumnRenamed(orig, new)
```

### 2. Trim Whitespace + Empty String → null

Apply to every string column (post-rename, non-audit):

```python
for col in STRING_COLS:
    df = df.withColumn(col, F.trim(F.col(col)))
    df = df.withColumn(col, F.when(F.col(col) == "", None).otherwise(F.col(col)))
```

### 3. Cast Data Types

```python
TYPE_CASTS = {
    "supplier_id":  "int",
    "unit_cost":    "double",
    "is_active":    "boolean",
    # ... generated from Bronze schema
}
for col, dtype in TYPE_CASTS.items():
    df = df.withColumn(col, F.col(col).cast(dtype))
```

### 4. Standardize Date / Timestamp Formats

For string columns that represent dates or timestamps, try multiple input formats via `coalesce`:

```python
DATE_FORMATS = ["yyyy-MM-dd", "MM/dd/yyyy", "dd-MM-yyyy", "dd/MM/yyyy", "yyyyMMdd"]
TS_FORMATS   = ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss.SSS",
                "yyyy-MM-dd HH:mm:ss", "MM/dd/yyyy HH:mm:ss"]

# Date columns: name contains "date", "_dt", "_day", "_on", or type is DateType
for col in DATE_COLS:
    df = df.withColumn(col, F.coalesce(*[F.to_date(F.col(col), fmt) for fmt in DATE_FORMATS]))

# Timestamp columns: name contains "_at", "_time", "timestamp", "created", "updated"
for col in TIMESTAMP_COLS:
    df = df.withColumn(col, F.coalesce(*[F.to_timestamp(F.col(col), fmt) for fmt in TS_FORMATS]))
```

### 5. Remove Duplicates

Keep the most recent record per primary key (uses `_ingestion_timestamp` from Bronze audit):

```python
from pyspark.sql import Window

w = Window.partitionBy(PRIMARY_KEY).orderBy(F.desc("_ingestion_timestamp"))
df = df.withColumn("_rn", F.row_number().over(w))
df = df.filter(F.col("_rn") == 1).drop("_rn")
```

### 6. Handle Nulls (configurable strategy)

**`keep`** (default) — keep nulls in non-PK columns; drop only null-PK rows:
```python
df_rejected = df.filter(F.col(PRIMARY_KEY).isNull())
df = df.filter(F.col(PRIMARY_KEY).isNotNull())
```

**`fill`** — fill nulls with type-appropriate defaults after dropping null-PK rows:
```python
NULL_FILLS = {col: "UNKNOWN" for col in STRING_COLS if col != PRIMARY_KEY}
NULL_FILLS.update({col: 0 for col in NUMERIC_COLS if col != PRIMARY_KEY})
for col, val in NULL_FILLS.items():
    df = df.withColumn(col, F.coalesce(F.col(col), F.lit(val)))
```

**`reject`** — reject ANY row where a key column is null (stricter):
```python
df_rejected = df.filter(F.col(PRIMARY_KEY).isNull()).withColumn(
    "_rejection_reason", F.lit(f"null_primary_key:{PRIMARY_KEY}")
)
df = df.filter(F.col(PRIMARY_KEY).isNotNull())
```

### 7. Surrogate Key (optional)

Generate `sk_<table_name>` as an MD5 hash of the primary key:

```python
if SURROGATE_KEY:
    df = df.withColumn(f"sk_{TABLE_NAME}", F.md5(F.col(PRIMARY_KEY).cast("string")))
```

---

## Data Quality Checks

Always run after transformations, before writing:

```python
clean_count  = df.count()
pk_distinct  = df.select(PRIMARY_KEY).distinct().count()

# PK uniqueness
if pk_distinct < clean_count:
    print(f"⚠ PK NOT UNIQUE: {clean_count - pk_distinct} duplicates in {PRIMARY_KEY}")

# Null rates per column — warn if > 20%
for col in business_cols:
    null_count = df.filter(F.col(col).isNull()).count()
    null_rate  = null_count / clean_count * 100 if clean_count > 0 else 0
    flag = "⚠" if null_rate > 20 else "✅"
    print(f"{flag} {col}: {null_count} nulls ({null_rate:.1f}%)")
```

---

## Write Silver

### Full Load
```python
df.coalesce(1).write.mode("overwrite").parquet(f"data/silver/{TABLE_NAME}")
```

### Incremental MERGE

PySpark has no native MERGE — implement with union of three segments:

```python
existing  = spark.read.parquet(SILVER_PATH)
unchanged = existing.join(df.select(PRIMARY_KEY), on=PRIMARY_KEY, how="left_anti")
updated   = df.join(existing.select(PRIMARY_KEY), on=PRIMARY_KEY, how="inner")
new_rows  = df.join(existing.select(PRIMARY_KEY), on=PRIMARY_KEY, how="left_anti")

merged = (
    unchanged
    .unionByName(updated,  allowMissingColumns=True)
    .unionByName(new_rows, allowMissingColumns=True)
)
merged.coalesce(1).write.mode("overwrite").parquet(SILVER_PATH)
```

Always align schemas before union: add missing columns as `F.lit(None).cast(original_type)`.

---

## Rejected Records

Write rows that failed PK validation to a separate path:

```python
if df_rejected is not None and df_rejected.count() > 0:
    df_rejected.withColumn("_rejection_reason", F.lit("null_primary_key")) \
               .coalesce(1).write.mode("overwrite") \
               .parquet(f"data/silver/{TABLE_NAME}_rejected")
```

---

## Primary Key Inference

When the user does not specify a PK:
1. Pick the first column whose snake_case name ends with `_id`
2. If no `_id` column, pick the first non-audit column
3. Never pick an audit column (`_ingestion_timestamp`, `_source_name`, `_load_mode`)

---

## Output Paths

| Bronze input | Silver output | Rejected |
|---|---|---|
| `data/bronze/suppliers/` | `data/silver/suppliers/` | `data/silver/suppliers_rejected/` |
| `data/bronze/employees/` | `data/silver/employees/` | `data/silver/employees_rejected/` |

---

## What NOT to Do in Silver

- No joins across tables (that is Gold's job)
- No `groupBy` / aggregations
- No `select("*")` — always explicit column selection or post-rename operations
- No `df.show()` in production — use `print()` / logger
- Never modify audit columns
- Never write aggregated metrics to Silver
