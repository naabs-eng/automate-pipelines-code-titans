---
name: Bronze Ingestion
description: Use when ingesting any source (PostgreSQL or flat file) into the Bronze layer — covers audit columns, full/incremental modes, schema evolution, watermark state, and write patterns.
---

# Bronze Ingestion — ClaudeDataPipeline

## Purpose

Bronze is a **faithful, raw copy** of the source. No business logic, no renaming, no transformations. Every Bronze table is a snapshot (full) or append (incremental) of exactly what the source contained at ingestion time.

---

## Audit Columns — Always Required

Every Bronze table must have these three columns added via `_add_audit_columns()`:

```python
df = (
    df.withColumn("_ingestion_timestamp", F.current_timestamp())
      .withColumn("_source_name", F.lit(source_name))   # table name or file path
      .withColumn("_load_mode", F.lit(mode))             # "full" or "incremental"
)
```

Never skip these. Silver uses `_ingestion_timestamp` for deduplication ordering.

---

## Load Modes

### Full Load (default)
```python
df.coalesce(1).write.mode("overwrite").parquet(str(output_path))
```

### Incremental Load
Append new rows and handle schema evolution (new columns in source that don't exist in existing Bronze):

```python
if mode == "incremental" and bronze_exists:
    existing = spark.read.parquet(str(output_path))
    # Null-fill any columns that dropped out of the incoming batch
    for col_name, col_type in {f.name: f.dataType for f in existing.schema}.items():
        if col_name not in incoming_col_names:
            df = df.withColumn(col_name, F.lit(None).cast(col_type))
    df.coalesce(1).write.option("mergeSchema", "true").mode("append").parquet(str(output_path))
else:
    df.coalesce(1).write.mode("overwrite").parquet(str(output_path))
```

---

## PostgreSQL Ingestion

```python
jdbc_url = f"jdbc:postgresql://{host}:{port}/{database}"
props = {
    "user": os.environ.get("PG_USERNAME") or getpass.getuser(),  # never pass empty string
    "password": os.environ.get("PG_PASSWORD", ""),
    "driver": "org.postgresql.Driver",
}

# Full load
df = spark.read.jdbc(url=jdbc_url, table=table_name, properties=props)

# Incremental: push predicate to the database
if last_watermark:
    query = f"(SELECT * FROM {table_name} WHERE {watermark_col} > '{last_watermark}') t"
    df = spark.read.jdbc(url=jdbc_url, table=query, properties=props)
```

**Driver**: `spark.driver.extraClassPath` / `spark.executor.extraClassPath` — NOT `spark.jars` (causes network errors in local mode on Mac).

**Credentials**: always `os.environ.get("PG_USERNAME") or getpass.getuser()`. Passing `user=""` causes JDBC auth failure.

Per-table connection overrides (`host`, `port`, `database`) are passed as kwargs; fall back to global config when `None`.

---

## File Ingestion

```python
# Auto-detect format from extension
ext = Path(file_path).suffix.lower().lstrip(".")
format_map = {"tsv": "csv"}
file_format = format_map.get(ext, ext)

if file_format in ("csv", "tsv"):
    sep = "\t" if original_ext == "tsv" else ","
    df = spark.read.csv(str(path), header=True, inferSchema=True, sep=sep)
elif file_format == "json":
    df = spark.read.json(str(path))
elif file_format == "parquet":
    df = spark.read.parquet(str(path))
```

Source name for audit column = `str(path)` (full file path).

---

## Watermark State

Stored at `data/bronze/.watermarks.json`. Updated after every successful ingest:

```python
{
  "suppliers": {
    "last_ingested": "2026-07-09T10:00:00+00:00",
    "source_type": "postgresql",
    "mode": "incremental",
    "watermark_col": "updated_at",
    "last_watermark_value": "2026-07-08T22:00:00"
  }
}
```

Always use `datetime.now(timezone.utc)` — never `datetime.utcnow()` (deprecated).

---

## Output Paths and Naming

| Source | Bronze directory |
|---|---|
| `public.suppliers` | `data/bronze/suppliers/` |
| `public.order_items` | `data/bronze/order_items/` |
| `employees.csv` | `data/bronze/employees/` |
| `transactions.json` | `data/bronze/transactions/` |

Rule: `table.split(".")[-1]` for PostgreSQL; `Path(file).stem` for files.

---

## What NOT to Do in Bronze

- No renaming columns
- No type casting
- No filtering rows
- No joins or aggregations
- No `df.toPandas()` or `df.show()`
- No hardcoded credentials — always read from `.env` via `os.environ`
- `coalesce(1)` is fine for local dev; do not carry to production
