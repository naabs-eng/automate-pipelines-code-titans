import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from config.config_manager import ConfigManager
from pipeline_docs import load_pipeline_doc, _safe_filename

st.title("📊 Monitor Pipelines")
st.caption("Overview of all pipelines — click a name to see its full documentation.")

config = ConfigManager()
pipelines = config.get("pipelines", []) or []

if not pipelines:
    st.info(
        "No pipelines found. Create one in **Bronze & Silver Pipeline** or "
        "**Gold Builder**."
    )
    st.stop()

# ── Selected pipeline state ────────────────────────────────────────────────────
if "monitor_selected" not in st.session_state:
    st.session_state.monitor_selected = None
if "mon_delete_confirm" not in st.session_state:
    st.session_state.mon_delete_confirm = None


def _select(name):
    if st.session_state.monitor_selected == name:
        st.session_state.monitor_selected = None  # toggle off
    else:
        st.session_state.monitor_selected = name


def _schedule_label(p):
    sc = p.get("schedule_config", {})
    stype = sc.get("type") or p.get("schedule", "run_once")
    if stype in ("run_once", "Run Once"):
        return "Run once"
    if stype in ("hourly", "Hourly"):
        return "Hourly"
    if stype in ("daily", "Daily"):
        t = sc.get("time", "")
        return f"Daily {t}".strip()
    if stype in ("weekly", "Weekly"):
        day = sc.get("day", "")
        t = sc.get("time", "")
        return f"Weekly {day} {t}".strip()
    if stype in ("custom_cron", "Custom Cron"):
        return sc.get("cron", "Custom")
    return str(stype).replace("_", " ").title()


def _status_badge(p):
    s = p.get("last_status", "")
    if s == "success":
        return "✅ Passed"
    if s == "failed":
        return "❌ Failed"
    return "—"


def _pipeline_type(p):
    name = p.get("name", "")
    if name.endswith("_gold"):
        return "🏆 Gold"
    if name.endswith("_bronze_silver"):
        return "🔄 Bronze & Silver"
    return "—"


# ── Delete confirmation banner ─────────────────────────────────────────────────
_pending_delete = st.session_state.mon_delete_confirm
if _pending_delete:
    st.warning(
        f"⚠️ Delete pipeline **{_pending_delete}**? "
        "This removes it from config.yaml and its documentation file."
    )
    _dc1, _dc2, _ = st.columns([1, 1, 4])
    if _dc1.button("🗑 Confirm Delete", type="primary", key="mon_del_confirm_btn"):
        config.reload()
        _all_pipes = config.get("pipelines", []) or []
        _all_pipes = [p for p in _all_pipes if p.get("name") != _pending_delete]
        config.set("pipelines", _all_pipes)
        config.save()
        _doc_path = _PROJECT_ROOT / "pipelines" / f"{_safe_filename(_pending_delete)}.md"
        if _doc_path.exists():
            _doc_path.unlink()
        if st.session_state.monitor_selected == _pending_delete:
            st.session_state.monitor_selected = None
        st.session_state.mon_delete_confirm = None
        st.rerun()
    if _dc2.button("Cancel", key="mon_del_cancel_btn"):
        st.session_state.mon_delete_confirm = None
        st.rerun()

# ── Pipeline table ─────────────────────────────────────────────────────────────
# Header
hcols = st.columns([0.24, 0.13, 0.20, 0.17, 0.14, 0.12])
hcols[0].markdown("**Pipeline Name**")
hcols[1].markdown("**Type**")
hcols[2].markdown("**Schedule**")
hcols[3].markdown("**Last Run**")
hcols[4].markdown("**Status**")
hcols[5].markdown("**Delete**")

st.markdown(
    "<hr style='margin:4px 0 8px 0; border-color:#e0e0e0'>",
    unsafe_allow_html=True,
)

for p in pipelines:
    name = p.get("name", "Unnamed")
    last_run = p.get("last_run", "—")
    is_selected = st.session_state.monitor_selected == name

    row = st.columns([0.24, 0.13, 0.20, 0.17, 0.14, 0.12])
    with row[0]:
        label = f"**{name}**" if is_selected else name
        if st.button(
            label,
            key=f"mon_sel_{name}",
            help="Click to view pipeline details",
            use_container_width=True,
        ):
            _select(name)
    row[1].markdown(_pipeline_type(p))
    row[2].markdown(_schedule_label(p))
    row[3].markdown(last_run[:16] if last_run and last_run != "—" else "—")
    row[4].markdown(_status_badge(p))
    with row[5]:
        if st.button("🗑", key=f"mon_del_{name}", help=f"Delete {name}"):
            st.session_state.mon_delete_confirm = name
            st.rerun()

st.divider()

# ── Detail panel ───────────────────────────────────────────────────────────────
selected = st.session_state.monitor_selected

if not selected:
    st.caption("Select a pipeline above to view its documentation.")
else:
    # Find the pipeline entry
    entry = next((p for p in pipelines if p.get("name") == selected), None)
    doc_content = load_pipeline_doc(_PROJECT_ROOT, selected)

    if doc_content:
        # Toolbar: re-run button routes to the correct page
        rc1, rc2, rc3 = st.columns([4, 1, 1])
        with rc1:
            st.subheader(f"Pipeline: {selected}")
        with rc2:
            pipeline_type = _pipeline_type(entry or {})
            if "Bronze" in pipeline_type:
                if st.button(
                    "▶ Re-run",
                    key="mon_rerun_bs",
                    type="primary",
                    help="Go to Bronze & Silver Pipeline page to re-run",
                ):
                    # Pre-fill the base name by stripping the suffix
                    base = selected.removesuffix("_bronze_silver")
                    st.session_state["bs_pipeline_name_input"] = base
                    if entry:
                        srcs = entry.get("sources", [])
                        ids = []
                        for j, s in enumerate(srcs, 1):
                            sid = f"src_{j}"
                            ids.append(sid)
                            st.session_state[f"stype_{sid}"] = (
                                "PostgreSQL"
                                if s.get("source_type") == "postgresql"
                                else "File / CSV / JSON"
                            )
                            st.session_state[f"tables_{sid}"] = "\n".join(
                                s.get("tables", [])
                            )
                            st.session_state[f"mode_{sid}"] = "Full Load"
                        st.session_state["pipeline_source_ids"] = ids
                        st.session_state["source_counter"] = len(ids)
                    st.switch_page("pages/2_Bronze_Silver.py")
            else:
                if st.button(
                    "▶ Re-run",
                    key="mon_rerun_gold",
                    type="primary",
                    help="Go to Gold Builder page to re-run",
                ):
                    base = selected.removesuffix("_gold")
                    st.session_state["gold_pipeline_name_input"] = base
                    if entry:
                        all_tbls = [
                            t
                            for s in entry.get("sources", [])
                            for t in s.get("tables", [])
                        ]
                        st.session_state["gold_rerun_tables"] = all_tbls
                    st.switch_page("pages/3_Gold_Builder.py")
        with rc3:
            if st.button("✕ Close", key="mon_close"):
                st.session_state.monitor_selected = None
                st.rerun()

        st.markdown(doc_content)

    else:
        st.subheader(f"Pipeline: {selected}")
        st.info(
            "No documentation file found for this pipeline yet. "
            "A doc is generated after the first successful run.\n\n"
            f"Expected path: `pipelines/{selected}.md`"
        )
        if entry:
            st.markdown("**Config entry:**")
            st.json(entry)
