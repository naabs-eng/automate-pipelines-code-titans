# ClaudeDataPipeline — Project Memory

## Project Identity

- **Type**: Python + PySpark ETL pipeline, Medallion Architecture (Bronze → Silver → Gold)
- **Sources**: PostgreSQL (`localhost/postgres`) + file sources (CSV/JSON under `data/sources/`)
- **Output**: Parquet files under `data/<layer>/<table_name>_<layer>/`
- **Primary entry point**: `streamlit run app.py` (from project root)
- **Secondary entry point**: `python src/main.py` (legacy CLI, kept for direct Spark runs)
- **Config**: `config.yaml` — accessed via `ConfigManager.get('dot.notation.key')`
- **Domain**: Customer transactions + HR employee leave data

---

## Architecture Map

```
app.py                          — Streamlit router + full CSS aurora theme
pages/
  2_Bronze_Silver.py            — Run Bronze/Silver ingestion via UI
  3_Gold_Builder.py             — Design and build Gold aggregation tables
  4_Monitor_Pipelines.py        — Monitor pipeline run history and status
  5_Gold_Agent.py               — AI-powered Gold query agent
  6_Data_Explorer.py            — Browse/query Parquet data with DuckDB SQL

src/
  main.py                       — Legacy entry point: SparkSession + layer wiring (SQL Server era)
  run_bronze.py                 — Bronze ingestion CLI, invoked by Bronze_Silver page
  run_silver_gold.py            — Silver/Gold pipeline CLI, invoked by Bronze_Silver + Gold_Builder pages
  analyse_gold.py               — Gold table analysis, invoked by Gold_Builder page
  gold_agent.py                 — Gold AI agent logic, invoked by Gold_Agent page
  gold_chatbot.py               — Gold chatbot helper utilities
  pipeline_docs.py              — Pipeline .md doc generator, invoked by Monitor page
  bronze/ingestion.py           — BronzeLayer: PostgreSQL + file → Parquet (raw, no transforms)
  config/config_manager.py      — ConfigManager: YAML dot-notation access
  utils/logger.py               — PipelineLogger: timestamped file + console handlers
  utils/db_validator.py         — PostgreSQL connectivity validator

pipelines/                      — Auto-generated .md docs, one per pipeline
data/
  bronze/                       — Raw Parquet (suffix: _bronze)
  silver/                       — Cleaned/typed Parquet (suffix: _silver)
  gold/                         — Aggregated Parquet (no suffix)
  sources/                      — Raw source files (CSV/JSON)
sql/
  create_schema.sql             — SQL Server DDL (legacy, for reference)
  insert_sample_data.sql        — SQL Server sample data (legacy, for reference)
```

### Dependency Injection Pattern

`BronzeLayer` is constructed with `(spark, config_manager, logger)`. SparkSession is created once in `main.py` and passed down. Never instantiate SparkSession inside a layer class. The Streamlit UI invokes `run_bronze.py` and `run_silver_gold.py` as subprocesses — they create their own SparkSession internally.

---

## Active Pipelines

Pipelines are defined in `config.yaml` under the `pipelines:` key and tracked as `.md` docs in `pipelines/`.

| Pipeline | Schedule | Sources | Produces |
|---|---|---|---|
| `pl_enrich_customer_transactions_bronze_silver` | Daily 08:00 | `pg_customers`, `transactions.json` | `pg_customers_bronze/silver`, `transactions_bronze/silver` |
| `pl_enrich_customer_transactions_gold` | Weekly Monday 10:00 | `pg_customers_silver`, `transactions_silver` | Gold (see `pipelines/` docs) |
| `pl_hr_employee_leave_reconciliation_bronze_silver` | Run Once | `pg_employees`, `leave_logs.csv` | `pg_employees_bronze/silver`, `leave_logs_bronze/silver` |
| `pl_hr_employee_leave_reconciliation_gold` | Run Once | `leave_logs_silver`, `pg_employees_silver` | Gold (see `pipelines/` docs) |

**Unused source files** (in `data/sources/` but not wired to any pipeline yet): `employees.csv`, `route_telemetry.csv`, `ticket_events.json`

---

## Medallion Layer Contracts

### Bronze — Raw Ingestion
- **Rule**: Faithful copy of source. Zero business logic. Zero renaming.
- **Schema**: Identical to source (PostgreSQL column names and types; file source column names as-is)
- **Write mode**: `overwrite` (full load, idempotent)
- **Output naming**: `data/bronze/<table_name>_bronze/` — `_bronze` suffix is mandatory
- **Source → Bronze**: `pg_customers → pg_customers_bronze`, `pg_employees → pg_employees_bronze`, `transactions.json → transactions_bronze`, `leave_logs.csv → leave_logs_bronze`

### Silver — Validated & Typed
- **Rule**: Clean, typed, snake_case, null-safe DataFrames. Row-level only — no aggregation.
- **Contract**: Every row in Silver has a non-null primary key. Null PK filter is always the last operation.
- **Output naming**: `data/silver/<table_name>_silver/` — `_silver` suffix is mandatory
- **Write mode**: `overwrite`

### Gold — Business Aggregations
- **Rule**: groupBy + agg only. Never modify Silver-level row data. Analysts consume Gold.
- **Join strategy**: Always `left` join from fact table. Never `inner` join.
- **Output naming**: `data/gold/<descriptive_name>/` — no layer suffix, named by business metric
- **Active Gold tables**:
  - `gold_customer_revenue_summary` — customer revenue from transactions pipeline
  - `gold_departmental_leave_utilization` — department-level leave stats from HR pipeline

---

## Naming Conventions

- **PostgreSQL source**: `public.<snake_case>` (e.g. `public.pg_customers`)
- **Bronze output**: `<source_name>_bronze` (e.g. `pg_customers_bronze`, `transactions_bronze`)
- **Silver output**: `<source_name>_silver` (e.g. `pg_customers_silver`, `transactions_silver`)
- **Gold output**: descriptive snake_case metric name (e.g. `gold_customer_revenue_summary`)
- **Pipeline names**: `pl_<domain>_<description>_<layer>` (e.g. `pl_hr_employee_leave_reconciliation_gold`)
- **New tables**: PostgreSQL source → `<name>_bronze` → `<name>_silver` pattern

---

## Known Bugs & Gaps (Claude must proactively flag these)

1. **`coalesce(1)` is dev-only**: All writes use `coalesce(1)` which produces a single Parquet file. Fine for this local project; do not carry this to production.

2. **No watermarking / incremental ingestion**: Pipeline does full overwrite on every run. No `last_ingested` state tracked. Use `/incremental-design` command to scaffold this improvement.

3. **Empty `tests/`**: No test coverage exists. Use `/test-layer` command to generate pytest suites.

4. **Logger creates a new file per `get_logger()` call**: If called multiple times in one run, multiple log files are created. Refactor to use a single session log file.

5. **Stale Gold tables in `data/gold/`**: Directories `ec_categories_summary`, `employees_summary`, `inventory_by_category`, `inventory_summary`, `shipments_by_status`, `shipments_summary`, `supplier_inventory_summary`, `suppliers_summary` are from an earlier pipeline iteration (suppliers/inventory/shipments era). They are not produced by any current pipeline and can be deleted.

6. **`python-dotenv` not wired**: It's in `requirements.txt` but never imported. PostgreSQL credentials come from `config.yaml`. If credentials need to be moved to `.env`, wire via `load_dotenv()` in `run_bronze.py`.

7. **`src/main.py` is legacy**: It still references the SQL Server era layer classes. Do not extend it — use `run_bronze.py` / `run_silver_gold.py` for new ingestion work.

---

## What NOT to Do

- **Never** instantiate `SparkSession` inside `BronzeLayer`
- **Never** use `inner` join in Gold aggregations — always `left` to preserve all fact rows
- **Never** use `select("*")` in Silver — always explicit column selection with `.alias()`
- **Never** commit `data/`, `logs/`, `.env` — they are gitignored
- **Never** put business logic (aggregations, joins across tables) in Silver
- **Never** put row-level transformations in Gold
- **Never** hardcode connection strings or credentials — always read from `config.yaml`
- **Never** use `df.toPandas()` in the pipeline — defeats Spark's execution model
- **Never** use `df.show()` in production code — use `logger.info()`
- **Never** create a `_bronze` or `_silver` output directory without the suffix — non-suffixed dirs are considered stale and will be cleaned up
- **Never** add entries to `tables.pg_source` or `tables.file_source` in config.yaml — those sections are removed; use the `pipelines:` structure instead

---

## Dev Runbook

```bash
# Install dependencies
pip install -r requirements.txt

# Run Streamlit app (primary entry point)
streamlit run app.py

# Validate config.yaml loads correctly
python -c "from src.config.config_manager import ConfigManager; c=ConfigManager(); print(c.get('postgresql.host'), c.get('paths.bronze'))"

# Run Bronze ingestion for a pipeline (example)
python src/run_bronze.py --pipeline pl_enrich_customer_transactions_bronze_silver

# Run Silver/Gold for a pipeline (example)
python src/run_silver_gold.py --pipeline pl_enrich_customer_transactions_bronze_silver

# Check Parquet output (example: gold customer revenue)
python -c "
import pyarrow.parquet as pq
t = pq.read_table('data/gold/gold_customer_revenue_summary')
print(t.schema)
print(t.to_pandas().head())
"

# Run tests (once written)
pytest tests/ -v
pytest tests/ -v -m "not integration"

# Syntax check all source files
python -m py_compile src/bronze/ingestion.py src/run_bronze.py src/run_silver_gold.py src/main.py

# View latest pipeline log
ls -t logs/ | head -1

# Set up PostgreSQL source tables
# Run sql/create_schema.sql equivalent in psql for your source tables
# Data is managed manually in PostgreSQL

# Set up SQL Server sample data (legacy reference only)
# 1. Run sql/create_schema.sql in SSMS
# 2. Run sql/insert_sample_data.sql in SSMS
```

---

## Hooks

Claude Code hooks are in `.claude/hooks/` and wired in `.claude/settings.json`.

| Hook | Event | Does |
|---|---|---|
| `pre_bash_guard.py` | PreToolUse → Bash | Blocks `rm -rf`, force push, DROP TABLE, `> config.yaml`, `> .env` |
| `post_bash_logger.py` | PostToolUse → Bash | Audit trail to `logs/claude_session_audit.log`; pipeline outcomes to `logs/pipeline_runs.log` |
| `post_py_compile.py` | PostToolUse → Write/Edit | Syntax-checks any `.py` file immediately after it's written — surfaces errors before proceeding |
| `post_yaml_validate.py` | PostToolUse → Write/Edit | Validates `config.yaml` parses as YAML and has required top-level keys after any edit |
| `session_summary.py` | Stop | Prints command + pipeline run stats when Claude Code session ends |

---

## Skills Reference

Claude should consult these domain documents when working on specific tasks:

- `.claude/skills/medallion-architecture.md` — Layer design rules, contracts, when to add new tables
- `.claude/skills/pyspark-patterns.md` — DataFrame idioms, test patterns, anti-patterns
- `.claude/skills/data-quality.md` — DQ checks, null rates, referential integrity, Gold↔Silver reconciliation
- `.claude/skills/bronze-ingestion.md` — Audit columns, full/incremental modes, schema evolution, watermark state, PostgreSQL + file patterns
- `.claude/skills/silver-ingestion.md` — snake_case renaming, type casting, dedup, null strategies, date standardization, DQ checks, MERGE, rejected records
- `.claude/skills/gold-ingestion.md` — Analyse-validate-plan-confirm-implement cycle for Gold tables; KPIs, joins, aggregations, business rules, target grain, dimensions and measures
- `.claude/skills/source-validation.md` — File existence checks, PostgreSQL connectivity, table presence, error patterns and fixes
- `.claude/skills/data-modeling.md` — Star schema, fact/dimension modeling, medallion design decisions
- `.claude/skills/git-versioning.md` — Branch strategy, commit message conventions, safe staging rules
- `.claude/skills/cicd-github-actions.md` — CI workflow patterns for Python + PySpark
- `.claude/skills/sql-server-integration.md` — Legacy: JDBC URL format, driver jar, Windows auth (kept for reference only — SQL Server is no longer the active source)
- `.claude/skills/pipeline-docs.md` — Pipeline doc format (sections per type), when to regenerate, Monitor Pipelines page wiring, last_status tracking
- `.claude/skills/data-explorer.md` — Data Explorer page: `_scan_layer()` pattern, DuckDB registration, cross-layer query examples

---

## Agents Reference

Specialist sub-agents for focused tasks:

- `.claude/agents/bronze-layer-agent.md` — PostgreSQL/file ingestion, BronzeLayer patterns, schema-on-read
- `.claude/agents/silver-layer-agent.md` — Type casting, null safety, schema enforcement, derived columns
- `.claude/agents/gold-layer-agent.md` — Join strategies, aggregations, window functions, business metrics
- `.claude/agents/test-writer-agent.md` — pytest + PySpark test suite architecture
- `.claude/agents/ci-cd-agent.md` — GitHub Actions workflows for this pipeline

---

## Available Slash Commands

| Command | Purpose |
|---|---|
| `/validate-schema [layer]` | Compare actual Parquet schema to expected contracts |
| `/data-quality [layer]` | Run null checks, PK uniqueness, referential integrity, Gold↔Silver reconciliation |
| `/add-table <TableName>` | Scaffold all 3 layers + config for a new source table |
| `/test-layer bronze\|silver\|gold` | Generate and run pytest tests for a layer |
| `/config-audit` | Cross-check every config.get() call against config.yaml keys |
| `/git-checkpoint` | Safe git commit: stages only src/ files, auto-generates commit message |
| `/spark-debug [keyword]` | Parse logs for errors, match to known patterns, suggest fixes |
| `/lineage-report` | Column-level lineage from source through all 3 layers |
| `/incremental-design` | Design watermark-based incremental ingestion |
