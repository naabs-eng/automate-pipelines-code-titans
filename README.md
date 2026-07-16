# ClaudeDataPipeline

A Python + PySpark ETL pipeline built on the **Medallion Architecture** (Bronze → Silver → Gold), with a Streamlit UI for running pipelines, building Gold aggregations, and querying data — no code required.

## Architecture

```
PostgreSQL  ─┐
             ├─▶  Bronze (raw Parquet)  ─▶  Silver (clean/typed)  ─▶  Gold (aggregations)
File sources ─┘
```

| Layer | What it stores | Location |
|---|---|---|
| Bronze | Faithful copy of source, audit columns added | `data/bronze/<table>_bronze/` |
| Silver | Typed, snake_case, null-safe rows | `data/silver/<table>_silver/` |
| Gold | Business aggregations for analysis | `data/gold/<metric_name>/` |

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.9+ | 3.11 recommended |
| Java | 11+ | Required by PySpark — [Temurin JDK](https://adoptium.net/) recommended |
| PostgreSQL | 13+ | Source database; must be running locally |

**macOS quick install:**
```bash
brew install openjdk@17 postgresql@15
```

**Windows:** Install [Temurin JDK 17](https://adoptium.net/) and [PostgreSQL](https://www.postgresql.org/download/windows/), then ensure `JAVA_HOME` is set in your environment.

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd ClaudeDataPipeline
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:

```env
# PostgreSQL — defaults to your OS username with no password (Mac/Linux trust auth)
PG_USERNAME=your_postgres_username
PG_PASSWORD=your_postgres_password

# Required only for the Gold Agent page (AI-powered analysis)
ANTHROPIC_API_KEY=sk-ant-...
```

### 3a. Set login credentials (required)

The app requires a username and password at startup. These are stored **outside the project directory** as system environment variables — never in `.env` or any committed file.

**macOS / Linux** — add to `~/.zshrc` (or `~/.bashrc`):

```bash
export NF_USERNAME="your_username"
export NF_PASSWORD="your_password"
```

Then reload your shell:

```bash
source ~/.zshrc
```

**Windows** — set via System Properties → Environment Variables, or in PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable("NF_USERNAME", "your_username", "User")
[System.Environment]::SetEnvironmentVariable("NF_PASSWORD", "your_password", "User")
```

> If `NF_USERNAME` or `NF_PASSWORD` are not set, the login form will reject all credentials.

### 4. Verify config.yaml

Open `config.yaml` and confirm the PostgreSQL connection matches your local setup:

```yaml
postgresql:
  host: localhost
  port: 5432
  database: postgres
```

Change these if your PostgreSQL runs on a different host, port, or database name.

### 5. Set up your PostgreSQL source tables

Create the tables your pipelines will ingest from and populate them with data. The default pipelines expect:

- `pg_customers` — customer records
- `pg_employees` — employee records

Add your data directly in PostgreSQL using `psql` or any PostgreSQL client.

### 6. Add source files (optional)

Place CSV or JSON source files in `data/sources/`. The pipelines reference them by filename (e.g. `transactions.json`, `leave_logs.csv`).

### 7. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Using the App

### Bronze & Silver
Run ingestion for any configured pipeline. Reads from PostgreSQL and/or file sources, writes raw Parquet to `data/bronze/`, then transforms and cleans to `data/silver/`.

### Gold Builder
Design Gold aggregation tables interactively. Select Silver tables, choose dimensions and measures, and the app generates and runs the PySpark aggregation.

### Monitor Pipelines
View run history, schedules, and last status for all pipelines defined in `config.yaml`.

### Gold Agent *(requires `ANTHROPIC_API_KEY`)*
Ask questions about your Gold data in plain English. The agent generates and runs PySpark queries and returns results with explanations.

### Data Explorer
Browse Bronze, Silver, and Gold tables. Inspect schemas, preview rows, view file metadata, and run cross-layer SQL queries via DuckDB — no Spark startup required.

---

## Adding a New Pipeline

1. Add a new entry under `pipelines:` in `config.yaml`:

```yaml
- name: pl_my_domain_description_bronze_silver
  schedule: daily
  schedule_config:
    type: Daily
    time: "09:00"
  sources:
  - source_type: postgresql
    mode: full
    tables:
      - my_pg_table
  - source_type: file
    mode: full
    tables:
      - my_file.csv
```

2. Run the pipeline from the **Bronze & Silver** page.

3. The **Active Pipelines** section in `CLAUDE.md` updates automatically on save (via the `post_yaml_validate` hook).

---

## Project Structure

```
app.py                    — Streamlit router + theme
pages/
  2_Bronze_Silver.py      — Ingestion UI
  3_Gold_Builder.py       — Gold table builder
  4_Monitor_Pipelines.py  — Pipeline monitor
  5_Gold_Agent.py         — AI query agent
  6_Data_Explorer.py      — Data browser + DuckDB SQL

src/
  run_bronze.py           — Bronze ingestion CLI (called by UI)
  run_silver_gold.py      — Silver/Gold pipeline CLI (called by UI)
  analyse_gold.py         — Gold analysis (called by Gold Builder)
  gold_agent.py           — AI agent logic (called by Gold Agent)
  pipeline_docs.py        — Pipeline doc generator
  bronze/ingestion.py     — BronzeLayer: PostgreSQL + file → Parquet
  config/config_manager.py
  utils/logger.py
  utils/db_validator.py

drivers/
  postgresql-42.7.13.jar  — PostgreSQL JDBC driver (included)

data/
  bronze/                 — Raw Parquet output
  silver/                 — Cleaned Parquet output
  gold/                   — Aggregated Parquet output
  sources/                — Input CSV/JSON files

sql/
  create_schema.sql       — Legacy SQL Server DDL (reference only)
  insert_sample_data.sql  — Legacy SQL Server sample data (reference only)

config.yaml               — All pipeline and connection config
.env                      — Credentials (not committed)
```

---

## Troubleshooting

**PySpark fails to start**
Ensure Java 11+ is installed and `JAVA_HOME` is set:
```bash
java -version     # should print 11 or higher
echo $JAVA_HOME   # should point to JDK root
```

**PostgreSQL connection refused**
Confirm PostgreSQL is running and credentials in `.env` match your setup:
```bash
psql -U $PG_USERNAME -d postgres -c "SELECT 1"
```

**`ModuleNotFoundError` on import**
Run from the project root, not from inside `src/`:
```bash
cd ClaudeDataPipeline
streamlit run app.py
```

**Login always fails / "Invalid credentials"**
Ensure `NF_USERNAME` and `NF_PASSWORD` are set as system environment variables (not in `.env`). Restart your terminal and re-run `streamlit run app.py` after setting them.

**Gold Agent returns no API key error**
Set `ANTHROPIC_API_KEY` in your `.env` file, or enter it directly in the Gold Agent page sidebar.
