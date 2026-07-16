---
name: Data Explorer
description: Use when extending or debugging the Data Explorer page (pages/6_Data_Explorer.py) — covers table scanning, DuckDB SQL patterns, cross-layer queries, and tab extension.
---

# Data Explorer — ClaudeDataPipeline

## Purpose

The Data Explorer (`pages/6_Data_Explorer.py`) lets users browse all three medallion layers interactively without writing code. It uses `pyarrow` for fast data/schema reads (no Spark) and `duckdb` for the SQL editor.

---

## Layer Scanning

Tables are discovered by listing subdirectories under each layer path:

```python
def _scan_layer(layer_label: str) -> list:
    base = _resolve_path(LAYERS[layer_label])
    for d in sorted(base.iterdir()):
        parts = sorted(d.glob("**/*.parquet"))
        schema    = pq.read_schema(str(parts[0]))
        pf        = pq.ParquetFile(str(parts[0]))
        row_count = pf.metadata.num_rows
```

Layer paths come from `config.get("paths.bronze/silver/gold")`. Always use `_resolve_path()` to handle relative paths.

**Never start Spark** inside a Streamlit page — pyarrow is sufficient for all display operations.

---

## DuckDB SQL Pattern

All tables across all three layers are registered as DuckDB views before executing any user query:

```python
import duckdb
con = duckdb.connect()   # in-memory, no file

for label, raw_path in LAYERS.items():
    base = _resolve_path(raw_path)
    for d in sorted(base.iterdir()):
        parts = sorted(d.glob("**/*.parquet"))
        if parts:
            con.execute(
                f"CREATE OR REPLACE VIEW {d.name} AS "
                f"SELECT * FROM read_parquet('{parts[0]}')"
            )

result_df = con.execute(user_sql).df()
con.close()
```

- Use `CREATE OR REPLACE VIEW` — safe to call multiple times
- Use `d.name.replace("-", "_")` if table directory names contain hyphens
- `con.execute(...).df()` returns a pandas DataFrame

---

## Cross-Layer Queries

Since all layers register under their directory names, users can JOIN across layers:

```sql
-- Bronze vs Silver row count diff
SELECT
    'bronze' AS layer, COUNT(*) AS rows FROM leave_logs_bronze
UNION ALL
SELECT
    'silver', COUNT(*) FROM leave_logs_silver

-- Gold enriched from Silver
SELECT g.department, g.total_approved_leave_days, s.leave_type
FROM   gold_departmental_leave_utilization g
JOIN   leave_logs_silver s ON g.department = s.department
LIMIT  20
```

---

## Tabs

| Tab | What it shows | Key function |
|---|---|---|
| Data | Row preview (configurable) | `pq.read_table().to_pandas().head(n)` |
| Schema | Column names + types, audit col markers | `pq.read_schema()` |
| Info | File size, last modified, watermark, related pipelines | `Path.stat()`, `.watermarks.json`, `config.get("pipelines")` |
| SQL | DuckDB editor, all layers registered | `duckdb.connect()` + `_register_all_views()` |

### Adding a new tab

1. Add a new label to the `st.tabs([...])` call
2. Add a `with tab_new:` block
3. Use `parquet_path` (already resolved) and `selected` dict for the current table

---

## Audit Columns

These three columns are added by `BronzeLayer._add_audit_columns()` and passed through to Silver:

```python
AUDIT_COLS = {"_ingestion_timestamp", "_source_name", "_load_mode"}
```

They are marked with `✓` in the Schema tab and should never be used as join keys or aggregation inputs.

---

## Watermark Info (Bronze only)

Watermarks are stored in `data/bronze/.watermarks.json`, keyed by bronze table name:

```json
{
  "leave_logs_bronze": {
    "last_ingested": "2026-07-12T11:55:12+00:00",
    "source_type": "file",
    "mode": "full"
  }
}
```

Only show the watermark section when `"Bronze" in layer_label`.
