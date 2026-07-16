---
name: Source Validation
description: Use when validating any configured source before ingestion — covers file existence checks, PostgreSQL connectivity, table presence, and reporting patterns.
---

# Source Validation — ClaudeDataPipeline

## Purpose

Validate that all sources referenced in `config.yaml` are reachable before running a pipeline. Fail fast with clear diagnostics rather than discovering issues mid-run.

---

## File Source Validation

```python
from pathlib import Path
import sys

base_dir = Path(config.get("file_sources.base_dir", "./data/sources"))
file_sources = config.get("tables.file_source", []) or []

# 1. Check base directory
if not base_dir.exists() or not base_dir.is_dir():
    print(f"❌ Base directory not found: {base_dir}")
    sys.exit(1)

# 2. Check each registered file
for src in file_sources:
    fpath = Path(src.get("path", ""))
    if not fpath.is_absolute():
        fpath = base_dir / fpath.name
    exists = fpath.exists()
    size   = f"  ({fpath.stat().st_size:,} bytes)" if exists else ""
    icon   = "✅" if exists else "❌"
    print(f"{icon} {src['bronze_table']:<20} {fpath}{size}")
```

**Common failures:**
| Symptom | Cause | Fix |
|---|---|---|
| Base dir not found | `file_sources.base_dir` wrong | Update path in `config.yaml` |
| File not found | `path` key has wrong name/location | Check `tables.file_source[].path` |
| File found but empty | Source wrote zero rows | Re-generate source file |

---

## PostgreSQL Source Validation

```python
import getpass, os, psycopg2

host = config.get("postgresql.host", "localhost")
port = int(config.get("postgresql.port", 5432))
db   = config.get("postgresql.database", "")
user = os.environ.get("PG_USERNAME") or getpass.getuser()
pw   = os.environ.get("PG_PASSWORD", "")

# 1. Test connection
try:
    conn = psycopg2.connect(host=host, port=port, dbname=db,
                            user=user, password=pw, connect_timeout=5)
    print(f"✅ Connected to {host}:{port}/{db}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

# 2. Check each registered table
cur = conn.cursor()
for src in config.get("tables.pg_source", []) or []:
    table_full = src.get("name", "")
    schema, tname = ("public", table_full) if "." not in table_full else table_full.split(".", 1)
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, tname),
    )
    found = cur.fetchone() is not None
    if found:
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{tname}"')
        rows = cur.fetchone()[0]
        print(f"✅ {src['bronze_table']:<20} {table_full}  ({rows:,} rows)")
    else:
        print(f"❌ {src['bronze_table']:<20} {table_full}  — not found")

cur.close()
conn.close()
```

**Common failures:**
| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: no PostgreSQL user name specified` | `user=""` passed to JDBC/psycopg2 | Use `os.environ.get("PG_USERNAME") or getpass.getuser()` |
| `could not connect to server` | PostgreSQL not running, wrong host/port | Check `postgresql.host`/`port` in `config.yaml` |
| `database "salesdb" does not exist` | Wrong `database` in config | Run `SELECT datname FROM pg_database` to list available databases |
| Table not found | Wrong schema prefix or table in a different DB | Verify with `\dt` in psql; check `database` setting |
| Auth failure | Wrong credentials in `.env` | Update `PG_USERNAME`/`PG_PASSWORD` in `.env` |

---

## Validation Report Format

Always print a summary at the end:

```
============================================================
SUMMARY: 5/6 passed  ⚠ 1 issue needs attention
============================================================

Failed items:
  ❌ shipments: public.shipments — not found
```

Exit code: `0` if all pass, `1` if any fail. This lets CI/CD detect failures.

---

## Per-Source-Block Validation (Pipeline Runner)

When validating inside a Streamlit source block, use `psycopg2` directly (not Spark) for speed:

```python
import psycopg2
conn = psycopg2.connect(host=host, port=port, dbname=database,
                        user=username, password=password, connect_timeout=5)
cur = conn.cursor()
for table in tables:
    schema, tname = ("public", table) if "." not in table else table.split(".", 1)
    cur.execute("SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name=%s", (schema, tname))
    found = cur.fetchone() is not None
    # store in st.session_state[f"src_val_{src_id}"]
```

For file sources, use `Path(base_dir / filename).exists()` — no Spark needed.

---

## Pre-Flight Checks Before Pipeline Run

Before triggering Bronze ingestion, validate:
1. All file base directories exist
2. All registered files exist  
3. PostgreSQL is reachable
4. All registered tables exist in the target database
5. Bronze output directory (`data/bronze/`) is writable

Only skip validation if the user explicitly bypasses it — fail-fast saves debug time.
