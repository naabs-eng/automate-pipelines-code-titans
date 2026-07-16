import os
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from config.config_manager import ConfigManager
from pipeline_docs import bronze_silver_doc, save_pipeline_doc
from utils.db_validator import validate_tables

st.title("🔄 Bronze & Silver Pipeline")
st.caption(
    "Ingest raw data from PostgreSQL or files → **Bronze** (raw Parquet) → **Silver** "
    "(typed, snake_case, null-safe). After success, go to **Gold Builder** to build "
    "business aggregations."
)

config = ConfigManager()

# ── Session state bootstrap ────────────────────────────────────────────────────
if "pipeline_source_ids" not in st.session_state:
    st.session_state.pipeline_source_ids = ["src_1"]
    st.session_state.source_counter = 1
if "pipeline_validation" not in st.session_state:
    st.session_state.pipeline_validation = {}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _pg_conn():
    import getpass
    return {
        "host": config.get("postgresql.host", "localhost"),
        "port": int(config.get("postgresql.port", 5432)),
        "database": config.get("postgresql.database", ""),
        "username": os.environ.get("PG_USERNAME") or getpass.getuser(),
        "password": os.environ.get("PG_PASSWORD", ""),
    }


def _get_source_conn(src_id):
    base = _pg_conn()
    if st.session_state.get(f"pg_override_{src_id}"):
        return {
            **base,
            "host": st.session_state.get(f"pg_host_{src_id}") or base["host"],
            "port": int(
                st.session_state.get(f"pg_port_{src_id}") or base["port"]
            ),
            "database": st.session_state.get(f"pg_db_{src_id}") or base["database"],
            "username": st.session_state.get(f"pg_user_{src_id}") or base["username"],
            "password": st.session_state.get(f"pg_pass_{src_id}", base["password"]),
            "is_override": True,
        }
    return {**base, "is_override": False}


def _bronze_name(table, stype):
    stem = Path(table).stem if stype == "file" else table.split(".")[-1]
    return f"{stem}_bronze"


def _silver_name(bronze_name):
    if bronze_name.endswith("_bronze"):
        return bronze_name[:-7] + "_silver"
    return bronze_name + "_silver"


def _file_path(filename, base_dir=None):
    base = base_dir or config.get("file_sources.base_dir", "./data/sources")
    p = Path(base)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return str(p / filename)


# ── Saved Pipelines ───────────────────────────────────────────────────────────
saved = [
    p for p in (config.get("pipelines", []) or [])
    if str(p.get("name", "")).endswith("_bronze_silver")
]
if saved:
    with st.expander(f"Saved Bronze & Silver Pipelines ({len(saved)})", expanded=False):
        for i, p in enumerate(saved):
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{p.get('name', 'Unnamed')}**")
                src_summary = ", ".join(
                    f"{s['source_type']}({len(s.get('tables', []))} tables)"
                    for s in p.get("sources", [])
                )
                st.caption(
                    f"Sources: {src_summary} | Schedule: {p.get('schedule', 'run_once')}"
                )
            with c2:
                if p.get("last_run"):
                    st.caption(f"Last run: {p['last_run'][:16]}")
            with c3:
                if st.button("Re-run", key=f"bs_rerun_{i}"):
                    srcs = p.get("sources", [])
                    ids = []
                    st.session_state.source_counter = len(srcs)
                    for j, s in enumerate(srcs):
                        sid = f"src_{j + 1}"
                        ids.append(sid)
                        st.session_state[f"stype_{sid}"] = (
                            "PostgreSQL"
                            if s["source_type"] == "postgresql"
                            else "File / CSV / JSON"
                        )
                        st.session_state[f"tables_{sid}"] = "\n".join(
                            s.get("tables", [])
                        )
                        st.session_state[f"mode_{sid}"] = "Full Load"
                    st.session_state.pipeline_source_ids = ids
                    raw_base = p.get("name", "").removesuffix("_bronze_silver")
                    st.session_state["bs_pipeline_name_input"] = raw_base
                    st.rerun()
    st.divider()

# ── 1. Pipeline Name ───────────────────────────────────────────────────────────
st.subheader("1 — Pipeline Name")
bs_name_raw = st.text_input(
    "Name *",
    key="bs_pipeline_name_input",
    placeholder="e.g. daily_sales",
    help="Required. Your pipeline will be saved as `<name>_bronze_silver`.",
)
if bs_name_raw:
    bs_pipeline_name = f"{bs_name_raw.strip()}_bronze_silver"
    st.caption(f"Pipeline name: **`{bs_pipeline_name}`**")
else:
    bs_pipeline_name = None
    st.caption(
        "Enter a name above. The pipeline will be saved as `<name>_bronze_silver`."
    )

st.divider()

# ── 2. Sources ─────────────────────────────────────────────────────────────────
st.subheader("2 — Sources")
st.caption("Add one or more sources. Each source can pull from PostgreSQL or flat files.")

for src_id in list(st.session_state.pipeline_source_ids):
    idx = st.session_state.pipeline_source_ids.index(src_id) + 1
    stype_val = st.session_state.get(f"stype_{src_id}", "PostgreSQL")
    with st.expander(f"Source {idx} — {stype_val}", expanded=True):
        col_l, col_r = st.columns([4, 1])

        with col_l:
            stype = st.selectbox(
                "Source Type",
                ["PostgreSQL", "File / CSV / JSON"],
                key=f"stype_{src_id}",
            )

            if stype == "PostgreSQL":
                use_override = st.checkbox(
                    "Connect to a different database",
                    key=f"pg_override_{src_id}",
                    help="Override host / port / database for this source only",
                )
                if use_override:
                    base = _pg_conn()
                    ov1, ov2, ov3 = st.columns(3)
                    with ov1:
                        st.text_input(
                            "Host", key=f"pg_host_{src_id}",
                            value=st.session_state.get(f"pg_host_{src_id}") or base["host"],
                        )
                    with ov2:
                        st.number_input(
                            "Port", key=f"pg_port_{src_id}",
                            value=int(
                                st.session_state.get(f"pg_port_{src_id}") or base["port"]
                            ),
                            step=1, min_value=1, max_value=65535,
                        )
                    with ov3:
                        st.text_input(
                            "Database", key=f"pg_db_{src_id}",
                            value=st.session_state.get(f"pg_db_{src_id}") or "",
                        )
                    ov4, ov5 = st.columns(2)
                    with ov4:
                        st.text_input(
                            "Username", key=f"pg_user_{src_id}",
                            value=st.session_state.get(f"pg_user_{src_id}") or "",
                            placeholder=_pg_conn()["username"],
                        )
                    with ov5:
                        st.text_input(
                            "Password", key=f"pg_pass_{src_id}", type="password"
                        )

                eff = _get_source_conn(src_id)
                conn_label = "Override" if eff["is_override"] else "Using"
                st.caption(
                    f"{conn_label}: `{eff['host']}:{eff['port']}/{eff['database']}`"
                )

                st.text_area(
                    "Tables (one per line, with schema prefix)",
                    placeholder="public.ec_categories\npublic.suppliers",
                    key=f"tables_{src_id}",
                    height=100,
                )

                vbc, vmc = st.columns([1, 4])
                with vbc:
                    if st.button("Validate", key=f"val_{src_id}", type="secondary"):
                        eff_c = _get_source_conn(src_id)
                        raw_tbls = st.session_state.get(f"tables_{src_id}", "")
                        tbls = [
                            t.strip()
                            for t in raw_tbls.strip().splitlines()
                            if t.strip()
                        ]
                        try:
                            import psycopg2
                            pg_conn = psycopg2.connect(
                                host=eff_c["host"], port=eff_c["port"],
                                dbname=eff_c["database"],
                                user=eff_c["username"], password=eff_c["password"],
                                connect_timeout=5, gssencmode='disable',
                            )
                            cur = pg_conn.cursor()
                            tbl_results = {}
                            for tbl in tbls:
                                _p = tbl.split(".", 1)
                                schema, tname = (
                                    (_p[0].strip(), _p[1].strip())
                                    if len(_p) == 2
                                    else ("public", tbl.strip())
                                )
                                cur.execute(
                                    "SELECT 1 FROM information_schema.tables "
                                    "WHERE table_schema=%s AND table_name=%s",
                                    (schema, tname),
                                )
                                tbl_results[tbl] = cur.fetchone() is not None
                            cur.close()
                            pg_conn.close()
                            st.session_state[f"src_val_{src_id}"] = {
                                "ok": True, "error": "", "tables": tbl_results,
                            }
                        except Exception as exc:
                            st.session_state[f"src_val_{src_id}"] = {
                                "ok": False, "error": str(exc), "tables": {},
                            }
                src_val = st.session_state.get(f"src_val_{src_id}")
                with vmc:
                    if src_val:
                        if src_val["ok"]:
                            n_found = sum(v for v in src_val["tables"].values())
                            n_total = len(src_val["tables"])
                            st.caption(
                                f"✅ Connected — {n_found}/{n_total} table(s) found"
                            )
                        else:
                            st.caption(f"❌ {src_val['error'][:120]}")
                if src_val and src_val.get("tables"):
                    for tbl, found in src_val["tables"].items():
                        st.caption(f"{'  ✅' if found else '  ❌'} `{tbl}`")

            else:
                default_base = config.get("file_sources.base_dir", "./data/sources")
                file_base_val = st.text_input(
                    "Base Directory",
                    key=f"file_base_{src_id}",
                    value=st.session_state.get(f"file_base_{src_id}") or default_base,
                    help="Files are resolved relative to this path.",
                )
                if file_base_val:
                    bp = Path(file_base_val)
                    if not bp.is_absolute():
                        bp = _PROJECT_ROOT / bp
                    if bp.exists() and bp.is_dir():
                        st.caption("✅ Directory found")
                    else:
                        st.caption(f"❌ Directory not found: `{file_base_val}`")

                st.text_area(
                    "Filenames (one per line, with extension)",
                    placeholder="employees.csv\ntransactions.json",
                    key=f"tables_{src_id}",
                    height=90,
                )
                raw_fnames = st.session_state.get(f"tables_{src_id}", "")
                fnames = [
                    f.strip()
                    for f in raw_fnames.strip().splitlines()
                    if f.strip()
                ]
                if fnames and file_base_val:
                    bp = Path(file_base_val)
                    if not bp.is_absolute():
                        bp = _PROJECT_ROOT / bp
                    for fn in fnames:
                        fpath = bp / fn
                        if fpath.exists():
                            st.caption(f"  ✅ `{fn}`")
                        elif bp.exists():
                            st.caption(f"  ❌ `{fn}` — not found in `{file_base_val}`")
                        else:
                            st.caption(f"  ⚠ `{fn}` — base directory not found")

            mode = st.radio(
                "Load Mode",
                ["Full Load", "Incremental"],
                key=f"mode_{src_id}",
                horizontal=True,
            )
            if stype == "PostgreSQL" and mode == "Incremental":
                st.text_input(
                    "Watermark Column (optional)",
                    placeholder="e.g. created_at",
                    key=f"wm_{src_id}",
                )

        with col_r:
            st.write("")
            st.write("")
            if len(st.session_state.pipeline_source_ids) > 1:
                if st.button("Remove", key=f"remove_{src_id}", type="secondary"):
                    st.session_state.pipeline_source_ids.remove(src_id)
                    keys_to_clear = [
                        f"stype_{src_id}", f"tables_{src_id}", f"mode_{src_id}",
                        f"wm_{src_id}", f"pg_override_{src_id}",
                        f"pg_host_{src_id}", f"pg_port_{src_id}",
                        f"pg_db_{src_id}", f"pg_user_{src_id}", f"pg_pass_{src_id}",
                        f"file_base_{src_id}", f"src_val_{src_id}",
                    ]
                    for k in keys_to_clear:
                        st.session_state.pop(k, None)
                    st.session_state.pipeline_validation.pop(src_id, None)
                    st.rerun()

if st.button("+ Add Source", type="secondary"):
    st.session_state.source_counter += 1
    st.session_state.pipeline_source_ids.append(
        f"src_{st.session_state.source_counter}"
    )
    st.rerun()

st.divider()

# ── 3. Schedule ────────────────────────────────────────────────────────────────
st.subheader("3 — Schedule")

bs_schedule_type = st.selectbox(
    "Run Schedule",
    ["Run Once", "Hourly", "Daily", "Weekly", "Custom Cron"],
    key="bs_schedule_type",
)
bs_schedule_config = {"type": bs_schedule_type}

if bs_schedule_type == "Daily":
    bs_rt = st.time_input("Run at", value=time(8, 0), key="bs_run_time_d")
    bs_schedule_config["time"] = bs_rt.strftime("%H:%M")
    st.caption(f"Cron: `{bs_rt.minute} {bs_rt.hour} * * *`")
elif bs_schedule_type == "Weekly":
    wc1, wc2 = st.columns(2)
    with wc1:
        bs_day = st.selectbox(
            "Day",
            ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"],
            key="bs_weekly_day",
        )
    with wc2:
        bs_rt = st.time_input("Run at", value=time(8, 0), key="bs_run_time_w")
    day_num = ["Monday", "Tuesday", "Wednesday", "Thursday",
               "Friday", "Saturday", "Sunday"].index(bs_day)
    bs_schedule_config["day"] = bs_day
    bs_schedule_config["time"] = bs_rt.strftime("%H:%M")
    st.caption(f"Cron: `{bs_rt.minute} {bs_rt.hour} * * {day_num}`")
elif bs_schedule_type == "Hourly":
    st.caption("Cron: `0 * * * *`")
    bs_schedule_config["cron"] = "0 * * * *"
elif bs_schedule_type == "Custom Cron":
    bs_cron = st.text_input(
        "Cron Expression", placeholder="0 8 * * 1-5", key="bs_cron_expr",
        help="minute  hour  day-of-month  month  day-of-week",
    )
    bs_schedule_config["cron"] = bs_cron
    if bs_cron:
        st.caption(f"Expression: `{bs_cron}`")

st.divider()

# ── 4. Validate All Sources ────────────────────────────────────────────────────
st.subheader("4 — Validate All Sources")

if st.button("Validate All Sources", type="secondary", key="bs_validate_all"):
    st.session_state.pipeline_validation = {}
    for src_id in st.session_state.pipeline_source_ids:
        stype = st.session_state.get(f"stype_{src_id}", "PostgreSQL")
        tables_raw = st.session_state.get(f"tables_{src_id}", "")
        tables = [t.strip() for t in tables_raw.strip().splitlines() if t.strip()]
        if not tables:
            st.session_state.pipeline_validation[src_id] = {}
            continue
        if stype == "PostgreSQL":
            conn = _get_source_conn(src_id)
            results, _ = validate_tables(
                "postgresql", conn["host"], conn["port"], conn["database"],
                conn["username"], conn["password"], tables,
            )
        else:
            base_dir = (
                st.session_state.get(f"file_base_{src_id}")
                or config.get("file_sources.base_dir", "./data/sources")
            )
            results, _ = validate_tables("file", base_dir, 0, "", "", "", tables)
        st.session_state.pipeline_validation[src_id] = results

if st.session_state.pipeline_validation:
    for src_id, results in st.session_state.pipeline_validation.items():
        if not results:
            continue
        idx = st.session_state.pipeline_source_ids.index(src_id) + 1
        stype = st.session_state.get(f"stype_{src_id}", "PostgreSQL")
        with st.expander(f"Source {idx} — {stype}", expanded=True):
            for table, found in results.items():
                if found:
                    st.success(f"✅ `{table}`")
                else:
                    st.error(f"❌ `{table}` — not found")

st.divider()

# ── 5. Run ─────────────────────────────────────────────────────────────────────
st.subheader("5 — Run")

# Collect valid tables across all sources
all_sources = []
total_tables = 0

for src_id in st.session_state.pipeline_source_ids:
    stype = st.session_state.get(f"stype_{src_id}", "PostgreSQL")
    tables_raw = st.session_state.get(f"tables_{src_id}", "")
    mode = st.session_state.get(f"mode_{src_id}", "Full Load")
    wm = st.session_state.get(f"wm_{src_id}", "")
    tables = [t.strip() for t in tables_raw.strip().splitlines() if t.strip()]
    validation = st.session_state.pipeline_validation.get(src_id, {})
    valid_tables = [t for t in tables if validation.get(t, False)]

    conn = _get_source_conn(src_id) if stype == "PostgreSQL" else {}
    file_base = (
        st.session_state.get(f"file_base_{src_id}")
        if stype == "File / CSV / JSON"
        else None
    )
    all_sources.append({
        "id": src_id,
        "source_type": stype,
        "tables": valid_tables,
        "mode": mode,
        "watermark_col": wm,
        "pg_host": conn.get("host"),
        "pg_port": conn.get("port"),
        "pg_database": conn.get("database"),
        "pg_is_override": conn.get("is_override", False),
        "pg_username": conn.get("username"),
        "pg_password": conn.get("password", ""),
        "file_base": file_base,
    })
    total_tables += len(valid_tables)

if not bs_pipeline_name:
    st.warning("Enter a pipeline name in Step 1 before running.")
elif not st.session_state.pipeline_validation:
    st.info("Run validation in Step 4 before executing the pipeline.")
elif total_tables == 0:
    st.warning("No valid tables found. Fix validation errors above.")
else:
    n_src = len([s for s in all_sources if s["tables"]])
    src_lines = "\n".join(
        f"- **{s['source_type']}**: "
        + ", ".join(f"`{t}`" for t in s["tables"])
        + f" ({s['mode']})"
        for s in all_sources
        if s["tables"]
    )
    st.markdown(
        f"Bronze → Silver for **{total_tables} table(s)** across **{n_src} source(s)** "
        f"| Pipeline: `{bs_pipeline_name}` | Schedule: **{bs_schedule_type}**\n\n{src_lines}"
    )

    confirmed_bs = st.checkbox(
        f"Confirm: run Bronze + Silver for {total_tables} table(s)",
        key="confirm_bs",
    )
    bs_btn = st.button(
        "▶ Run Bronze + Silver", type="primary", disabled=not confirmed_bs
    )

    if bs_btn and confirmed_bs:
        st.session_state.pop("bs_done_tables", None)

        run_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        status_box = st.empty()
        log_box = st.empty()
        log_lines = []

        status_map = {}
        for s in all_sources:
            for t in s["tables"]:
                src_type = (
                    "file" if s["source_type"] == "File / CSV / JSON" else "postgresql"
                )
                bn = _bronze_name(t, src_type)
                status_map[bn] = {
                    "source": s["source_type"].replace(" / CSV / JSON", ""),
                    "bronze": "⏳",
                    "silver": "–",
                }

        def _render_status():
            rows = ["| Table | Source | Bronze | Silver |", "|---|---|---|---|"]
            for bn_key, sv in status_map.items():
                sn = _silver_name(bn_key)
                rows.append(
                    f"| `{bn_key}` → `{sn}` | {sv['source']} "
                    f"| {sv['bronze']} | {sv['silver']} |"
                )
            status_box.markdown("\n".join(rows))

        def _stream(cmd, extra_env=None):
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**run_env, **(extra_env or {})},
            )
            while True:
                line = proc.stdout.readline()
                if line == "" and proc.poll() is not None:
                    break
                if line:
                    line = line.rstrip()
                    log_lines.append(line)
                    log_box.code("\n".join(log_lines[-60:]), language="text")
                    for bn_key in status_map:
                        sn_key = _silver_name(bn_key)
                        if (
                            f"-> data/bronze/{bn_key}" in line
                            or ("SUCCESS: " in line and bn_key in line)
                        ):
                            status_map[bn_key]["bronze"] = "✅"
                        elif "FAILED:" in line and bn_key in line:
                            status_map[bn_key]["bronze"] = "❌"
                        if f"[Silver] SUCCESS: {sn_key}" in line:
                            status_map[bn_key]["silver"] = "✅"
                        elif f"[Silver] Processing {bn_key}" in line:
                            status_map[bn_key]["silver"] = "⏳"
                    _render_status()
            return proc.returncode

        _render_status()
        run_failed = False
        all_bronze_names = []

        for s in all_sources:
            if not s["tables"]:
                continue
            src_type = (
                "file" if s["source_type"] == "File / CSV / JSON" else "postgresql"
            )
            tables_arg = ",".join(
                _file_path(t, s.get("file_base")) if src_type == "file" else t
                for t in s["tables"]
            )
            mode_arg = "full" if s["mode"] == "Full Load" else "incremental"

            bronze_cmd = [
                sys.executable,
                str(_PROJECT_ROOT / "src" / "run_bronze.py"),
                "--source", src_type,
                "--tables", tables_arg,
                "--mode", mode_arg,
            ]
            if s["watermark_col"] and src_type == "postgresql":
                bronze_cmd.extend(["--watermark-col", s["watermark_col"]])
            if src_type == "postgresql" and s["pg_is_override"]:
                bronze_cmd.extend([
                    "--pg-host", s["pg_host"],
                    "--pg-port", str(s["pg_port"]),
                    "--pg-database", s["pg_database"],
                ])

            src_extra_env = {}
            if src_type == "postgresql" and s["pg_is_override"] and s.get("pg_username"):
                src_extra_env["PG_USERNAME"] = s["pg_username"]
                src_extra_env["PG_PASSWORD"] = s.get("pg_password", "")

            log_lines.append(f"\n=== BRONZE: {s['source_type']} ({mode_arg}) ===")
            _render_status()
            rc = _stream(bronze_cmd, extra_env=src_extra_env)

            if rc != 0:
                st.error(
                    f"Bronze failed for {s['source_type']} source. "
                    "Remaining sources skipped."
                )
                run_failed = True
                break

            for t in s["tables"]:
                all_bronze_names.append(_bronze_name(t, src_type))

        if not run_failed and all_bronze_names:
            silver_cmd = [
                sys.executable,
                str(_PROJECT_ROOT / "src" / "run_silver_gold.py"),
                "--tables", ",".join(all_bronze_names),
                "--layer", "silver",
            ]
            log_lines.append("\n=== SILVER ===")
            _render_status()
            silver_rc = _stream(silver_cmd)

            if silver_rc == 0:
                st.success(
                    f"Bronze + Silver complete — {len(all_bronze_names)} table(s) "
                    "written to `data/silver/`."
                )
                st.info(
                    "Head to **Gold Builder** in the sidebar to create business "
                    "aggregations from your Silver tables."
                )
                st.session_state["bs_done_tables"] = all_bronze_names

                # Persist pipeline config
                config.reload()
                pipelines = config.get("pipelines", []) or []
                entry = {
                    "name": bs_pipeline_name,
                    "schedule": bs_schedule_type.lower().replace(" ", "_"),
                    "schedule_config": bs_schedule_config,
                    "sources": [
                        {
                            "source_type": (
                                "file"
                                if s["source_type"] == "File / CSV / JSON"
                                else "postgresql"
                            ),
                            "mode": "full" if s["mode"] == "Full Load" else "incremental",
                            "tables": s["tables"],
                            **(
                                {"connection": {
                                    "host": s["pg_host"],
                                    "port": s["pg_port"],
                                    "database": s["pg_database"],
                                }}
                                if s.get("pg_is_override")
                                else {}
                            ),
                        }
                        for s in all_sources
                        if s["tables"]
                    ],
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
                    "last_status": "success",
                }
                names = [p.get("name") for p in pipelines]
                if entry["name"] in names:
                    pipelines[names.index(entry["name"])] = entry
                else:
                    pipelines.append(entry)
                config.set("pipelines", pipelines)
                config.save()

                # Generate pipeline documentation
                doc_content = bronze_silver_doc(
                    pipeline_name=bs_pipeline_name,
                    sources=entry["sources"],
                    bronze_path=_PROJECT_ROOT / config.get("paths.bronze", "data/bronze"),
                    silver_path=_PROJECT_ROOT / config.get("paths.silver", "data/silver"),
                    bronze_names=all_bronze_names,
                    schedule_config=bs_schedule_config,
                    run_ts=entry["last_run"],
                )
                doc_path = save_pipeline_doc(_PROJECT_ROOT, bs_pipeline_name, doc_content)
                st.caption(f"📄 Pipeline doc saved: `{doc_path}`")
            else:
                st.error("Silver finished with errors. Check logs above.")
                # Record failure in config so Monitor Pipelines can display it
                if bs_pipeline_name:
                    config.reload()
                    pipelines = config.get("pipelines", []) or []
                    names = [p.get("name") for p in pipelines]
                    run_ts_f = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
                    if bs_pipeline_name in names:
                        pipelines[names.index(bs_pipeline_name)]["last_run"] = run_ts_f
                        pipelines[names.index(bs_pipeline_name)]["last_status"] = "failed"
                        config.set("pipelines", pipelines)
                        config.save()
