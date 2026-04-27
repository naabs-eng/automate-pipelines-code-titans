---
description: Run full or partial ETL pipeline with pre-flight checks and post-run summary
allowed-tools: Bash, Read, Glob
argument-hint: "[bronze|silver|gold] — omit to run full pipeline"
---

## Context

Current config state:
!`python -c "from src.config.config_manager import ConfigManager; c=ConfigManager(); print('Server:', c.get('sql_server.server'), '| DB:', c.get('sql_server.database'), '| Bronze path:', c.get('paths.bronze'), '| Tables:', [t['bronze_table'] for t in c.get('tables.source', [])])" 2>&1`

Data layer status:
!`python -c "import os; layers=['bronze','silver','gold']; [print(f'{l}:', [d for d in os.listdir(f'data/{l}') if not d.startswith('.')] if os.path.exists(f'data/{l}') else 'missing') for l in layers]" 2>&1`

Latest log (if any):
!`python -c "import os, pathlib; logs=sorted(pathlib.Path('logs').glob('*.log')) if pathlib.Path('logs').exists() else []; print(open(logs[-1]).readlines()[-5:] if logs else 'No logs yet')" 2>&1`

## Task

The user wants to run: **$ARGUMENTS** (if empty, run the full pipeline)

### Step 1 — Pre-flight checks

1. Verify `config.yaml` loads without error (already shown above).
2. Check that all required config keys exist: `sql_server.server`, `sql_server.database`, `spark.app_name`, `spark.master`, `paths.bronze`, `paths.silver`, `paths.gold`, `tables.source`.
3. Check `data/bronze/`, `data/silver/`, `data/gold/` directories exist. Create any that are missing with `mkdir -p`.
4. Check if `drivers/` directory has a `.jar` file — if missing, warn that the MSSQL JDBC driver is required before ingestion will work.
5. If `$ARGUMENTS` is `silver` or `gold`, verify the upstream layer's Parquet directories are non-empty before running.

### Step 2 — Execute

- If `$ARGUMENTS` is empty or `full`: run `python src/main.py`
- If `$ARGUMENTS` is `bronze`: explain that individual-layer execution requires a `--layer` flag not yet implemented; offer to run the full pipeline
- If `$ARGUMENTS` is `silver` or `gold`: run `python src/main.py` (full pipeline); note which layers will be the focus

Show the command before running it. Capture and display stdout/stderr.

### Step 3 — Post-run report

After execution:
1. Find the latest log file in `logs/` and show the last 20 lines.
2. For each Gold table in `data/gold/`, report the row count:
   ```python
   python -c "
   from pyspark.sql import SparkSession
   spark = SparkSession.builder.master('local').appName('check').getOrCreate()
   import os
   for t in ['sales_summary', 'daily_sales_by_category', 'product_performance']:
       path = f'data/gold/{t}'
       if os.path.exists(path):
           print(f'{t}: {spark.read.parquet(path).count()} rows')
   spark.stop()
   "
   ```
3. Report: SUCCESS (all Gold tables non-empty) or FAILURE (describe which step failed and what the error was).
4. On failure: extract ERROR lines from the log, match to known patterns in `.claude/skills/sql-server-integration.md` and `.claude/skills/pyspark-patterns.md`, and provide a specific fix suggestion.
