# ClaudeDataPipeline — Project Memory

## Project Identity

- **Type**: Python + PySpark ETL pipeline, Medallion Architecture (Bronze → Silver → Gold)
- **Source**: Microsoft SQL Server (`localhost/SalesDB`) — `dbo.Products`, `dbo.Customers`, `dbo.Orders`, `dbo.OrderItems`
- **Output**: Parquet files under `data/<layer>/<table>/`
- **Entry point**: `python src/main.py` (must be run from project root)
- **Config**: `config.yaml` — accessed via `ConfigManager.get('dot.notation.key')`
- **Domain**: Sales data — 10 products across 4 categories, 10 customers, 15 orders, 25 order items

---

## Architecture Map

```
src/
  main.py                     — Entry point: wires SparkSession + all three layer classes
  bronze/ingestion.py         — BronzeLayer: JDBC SQL Server → Parquet (raw, no transforms)
  silver/transformations.py   — SilverLayer: type casting, null filtering, derived columns
  gold/aggregations.py        — GoldLayer: joins + groupBy aggregations (business metrics)
  config/config_manager.py    — ConfigManager: YAML dot-notation access
  utils/logger.py             — PipelineLogger: timestamped file + console handlers
```

### Dependency Injection Pattern

All three layer classes are constructed with `(spark: SparkSession, config: ConfigManager, logger: Logger)`. SparkSession is created ONCE in `main.py` and passed down. Never instantiate SparkSession inside a layer class.

---

## Medallion Layer Contracts

### Bronze — Raw Ingestion
- **Rule**: Faithful copy of source. Zero business logic. Zero renaming.
- **Schema**: Identical to SQL Server source (PascalCase column names, SQL Server types)
- **Write mode**: `overwrite` (full load, idempotent)
- **Output**: `data/bronze/<table_name>/` (single Parquet file via `coalesce(1)`)
- **Source tables → Bronze dirs**: `dbo.Products → products`, `dbo.Customers → customers`, `dbo.Orders → orders`, `dbo.OrderItems → order_items`

### Silver — Validated & Typed
- **Rule**: Clean, typed, snake_case, null-safe DataFrames. Row-level only — no aggregation.
- **Contract**: Every row in Silver has a non-null primary key. Null PK filter is always the last operation.
- **Transforms applied**: PascalCase → snake_case aliases, explicit type casts, `line_total = quantity * unit_price` derivation in `order_items`
- **Write mode**: `overwrite`
- **Output**: `data/silver/<table_name>/`

### Gold — Business Aggregations
- **Rule**: groupBy + agg only. Never modify Silver-level row data. Analysts consume Gold.
- **Join strategy**: Always `left` join from fact table (`order_items`). Never `inner` join.
- **Current Gold tables**:
  - `sales_summary` — flat denormalized view (order_items + products + orders)
  - `daily_sales_by_category` — groupBy(order_date, category) → total_quantity, total_sales
  - `product_performance` — groupBy(product_id, product_name, category) → total_quantity_sold, total_revenue, avg_price (ordered by total_revenue DESC)

---

## Silver Schema Reference

| Table | Key Columns | Derived |
|---|---|---|
| products | product_id int, product_name string, category string, unit_price float | — |
| customers | customer_id int, customer_name string, email string, country string | — |
| orders | order_id int, customer_id int, order_date timestamp | — |
| order_items | order_item_id int, order_id int, product_id int, quantity int, unit_price float | line_total float |

---

## Naming Conventions

- **SQL Server source**: `dbo.PascalCase` (e.g. `dbo.OrderItems`)
- **Bronze output directories**: `snake_case` (e.g. `order_items`)
- **Silver/Gold column names**: `snake_case` (e.g. `product_id`, `order_date`)
- **Layer class methods**: `ingest_from_sql_server()`, `transform_<entity>()`, `create_<metric>()`, `save_<layer>_table()`
- **New tables**: follow `dbo.<PascalSingular>` → `<snake_plural>` pattern

---

## Known Bugs & Gaps (Claude must proactively flag these)

1. **JDBC Auth broken** (`src/bronze/ingestion.py`): `user=""` and `password=""` options are passed to JDBC. For Windows Integrated Auth, the correct approach is `integratedSecurity=true;authenticationScheme=NativeAuthentication` in the JDBC URL itself — not separate user/password options. Fix: update `ingest_from_sql_server()` to build the URL from `config.yaml` with `integratedSecurity=true` and remove the user/password options.

2. **JDBC driver jar not configured**: The `com.microsoft.sqlserver.jdbc.SQLServerDriver` class requires the MSSQL JDBC jar (e.g. `mssql-jdbc-12.4.2.jre11.jar`) to be on the Spark classpath via `.config("spark.jars", "drivers/mssql-jdbc-12.4.2.jre11.jar")`. This is not in `config.yaml` or `main.py`. Fix: add `spark.jdbc_driver_path` to `config.yaml` and wire it in `main.py`.

3. **Unused imports** (`src/silver/transformations.py`): `StructType`, `StructField`, `StringType`, etc. are imported but unused. Schema enforcement via StructType is not implemented. This means Bronze reads with inferred schema — type mismatches will only surface at Silver cast time.

4. **`coalesce(1)` is dev-only**: All writes use `coalesce(1)` which produces a single Parquet file. Fine for this local project; do not carry this to production.

5. **`python-dotenv` not wired**: It's in `requirements.txt` but never imported. Credential management via `.env` is planned but not implemented. When adding JDBC credentials, wire via `load_dotenv()` in `main.py`.

6. **No watermarking / incremental ingestion**: Pipeline does full overwrite on every run. No `last_ingested` state tracked. Use `/incremental-design` command to scaffold this improvement.

7. **Empty `tests/`**: No test coverage exists. Use `/test-layer` command to generate pytest suites.

8. **Logger creates a new file per `get_logger()` call**: If called multiple times in one run, multiple log files are created. Refactor to use a single session log file.

---

## What NOT to Do

- **Never** instantiate `SparkSession` inside `BronzeLayer`, `SilverLayer`, or `GoldLayer`
- **Never** use `inner` join in `GoldLayer` — always `left` to preserve all order_items
- **Never** use `select("*")` in Silver — always explicit column selection with `.alias()`
- **Never** commit `data/`, `logs/`, `.env` — they are gitignored
- **Never** put business logic (aggregations, joins across tables) in Silver
- **Never** put row-level transformations in Gold
- **Never** hardcode connection strings or credentials — always read from `config.yaml` / `.env`
- **Never** use `df.toPandas()` in the pipeline — defeats Spark's execution model
- **Never** use `df.show()` in production code — use `logger.info()`

---

## Dev Runbook

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline (from project root)
python src/main.py

# Validate config.yaml loads correctly
python -c "from src.config.config_manager import ConfigManager; c=ConfigManager(); print(c.get('sql_server.server'), c.get('paths.bronze'))"

# Check Parquet output (example: gold product_performance)
python -c "
from pyspark.sql import SparkSession
spark = SparkSession.builder.master('local').appName('check').getOrCreate()
spark.read.parquet('data/gold/product_performance').show()
spark.stop()
"

# Run tests (once written)
pytest tests/ -v

# Run tests excluding SQL Server integration tests
pytest tests/ -v -m "not integration"

# Syntax check all source files
python -m py_compile src/bronze/ingestion.py src/silver/transformations.py src/gold/aggregations.py src/main.py

# View latest pipeline log
ls -t logs/ | head -1

# Set up SQL Server sample data
# 1. Run sql/create_schema.sql in SSMS
# 2. Run sql/insert_sample_data.sql in SSMS
```

---

## Skills Reference

Claude should consult these domain documents when working on specific tasks:

- `.claude/skills/medallion-architecture.md` — Layer design rules, contracts, when to add new tables
- `.claude/skills/pyspark-patterns.md` — DataFrame idioms, test patterns, anti-patterns
- `.claude/skills/data-quality.md` — DQ checks, null rates, referential integrity, Gold↔Silver reconciliation
- `.claude/skills/sql-server-integration.md` — JDBC URL format, driver jar, Windows auth, common failures
- `.claude/skills/git-versioning.md` — Branch strategy, commit message conventions, safe staging rules
- `.claude/skills/cicd-github-actions.md` — CI workflow patterns for Python + PySpark
- `.claude/skills/data-modeling.md` — Star schema, fact/dimension modeling, medallion design decisions

---

## Agents Reference

Specialist sub-agents for focused tasks:

- `.claude/agents/bronze-layer-agent.md` — JDBC ingestion, SQL Server connectivity, schema-on-read
- `.claude/agents/silver-layer-agent.md` — Type casting, null safety, schema enforcement, derived columns
- `.claude/agents/gold-layer-agent.md` — Join strategies, aggregations, window functions, business metrics
- `.claude/agents/test-writer-agent.md` — pytest + PySpark test suite architecture
- `.claude/agents/ci-cd-agent.md` — GitHub Actions workflows for this pipeline

---

## Available Slash Commands

| Command | Purpose |
|---|---|
| `/run-pipeline [layer]` | Execute full or partial pipeline with pre-flight checks |
| `/validate-schema [layer]` | Compare actual Parquet schema to expected contracts |
| `/data-quality [layer]` | Run null checks, PK uniqueness, referential integrity, Gold↔Silver reconciliation |
| `/add-table <TableName>` | Scaffold all 3 layers + config + main.py for a new source table |
| `/test-layer bronze\|silver\|gold` | Generate and run pytest tests for a layer |
| `/config-audit` | Cross-check every config.get() call against config.yaml keys |
| `/git-checkpoint` | Safe git commit: stages only src/ files, auto-generates commit message |
| `/spark-debug [keyword]` | Parse logs for errors, match to known patterns, suggest fixes |
| `/lineage-report` | Column-level lineage from SQL Server through all 3 layers |
| `/incremental-design` | Design watermark-based incremental ingestion |
