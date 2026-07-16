import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from config.config_manager import ConfigManager


st.title("🔍 Data Explorer")
st.caption("Browse Bronze, Silver, and Gold tables — preview data, inspect schemas, and run SQL queries.")

config = ConfigManager()

LAYERS = {
    "🥉 Bronze": config.get("paths.bronze", "data/bronze"),
    "🥈 Silver": config.get("paths.silver", "data/silver"),
    "🥇 Gold":   config.get("paths.gold",   "data/gold"),
}
LAYER_KEYS = {k: k.split()[-1].lower() for k in LAYERS}   # "🥉 Bronze" → "bronze"
AUDIT_COLS  = {"_ingestion_timestamp", "_source_name", "_load_mode"}


def _resolve_path(raw):
    p = Path(raw)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _scan_layer(layer_label: str) -> list:
    base = _resolve_path(LAYERS[layer_label])
    tables = []
    if not base.exists():
        return tables
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        parts = sorted(d.glob("**/*.parquet"))
        if not parts:
            continue
        try:
            schema    = pq.read_schema(str(parts[0]))
            pf        = pq.ParquetFile(str(parts[0]))
            row_count = pf.metadata.num_rows
            col_count = len(schema.names)
        except Exception:
            row_count = 0
            col_count = 0
        tables.append({
            "name":      d.name,
            "row_count": row_count,
            "col_count": col_count,
            "path":      parts[0],
            "dir":       d,
        })
    return tables


def _register_all_views(con):
    """Register every parquet file across all layers as a DuckDB view."""
    registered = []
    for label, raw_path in LAYERS.items():
        base = _resolve_path(raw_path)
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            parts = sorted(d.glob("**/*.parquet"))
            if not parts:
                continue
            safe_name = d.name.replace("-", "_")
            con.execute(
                f"CREATE OR REPLACE VIEW {safe_name} AS "
                f"SELECT * FROM read_parquet('{parts[0]}')"
            )
            registered.append((safe_name, label.split()[-1]))
    return registered


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🗂 Navigator")
    layer_label = st.selectbox("Layer", list(LAYERS.keys()), key="de_layer")
    tables = _scan_layer(layer_label)

    if not tables:
        st.warning(f"No tables found in {layer_label} layer.")
        st.stop()

    table_names  = [t["name"] for t in tables]
    selected_name = st.selectbox("Table", table_names, key="de_table")
    selected      = next(t for t in tables if t["name"] == selected_name)

    st.divider()
    st.caption(f"{len(tables)} table(s) in layer")

# ── Header metrics ─────────────────────────────────────────────────────────────
st.subheader(f"`{selected_name}`")
c1, c2, c3 = st.columns(3)
c1.metric("Rows",    f"{selected['row_count']:,}")
c2.metric("Columns", selected["col_count"])
c3.metric("Layer",   layer_label.split()[-1])

parquet_path = str(selected["path"])

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_data, tab_schema, tab_info, tab_sql = st.tabs(
    ["📊 Data", "🗃 Schema", "ℹ️ Info", "🔍 SQL"]
)

# ── Tab: Data ─────────────────────────────────────────────────────────────────
with tab_data:
    n_rows = st.slider("Preview rows", 10, 500, 50, key="de_nrows")
    try:
        df = pq.read_table(parquet_path).to_pandas().head(n_rows)
        st.dataframe(df, use_container_width=True)
        st.caption(f"Showing {min(n_rows, len(df))} of {selected['row_count']:,} rows")
    except Exception as e:
        st.error(f"Could not read table: {e}")

# ── Tab: Schema ───────────────────────────────────────────────────────────────
with tab_schema:
    try:
        schema = pq.read_schema(parquet_path)
        schema_rows = []
        for i in range(len(schema.names)):
            col_name = schema.names[i]
            schema_rows.append({
                "Column":  col_name,
                "Type":    str(schema.types[i]),
                "Audit":   "✓" if col_name in AUDIT_COLS else "",
            })
        schema_df = pd.DataFrame(schema_rows)
        st.dataframe(schema_df, use_container_width=True, hide_index=True)
        audit_present = [r["Column"] for r in schema_rows if r["Audit"]]
        if audit_present:
            st.caption(f"Audit columns (added at ingestion): `{'`, `'.join(audit_present)}`")
    except Exception as e:
        st.error(f"Could not read schema: {e}")

# ── Tab: Info ─────────────────────────────────────────────────────────────────
with tab_info:
    try:
        stat        = selected["path"].stat()
        file_size   = stat.st_size
        last_mod    = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        pf          = pq.ParquetFile(parquet_path)
        meta        = pf.metadata
        compression = meta.row_group(0).column(0).compression if meta.num_row_groups > 0 else "—"

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**File details**")
            st.markdown(f"- **Path:** `{selected['dir']}`")
            st.markdown(f"- **Size:** {file_size / 1024:.1f} KB")
            st.markdown(f"- **Last modified:** {last_mod}")
            st.markdown(f"- **Row groups:** {meta.num_row_groups}")
            st.markdown(f"- **Compression:** {compression}")

        with col_b:
            # Watermark info (Bronze only)
            if "Bronze" in layer_label:
                st.markdown("**Watermark**")
                wm_file = _resolve_path("data/bronze/.watermarks.json")
                if wm_file.exists():
                    wm = json.loads(wm_file.read_text())
                    if selected_name in wm:
                        entry = wm[selected_name]
                        st.markdown(f"- **Last ingested:** {entry.get('last_ingested', '—')[:19]}")
                        st.markdown(f"- **Source type:** {entry.get('source_type', '—')}")
                        st.markdown(f"- **Mode:** {entry.get('mode', '—')}")
                        if entry.get("watermark_col"):
                            st.markdown(f"- **Watermark col:** `{entry['watermark_col']}`")
                            st.markdown(f"- **Last value:** `{entry.get('last_watermark_value', '—')}`")
                    else:
                        st.caption("No watermark recorded for this table.")
                else:
                    st.caption("No watermarks file found.")

            # Related pipelines
            st.markdown("**Related pipelines**")
            pipelines = config.get("pipelines", []) or []
            related = [
                p for p in pipelines
                if any(
                    selected_name in " ".join(str(t) for t in s.get("tables", []))
                    for s in p.get("sources", [])
                )
            ]
            if related:
                for p in related:
                    status_icon = "✅" if p.get("last_status") == "success" else (
                        "❌" if p.get("last_status") == "failed" else "—"
                    )
                    last_run = (p.get("last_run") or "—")[:10]
                    st.markdown(f"- `{p['name']}` {status_icon} {last_run}")
            else:
                st.caption("No pipelines reference this table.")

    except Exception as e:
        st.error(f"Could not load info: {e}")

# ── Tab: SQL ──────────────────────────────────────────────────────────────────
with tab_sql:
    try:
        import duckdb
        _duckdb_available = True
    except ImportError:
        _duckdb_available = False

    if not _duckdb_available:
        st.warning("DuckDB not installed. Run `pip install duckdb` then restart the app.")
    else:
        st.caption("DuckDB SQL — all tables from all layers are registered as views. Full SQL supported.")

        safe_selected = selected_name.replace("-", "_")
        default_sql   = f"SELECT *\nFROM   {safe_selected}\nLIMIT  20"
        sql_query     = st.text_area(
            "Query",
            value=st.session_state.get("de_sql_val", default_sql),
            height=140,
            key="de_sql",
            label_visibility="collapsed",
            placeholder="SELECT * FROM table_name LIMIT 20",
        )

        run_col, _ = st.columns([1, 5])
        run_clicked = run_col.button("▶ Run", type="primary", key="de_run")

        if run_clicked and sql_query.strip():
            st.session_state["de_sql_val"] = sql_query
            try:
                con        = duckdb.connect()
                registered = _register_all_views(con)
                result_df  = con.execute(sql_query).df()
                con.close()
                st.success(f"{len(result_df):,} row(s) returned")
                st.dataframe(result_df, use_container_width=True)
            except Exception as e:
                st.error(str(e))
