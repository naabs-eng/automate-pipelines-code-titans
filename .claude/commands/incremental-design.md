---
description: Design and implement watermark-based incremental ingestion to replace the current full-overwrite pattern
allowed-tools: Read, Bash
---

## Context

Current ingestion approach:
@src/bronze/ingestion.py
@src/main.py
@config.yaml

Source table structure (for identifying watermark-eligible columns):
@sql/create_schema.sql

## Task

Design and optionally implement incremental ingestion for this pipeline.

### Step 1 — Analyze Current State

The current pipeline uses `write.mode("overwrite")` for all layers and reads entire tables via JDBC on every run. This means every daily run re-ingests all historical data. For small volumes this is fine, but it doesn't scale.

### Step 2 — Identify Watermark Candidates

From `sql/create_schema.sql`, identify which tables have columns suitable for watermarking:
- `dbo.Orders.OrderDate` — datetime column, best watermark candidate (new orders have higher OrderDate than last run)
- `dbo.OrderItems` — no direct timestamp, but incremental via OrderID range or via Orders join
- `dbo.Products`, `dbo.Customers` — reference/dimension tables, typically full reload is fine

### Step 3 — Propose Architecture

Design a `WatermarkManager` utility class:

```python
# src/utils/watermark_manager.py
import json
from pathlib import Path
from datetime import datetime

class WatermarkManager:
    def __init__(self, watermark_path="data/watermarks.json"):
        self.path = Path(watermark_path)
        self._state = self._load()

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {}

    def get(self, table_name: str) -> str | None:
        """Returns last ingested max watermark value for a table."""
        return self._state.get(table_name)

    def update(self, table_name: str, new_watermark: str):
        """Save the new max watermark after successful ingestion."""
        self._state[table_name] = new_watermark
        self.path.write_text(json.dumps(self._state, indent=2))
```

Modified `ingest_from_sql_server()` with watermark support:
```python
def ingest_from_sql_server(self, table_name, bronze_table_name, 
                            watermark_col=None, watermark_value=None):
    if watermark_col and watermark_value:
        # Incremental: only fetch rows newer than last watermark
        query = f"(SELECT * FROM {table_name} WHERE {watermark_col} > '{watermark_value}') AS t"
    else:
        # Full load (for dimension tables or first run)
        query = table_name

    df = self.spark.read.format("jdbc") \
        .option("dbtable", query) \
        ...
    
    if watermark_col:
        # Write as append, not overwrite, to preserve history
        df.write.mode("append").parquet(str(output_path))
    else:
        df.write.mode("overwrite").parquet(str(output_path))
```

### Step 4 — Show Full Diff

Present the complete set of changes needed:
1. `src/utils/watermark_manager.py` — new file
2. `src/bronze/ingestion.py` — modified `ingest_from_sql_server()` and `ingest_all_tables()`
3. `config.yaml` — add `pipeline.mode: incremental` and `pipeline.watermark_col` per table
4. `src/main.py` — wire `WatermarkManager` into the BronzeLayer instantiation

### Step 5 — Confirm and Implement

Ask: "Shall I implement these incremental ingestion changes?"

If confirmed:
1. Write `src/utils/watermark_manager.py`
2. Update `src/bronze/ingestion.py`
3. Update `config.yaml`
4. Update `src/main.py`
5. Add tests for `WatermarkManager` to `tests/`
6. Run `python -m py_compile` on all modified files

Note: The first run after implementing incremental will still be a full load (no watermark yet). On subsequent runs, only new/changed rows are ingested.
