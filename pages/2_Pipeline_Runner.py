import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.config_manager import ConfigManager
from utils.db_validator import validate_tables

st.set_page_config(page_title="Pipeline Runner", page_icon="▶️", layout="wide")
st.title("Pipeline Runner")
st.caption("Validate tables → Bronze → Silver → Gold in one run")

config = ConfigManager()

# ── Step 1: Select Source ──────────────────────────────────────────────────────
st.subheader("Step 1 — Select Source")

source_label = st.selectbox("Source", ["PostgreSQL", "SQL Server"])
source_type = "postgresql" if source_label == "PostgreSQL" else "sqlserver"

if source_type == "postgresql":
    host = config.get("postgresql.host", "localhost")
    port = int(config.get("postgresql.port", 5432))
    database = config.get("postgresql.database", "")
    username = os.environ.get("PG_USERNAME", "")
    password = os.environ.get("PG_PASSWORD", "")
    st.info(f"Connected to: `{host}:{port}/{database}`")
else:
    host = config.get("sql_server.server", "")
    port = 1433
    database = config.get("sql_server.database", "")
    username = ""
    password = ""
    st.info(f"Connected to: `{host}` / `{database}`")

st.divider()

# ── Step 2: Enter & Validate Tables ───────────────────────────────────────────
st.subheader("Step 2 — Enter & Validate Tables")

placeholder = "public.suppliers\npublic.inventory\npublic.shipments" if source_type == "postgresql" else "dbo.Products\ndbo.Orders"
table_input = st.text_area(
    "Enter table names (one per line, with schema prefix)",
    placeholder=placeholder,
    height=150
)

if "validation_results" not in st.session_state:
    st.session_state.validation_results = {}
if "validated_tables" not in st.session_state:
    st.session_state.validated_tables = []

if st.button("Validate Tables", type="secondary"):
    raw = [t.strip() for t in table_input.strip().splitlines() if t.strip()]
    if not raw:
        st.warning("Please enter at least one table name.")
    else:
        with st.spinner(f"Checking {len(raw)} table(s) in {source_label}..."):
            results, err = validate_tables(source_type, host, port, database, username, password, raw)
        st.session_state.validation_results = results
        st.session_state.validated_tables = raw
        if err:
            st.error(f"Validation error: {err}")

if st.session_state.validation_results:
    results = st.session_state.validation_results
    all_valid = all(results.values())
    for table, found in results.items():
        if found:
            st.success(f"✅ `{table}` — found")
        else:
            st.error(f"❌ `{table}` — not found in {source_label}, please check the name")
    if not all_valid:
        st.warning("Fix the table names above and re-validate before running.")

st.divider()

# ── Step 3: Confirm & Run End-to-End ──────────────────────────────────────────
st.subheader("Step 3 — Confirm & Run Full Pipeline")

results = st.session_state.validation_results
all_valid = bool(results) and all(results.values())
valid_tables = [t for t, ok in results.items() if ok]

if not all_valid:
    st.info("Complete Step 2 validation before running.")
else:
    st.markdown(f"**Will run:** Bronze → Silver → Gold for {len(valid_tables)} table(s)")
    for t in valid_tables:
        st.markdown(f"- `{t}`")

    confirmed = st.checkbox(
        f"I confirm: run full pipeline for the {len(valid_tables)} table(s) above"
    )

    run_btn = st.button("▶ Run Full Pipeline", type="primary", disabled=not confirmed)

    if run_btn and confirmed:
        tables_arg = ",".join(valid_tables)
        bronze_tables_arg = ",".join(t.split(".")[-1] for t in valid_tables)

        bronze_cmd = [
            sys.executable,
            str(Path(__file__).parent.parent / "src" / "run_bronze.py"),
            "--source", source_type,
            "--tables", tables_arg,
        ]
        silver_gold_cmd = [
            sys.executable,
            str(Path(__file__).parent.parent / "src" / "run_silver_gold.py"),
            "--tables", bronze_tables_arg,
        ]

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        def stream_subprocess(cmd, label, log_lines, log_box, status_map, layer):
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, env=env)
            while True:
                line = proc.stdout.readline()
                if line == "" and proc.poll() is not None:
                    break
                if line:
                    line = line.rstrip()
                    log_lines.append(line)
                    log_box.code("\n".join(log_lines[-50:]), language="text")
                    for t in valid_tables:
                        tname = t.split(".")[-1]
                        if f"SUCCESS: {t}" in line or f"-> data/bronze/{tname}" in line:
                            status_map[tname]["bronze"] = "✅"
                        elif f"FAILED: {t}" in line:
                            status_map[tname]["bronze"] = "❌"
                        elif f"Ingesting {t}" in line:
                            status_map[tname]["bronze"] = "⏳"
                        if f"[Silver] SUCCESS: {tname}" in line:
                            status_map[tname]["silver"] = "✅"
                        elif f"[Silver] Processing {tname}" in line:
                            status_map[tname]["silver"] = "⏳"
                        if f"[Gold] SUCCESS: {tname}" in line:
                            status_map[tname]["gold"] = "✅"
                        elif f"[Gold] Processing {tname}" in line:
                            status_map[tname]["gold"] = "⏳"
                        elif f"[Gold] Skipping {tname}" in line:
                            status_map[tname]["gold"] = "⏭ Skipped"

                    rows = ["| Table | Bronze | Silver | Gold |", "|---|---|---|---|"]
                    for tname, s in status_map.items():
                        rows.append(f"| `{tname}` | {s['bronze']} | {s['silver']} | {s['gold']} |")
                    status_box.markdown("\n".join(rows))

            return proc.returncode

        st.subheader("Live Logs")
        log_box = st.empty()
        status_box = st.empty()

        status_map = {
            t.split(".")[-1]: {"bronze": "⏳ Pending", "silver": "–", "gold": "–"}
            for t in valid_tables
        }

        log_lines = []

        log_lines.append("=== BRONZE INGESTION ===")
        log_box.code("\n".join(log_lines), language="text")
        bronze_exit = stream_subprocess(bronze_cmd, "Bronze", log_lines, log_box, status_map, "bronze")

        if bronze_exit != 0:
            st.error("Bronze ingestion failed. Silver/Gold skipped.")
        else:
            log_lines.append("\n=== SILVER + GOLD TRANSFORMS ===")
            log_box.code("\n".join(log_lines), language="text")
            sg_exit = stream_subprocess(silver_gold_cmd, "Silver/Gold", log_lines, log_box, status_map, "silver_gold")

            if sg_exit == 0:
                st.success("Full pipeline completed: Bronze → Silver → Gold")

                # Save new tables to config
                config.reload()
                existing_key = "tables.pg_source" if source_type == "postgresql" else "tables.source"
                existing = config.get(existing_key, [])
                existing_bronze_names = {t["bronze_table"] for t in existing}
                added = []
                for t in valid_tables:
                    bronze_name = t.split(".")[-1]
                    if bronze_name not in existing_bronze_names:
                        existing.append({"name": t, "bronze_table": bronze_name})
                        added.append(t)
                        existing_bronze_names.add(bronze_name)
                if added:
                    config.set(existing_key, existing)
                    config.save()
                    st.info(f"Added {len(added)} new table(s) to config.yaml: {', '.join(added)}")

                st.session_state.validation_results = {}
                st.session_state.validated_tables = []
            else:
                st.error("Silver/Gold transforms finished with errors. Check logs above.")
