import json as _json
import os
import re
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from config.config_manager import ConfigManager
from gold_chatbot import (
    build_requirements_text,
    detect_join_keys,
    load_silver_schemas,
    map_column,
    parse_destination_schema,
    parse_requirements_to_plan,
)
from pipeline_docs import agent_gold_doc, gold_doc, save_pipeline_doc

st.title("🏆 Gold Builder")
st.caption(
    "Select Silver tables, optionally describe your business requirements, "
    "and build Gold aggregation tables. A plan is generated and shown for "
    "your confirmation before anything runs."
)

config = ConfigManager()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_agg_expr(expr: str):
    """Parse FUNC(args) where args may contain nested parens, e.g. SUM(datediff(a, b)).
    Returns (func_upper, args_str) or (None, None) if not parseable.
    Uses rfind so trailing punctuation (e.g. accidental '.') is ignored."""
    expr = expr.strip()
    first = expr.find("(")
    last = expr.rfind(")")
    if first < 1 or last == -1 or last <= first:
        return None, None
    func = expr[:first].strip().upper()
    if not re.match(r'^\w+$', func):
        return None, None
    args = expr[first + 1:last].strip()
    return func, args


def _resolve_path(raw):
    """Resolve a possibly-relative path to absolute using project root."""
    p = Path(raw)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _scan_silver_tables():
    """
    Return list of (display_name, dir_name, row_count, col_count) for every
    directory under data/silver/ that contains at least one Parquet file.
    Works with both old naming (suppliers) and new (suppliers_silver).
    """
    silver_path = _resolve_path(config.get("paths.silver", "data/silver"))
    results = []
    if not silver_path.exists():
        return results
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return results

    for d in sorted(silver_path.iterdir()):
        if not d.is_dir():
            continue
        parts = sorted(d.glob("**/*.parquet"))
        if not parts:
            continue
        try:
            schema = pq.read_schema(str(parts[0]))
            pf = pq.ParquetFile(str(parts[0]))
            row_count = pf.metadata.num_rows
            col_count = len(schema.names)
        except Exception:
            row_count = "?"
            col_count = "?"

        # Display name: strip _silver suffix if present, otherwise use dir name
        display = d.name[:-7] if d.name.endswith("_silver") else d.name
        results.append((display, d.name, row_count, col_count))

    return results



# ── Chatbot state machine ──────────────────────────────────────────────────────

def _gc_reset():
    for k in list(st.session_state.keys()):
        if k.startswith("gc_"):
            del st.session_state[k]


def _gc_add_bot(msg: str):
    st.session_state.gc_messages.append({"role": "assistant", "content": msg})


def _gc_add_user(msg: str):
    st.session_state.gc_messages.append({"role": "user", "content": msg})


def _mapping_summary_text(columns, mappings):
    lines = []
    for col in columns:
        name = col["name"]
        m = mappings.get(name, {})
        status = m.get("status", "not_found")
        if status == "direct":
            tables = ", ".join(m.get("source_tables", []))
            lines.append(f"✅ **{name}** — direct column from `{tables}`")
        elif status == "aggregation":
            lines.append(
                f"✅ **{name}** — `{m['func']}({m['source_col']})` (auto-resolved)"
            )
        elif status == "aggregation_candidates":
            lines.append(f"❓ **{name}** — aggregation, pick source column")
        elif status == "derived_boolean":
            lines.append(f"❓ **{name}** — derived boolean, need condition")
        elif status == "fuzzy":
            lines.append(f"❓ **{name}** — possible match, need confirmation")
        else:
            lines.append(f"❓ **{name}** — not found in Silver, need your input")
    return "\n".join(lines)


def _ask_filters():
    _gc_add_bot(
        "Any business rules or pre-aggregation filters?  \n"
        "e.g. `status = 'active'`, `amount > 0`  \n\n"
        "Type one and press **Add**, or click **Done** to skip."
    )


def _finalize_chatbot():
    gb = st.session_state.get("gc_resolved_gb", [])
    aggs = st.session_state.get("gc_resolved_aggs", [])
    derived = st.session_state.get("gc_derived", [])
    joins = []
    join = st.session_state.get("gc_join")
    if join:
        joins.append(join)
    filters = st.session_state.get("gc_filters", [])
    destination = st.session_state.get("gc_destination", "gold_output")
    columns = st.session_state.get("gc_columns", [])
    grain = st.session_state.get("gc_grain", "")

    gb_aliases = st.session_state.get("gc_gb_aliases", {})
    req_text = build_requirements_text(
        destination=destination,
        group_by=gb,
        aggregations=aggs,
        derived_columns=derived,
        joins=joins,
        filters=filters,
        requested_columns=columns,
        grain=grain,
        gb_aliases=gb_aliases,
    )
    st.session_state["gc_req_text"] = req_text
    st.session_state["gc_state"] = "done"
    _gc_add_bot(
        "✅ All set! Click **Use these requirements** below to fill Step 3 "
        "and proceed to Analyse & Plan."
    )


def _advance_resolution():
    unresolved = st.session_state.get("gc_unresolved", [])
    idx = st.session_state.get("gc_unresolved_idx", 0)
    idx += 1
    st.session_state["gc_unresolved_idx"] = idx
    if idx >= len(unresolved):
        _next_after_columns()
    else:
        _ask_column_question(unresolved[idx])


def _ask_column_question(col_name):
    mappings = st.session_state.get("gc_mappings", {})
    m = mappings.get(col_name, {})
    status = m.get("status", "not_found")
    st.session_state["gc_state"] = f"resolving"

    if status == "aggregation_candidates":
        cands = m.get("candidates", [])
        cand_list = ", ".join(f"`{c['col']}`" for c in cands[:4])
        _gc_add_bot(
            f"For **{col_name}**: which source column should `{m.get('func','SUM')}()` "
            f"be applied to?  \nOptions: {cand_list}"
        )
    elif status == "derived_boolean":
        _gc_add_bot(
            f"For **{col_name}**: what's the condition that makes it `TRUE`?  \n"
            f"e.g. `total_spend > 300`, `status = 'premium'`"
        )
    elif status == "fuzzy":
        cands = m.get("candidates", [])
        cand_list = ", ".join(f"`{c['col']}`" for c in cands[:4])
        _gc_add_bot(
            f"**{col_name}** wasn't found exactly.  \n"
            f"Possible matches: {cand_list}  \n"
            f"Pick one, type a different name, or **Skip**."
        )
    else:
        all_cols = [
            c["col"] for c in m.get("available", [])
        ]
        sample = ", ".join(f"`{c}`" for c in all_cols[:6])
        _gc_add_bot(
            f"**{col_name}** wasn't found in the selected Silver tables.  \n"
            f"Available columns: {sample}{'...' if len(all_cols) > 6 else ''}  \n"
            f"Type the correct column name or **Skip**."
        )


def _next_after_columns():
    schemas = st.session_state.get("gc_schemas", {})
    if len(schemas) >= 2:
        join_keys = detect_join_keys(schemas)
        keys_str = ", ".join(f"`{k}`" for k in join_keys[:5]) if join_keys else "none detected"
        _gc_add_bot(
            f"Multiple Silver tables selected. Should they be joined?  \n"
            f"Detected common key(s): {keys_str}"
        )
        st.session_state["gc_state"] = "awaiting_join"
    else:
        _ask_filters()
        st.session_state["gc_state"] = "filters"


def _render_chatbot(selected_silver: list, cfg):
    silver_path = _PROJECT_ROOT / cfg.get("paths.silver", "data/silver")

    # Reset chatbot if Silver table selection changed
    prev_tables = st.session_state.get("gc_tables")
    if prev_tables != selected_silver:
        _gc_reset()
        st.session_state["gc_tables"] = list(selected_silver)

    # Initialise session keys
    if "gc_state" not in st.session_state:
        st.session_state["gc_state"] = "idle"
    if "gc_messages" not in st.session_state:
        st.session_state["gc_messages"] = []

    state = st.session_state.gc_state

    # ── Render chat history ────────────────────────────────────────────────────
    for msg in st.session_state.get("gc_messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── State: idle ───────────────────────────────────────────────────────────
    if state == "idle":
        if not selected_silver:
            st.info("Select at least one Silver table in Step 2 to use the Chat Assistant.")
            return
        if st.button("💬 Start Chat Assistant", key="gc_start_btn"):
            schemas = load_silver_schemas(selected_silver, str(silver_path))
            st.session_state["gc_schemas"] = schemas
            st.session_state["gc_resolved_gb"] = []
            st.session_state["gc_resolved_aggs"] = []
            st.session_state["gc_derived"] = []
            st.session_state["gc_filters"] = []
            st.session_state["gc_join"] = None
            tables_str = ", ".join(f"`{t}`" for t in selected_silver)
            _gc_add_bot(
                f"I'll help you define your Gold table.  \n"
                f"Selected Silver tables: {tables_str}  \n\n"
                "What should the **destination table** be called, and what **columns** do you want?  \n"
                "Example: `customer_value_summary: customer_id (INT), total_spend (DECIMAL), "
                "transaction_count (INT), is_premium (BOOLEAN)`"
            )
            st.session_state["gc_state"] = "schema"
            st.rerun()
        return

    # ── State: schema ─────────────────────────────────────────────────────────
    if state == "schema":
        with st.form("gc_schema_form", clear_on_submit=True):
            user_input = st.text_input(
                "Your schema",
                placeholder="customer_value_summary: customer_id (INT), total_spend (DECIMAL), ...",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Submit")

        if submitted and user_input.strip():
            _gc_add_user(user_input)
            parsed = parse_destination_schema(user_input)
            dest = parsed.get("destination")
            columns = parsed.get("columns", [])

            if not dest:
                st.session_state["gc_state"] = "awaiting_destination"
                st.session_state["gc_columns"] = columns
                _gc_add_bot(
                    "I couldn't detect a destination table name.  \n"
                    "What should the Gold table be called?"
                )
                st.rerun()
                return

            st.session_state["gc_destination"] = dest
            st.session_state["gc_columns"] = columns

            schemas = st.session_state.get("gc_schemas", {})
            mappings = {col["name"]: map_column(col["name"], schemas) for col in columns}
            st.session_state["gc_mappings"] = mappings

            summary = _mapping_summary_text(columns, mappings)
            unresolved = [
                col["name"] for col in columns
                if mappings.get(col["name"], {}).get("status") not in ("direct", "aggregation")
            ]

            # Auto-resolve direct columns into group_by
            gb = st.session_state.get("gc_resolved_gb", [])
            for col in columns:
                name = col["name"]
                m = mappings.get(name, {})
                if m.get("status") == "direct" and name not in gb:
                    gb.append(name)
            st.session_state["gc_resolved_gb"] = gb

            # Auto-resolve clean aggregations
            aggs = st.session_state.get("gc_resolved_aggs", [])
            for col in columns:
                name = col["name"]
                m = mappings.get(name, {})
                if m.get("status") == "aggregation":
                    aggs.append({
                        "func": m["func"],
                        "source_col": m["source_col"],
                        "col": m["source_col"],
                        "alias": name,
                    })
            st.session_state["gc_resolved_aggs"] = aggs

            n_unresolved = len(unresolved)
            suffix = (
                f"\n\n{n_unresolved} column(s) need your input. Let's go through them."
                if n_unresolved else "\n\nAll columns resolved automatically!"
            )
            _gc_add_bot(
                f"**Destination:** `{dest}`\n\n{summary}{suffix}"
            )

            st.session_state["gc_unresolved"] = unresolved
            st.session_state["gc_unresolved_idx"] = 0

            # Ask grain before diving into column resolution
            _gc_add_bot(
                "What's the **grain** of this table — what does one row represent?  \n"
                "e.g. *one row per customer*, *one row per day and product category*"
            )
            st.session_state["gc_state"] = "awaiting_grain"
            st.rerun()
        return

    # ── State: awaiting_grain ──────────────────────────────────────────────────
    if state == "awaiting_grain":
        with st.form("gc_grain_form", clear_on_submit=True):
            grain_input = st.text_input(
                "Grain",
                placeholder="e.g. one row per customer",
                label_visibility="collapsed",
            )
            sub = st.form_submit_button("Set grain")
        if sub and grain_input.strip():
            _gc_add_user(grain_input.strip())
            st.session_state["gc_grain"] = grain_input.strip()
            _gc_add_bot(f"Got it — grain: *{grain_input.strip()}*")
            unresolved = st.session_state.get("gc_unresolved", [])
            if unresolved:
                _ask_column_question(unresolved[0])
                st.session_state["gc_state"] = "resolving"
            else:
                _next_after_columns()
            st.rerun()
        return

    # ── State: awaiting_destination ────────────────────────────────────────────
    if state == "awaiting_destination":
        with st.form("gc_dest_form", clear_on_submit=True):
            dest_input = st.text_input(
                "Destination table name",
                placeholder="e.g. customer_value_summary",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Set name")

        if submitted and dest_input.strip():
            _gc_add_user(dest_input.strip())
            st.session_state["gc_destination"] = dest_input.strip()
            columns = st.session_state.get("gc_columns", [])
            schemas = st.session_state.get("gc_schemas", {})
            mappings = {col["name"]: map_column(col["name"], schemas) for col in columns}
            st.session_state["gc_mappings"] = mappings

            unresolved = [
                col["name"] for col in columns
                if mappings.get(col["name"], {}).get("status") not in ("direct", "aggregation")
            ]
            gb = [col["name"] for col in columns if mappings.get(col["name"], {}).get("status") == "direct"]
            aggs = []
            for col in columns:
                m = mappings.get(col["name"], {})
                if m.get("status") == "aggregation":
                    aggs.append({"func": m["func"], "source_col": m["source_col"], "col": m["source_col"], "alias": col["name"]})
            st.session_state["gc_resolved_gb"] = gb
            st.session_state["gc_resolved_aggs"] = aggs

            summary = _mapping_summary_text(columns, mappings)
            _gc_add_bot(f"Got it — destination is `{dest_input.strip()}`.\n\n{summary}")

            if unresolved:
                st.session_state["gc_unresolved"] = unresolved
                st.session_state["gc_unresolved_idx"] = 0
                _ask_column_question(unresolved[0])
            else:
                _next_after_columns()
            st.rerun()
        return

    # ── State: resolving ───────────────────────────────────────────────────────
    if state == "resolving":
        unresolved = st.session_state.get("gc_unresolved", [])
        idx = st.session_state.get("gc_unresolved_idx", 0)
        if idx >= len(unresolved):
            _next_after_columns()
            st.rerun()
            return

        col_name = unresolved[idx]
        mappings = st.session_state.get("gc_mappings", {})
        m = mappings.get(col_name, {})
        status = m.get("status", "not_found")

        if status == "aggregation_candidates":
            cands = m.get("candidates", [])
            func = m.get("func", "SUM")
            cols_btns = st.columns(min(len(cands) + 1, 5))
            for i, c in enumerate(cands[:4]):
                label = f"{func}({c['col']})"
                if cols_btns[i].button(label, key=f"gc_agg_cand_{col_name}_{i}"):
                    _gc_add_user(label)
                    aggs = st.session_state.get("gc_resolved_aggs", [])
                    aggs.append({"func": func, "source_col": c["col"], "col": c["col"], "alias": col_name})
                    st.session_state["gc_resolved_aggs"] = aggs
                    _gc_add_bot(f"✅ **{col_name}** = `{func}({c['col']})`")
                    _advance_resolution()
                    st.rerun()
            if cols_btns[-1].button("Type manually", key=f"gc_agg_manual_{col_name}"):
                st.session_state["gc_state"] = "resolving_manual_agg"
                st.rerun()

        elif status == "derived_boolean":
            with st.form(f"gc_bool_form_{col_name}", clear_on_submit=True):
                cond = st.text_input(
                    f"Condition for {col_name}",
                    placeholder="e.g. total_spend > 300",
                    label_visibility="collapsed",
                )
                sub = st.form_submit_button("Set condition")
            if sub and cond.strip():
                _gc_add_user(cond.strip())
                derived = st.session_state.get("gc_derived", [])
                derived.append({"col": col_name, "condition": cond.strip()})
                st.session_state["gc_derived"] = derived
                _gc_add_bot(f"✅ **{col_name}** = `{cond.strip()}`")
                _advance_resolution()
                st.rerun()

        else:  # fuzzy or not_found
            cands = m.get("candidates", [])
            schemas_inner = st.session_state.get("gc_schemas", {})
            all_silver_cols = [c["name"] for tbl in schemas_inner.values() for c in tbl]

            # Quick-pick buttons for fuzzy candidates
            if cands:
                st.caption("Quick map to existing column:")
                btn_cols = st.columns(min(len(cands) + 1, 5))
                for i, c in enumerate(cands[:4]):
                    if btn_cols[i].button(f"{c['col']}", key=f"gc_fuzzy_{col_name}_{i}"):
                        _gc_add_user(c["col"])
                        gb = st.session_state.get("gc_resolved_gb", [])
                        gb.append(c["col"])
                        st.session_state["gc_resolved_gb"] = gb
                        if c["col"] != col_name:
                            aliases = st.session_state.get("gc_gb_aliases", {})
                            aliases[c["col"]] = col_name
                            st.session_state["gc_gb_aliases"] = aliases
                        _gc_add_bot(f"✅ **{col_name}** mapped to `{c['col']}`")
                        _advance_resolution()
                        st.rerun()

            with st.form(f"gc_notfound_form_{col_name}", clear_on_submit=True):
                st.caption("Enter an aggregation expression:")
                expr_input = st.text_input(
                    "Aggregation",
                    placeholder="e.g. COUNT(*), SUM(amount), AVG(price)",
                    label_visibility="collapsed",
                )
                st.caption("Or map to an existing Silver column (group by):")
                sel_col = st.selectbox(
                    f"Column",
                    ["— skip —"] + all_silver_cols,
                    label_visibility="collapsed",
                )
                c1, c2 = st.columns(2)
                sub_confirm = c1.form_submit_button("Confirm")
                sub_skip = c2.form_submit_button("Skip")

            if sub_confirm:
                if expr_input.strip():
                    func_p, src_p = _parse_agg_expr(expr_input.strip())
                    if func_p:
                        aggs = st.session_state.get("gc_resolved_aggs", [])
                        aggs.append({"func": func_p, "source_col": src_p, "col": src_p, "alias": col_name})
                        st.session_state["gc_resolved_aggs"] = aggs
                        _gc_add_user(expr_input.strip())
                        _gc_add_bot(f"✅ **{col_name}** = `{func_p}({src_p})`")
                    else:
                        _gc_add_bot(f"⚠️ Couldn't parse `{expr_input.strip()}`. Use `FUNC(col)` format, e.g. `SUM(datediff(end_date, current_date()))`.")
                elif sel_col != "— skip —":
                    _gc_add_user(sel_col)
                    gb = st.session_state.get("gc_resolved_gb", [])
                    gb.append(sel_col)
                    st.session_state["gc_resolved_gb"] = gb
                    if sel_col != col_name:
                        aliases = st.session_state.get("gc_gb_aliases", {})
                        aliases[sel_col] = col_name
                        st.session_state["gc_gb_aliases"] = aliases
                    _gc_add_bot(f"✅ **{col_name}** mapped to `{sel_col}`")
                else:
                    _gc_add_bot(f"⏭ Skipped **{col_name}**")
                _advance_resolution()
                st.rerun()
            if sub_skip:
                _gc_add_bot(f"⏭ Skipped **{col_name}**")
                _advance_resolution()
                st.rerun()
        return

    # ── State: resolving_manual_agg ────────────────────────────────────────────
    if state == "resolving_manual_agg":
        unresolved = st.session_state.get("gc_unresolved", [])
        idx = st.session_state.get("gc_unresolved_idx", 0)
        col_name = unresolved[idx] if idx < len(unresolved) else ""
        with st.form("gc_manual_agg_form", clear_on_submit=True):
            expr = st.text_input(
                "Aggregation expression",
                placeholder="e.g. SUM(amount), AVG(price), COUNT(*)",
                label_visibility="collapsed",
            )
            sub = st.form_submit_button("Set")
        if sub and expr.strip():
            _gc_add_user(expr.strip())
            func, src = _parse_agg_expr(expr.strip())
            if func:
                aggs = st.session_state.get("gc_resolved_aggs", [])
                aggs.append({"func": func, "source_col": src, "col": src, "alias": col_name})
                st.session_state["gc_resolved_aggs"] = aggs
                _gc_add_bot(f"✅ **{col_name}** = `{func}({src})`")
            else:
                _gc_add_bot(f"⚠️ Couldn't parse `{expr}`. Use `FUNC(col)` format, e.g. `SUM(datediff(end_date, current_date()))`.")
            _advance_resolution()
            st.rerun()
        return

    # ── State: awaiting_join ───────────────────────────────────────────────────
    if state == "awaiting_join":
        schemas = st.session_state.get("gc_schemas", {})
        tables = list(schemas.keys())
        join_keys = detect_join_keys(schemas)

        if join_keys:
            btn_cols = st.columns(min(len(join_keys) + 2, 5))
            for i, key in enumerate(join_keys[:3]):
                if btn_cols[i].button(key, key=f"gc_jk_{key}"):
                    _gc_add_user(key)
                    fact = tables[0]
                    dim = tables[1]
                    jspec = {"fact": fact, "dim": dim, "on": key, "type": "left"}
                    st.session_state["gc_join"] = jspec
                    _gc_add_bot(
                        f"✅ LEFT JOIN `{fact}` → `{dim}` on `{key}`"
                    )
                    _ask_filters()
                    st.session_state["gc_state"] = "filters"
                    st.rerun()
            if btn_cols[-2].button("No join", key="gc_jk_none"):
                _gc_add_user("No join")
                st.session_state["gc_join"] = None
                _ask_filters()
                st.session_state["gc_state"] = "filters"
                st.rerun()
            if btn_cols[-1].button("Custom key", key="gc_jk_custom"):
                st.session_state["gc_state"] = "awaiting_join_custom"
                st.rerun()
        else:
            with st.form("gc_join_custom_init", clear_on_submit=True):
                custom_key = st.text_input(
                    "Join column name",
                    placeholder="e.g. customer_id",
                    label_visibility="collapsed",
                )
                c1, c2 = st.columns(2)
                sub_join = c1.form_submit_button("Set join key")
                sub_none = c2.form_submit_button("No join")
            if sub_join and custom_key.strip():
                _gc_add_user(custom_key.strip())
                fact, dim = tables[0], tables[1]
                st.session_state["gc_join"] = {"fact": fact, "dim": dim, "on": custom_key.strip(), "type": "left"}
                _gc_add_bot(f"✅ LEFT JOIN `{fact}` → `{dim}` on `{custom_key.strip()}`")
                _ask_filters()
                st.session_state["gc_state"] = "filters"
                st.rerun()
            if sub_none:
                _gc_add_user("No join")
                st.session_state["gc_join"] = None
                _ask_filters()
                st.session_state["gc_state"] = "filters"
                st.rerun()
        return

    # ── State: awaiting_join_custom ────────────────────────────────────────────
    if state == "awaiting_join_custom":
        schemas = st.session_state.get("gc_schemas", {})
        tables = list(schemas.keys())
        with st.form("gc_join_custom_form", clear_on_submit=True):
            custom_key = st.text_input(
                "Enter join column name",
                placeholder="e.g. customer_id",
                label_visibility="collapsed",
            )
            sub = st.form_submit_button("Set")
        if sub and custom_key.strip():
            _gc_add_user(custom_key.strip())
            fact, dim = tables[0], tables[1]
            st.session_state["gc_join"] = {"fact": fact, "dim": dim, "on": custom_key.strip(), "type": "left"}
            _gc_add_bot(f"✅ LEFT JOIN `{fact}` → `{dim}` on `{custom_key.strip()}`")
            _ask_filters()
            st.session_state["gc_state"] = "filters"
            st.rerun()
        return

    # ── State: filters ─────────────────────────────────────────────────────────
    if state == "filters":
        filters = st.session_state.get("gc_filters", [])
        if filters:
            st.markdown("**Filters added:**")
            for f in filters:
                st.markdown(f"- `{f}`")

        with st.form("gc_filter_form", clear_on_submit=True):
            fval = st.text_input(
                "Filter condition",
                placeholder="e.g. status = 'active'",
                label_visibility="collapsed",
            )
            c1, c2 = st.columns(2)
            sub_add = c1.form_submit_button("Add filter")
            sub_done = c2.form_submit_button("Done / No filters")

        if sub_add and fval.strip():
            _gc_add_user(fval.strip())
            filters.append(fval.strip())
            st.session_state["gc_filters"] = filters
            _gc_add_bot(f"✅ Filter added: `{fval.strip()}`  \nAdd another or click **Done**.")
            st.rerun()
        if sub_done:
            _gc_add_user("Done")
            _finalize_chatbot()
            st.rerun()
        return

    # ── State: done ────────────────────────────────────────────────────────────
    if state == "done":
        with st.expander("📋 Requirements preview", expanded=True):
            st.caption(
                "Edit inline if anything is wrong — this text is used as-is for execution."
            )
            st.text_area(
                "Requirements",
                key="gc_req_text",
                height=300,
                label_visibility="collapsed",
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Use these requirements", type="primary", key="gc_use_btn"):
                st.session_state["gold_requirements"] = st.session_state.get("gc_req_text", "")
                st.success("Requirements filled! Proceed to **Pipeline run** below.")
        with c2:
            if st.button("🔄 Start over", key="gc_reset_btn"):
                _gc_reset()
                st.rerun()
        return


# ── Saved Gold Pipelines ──────────────────────────────────────────────────────
saved = [
    p for p in (config.get("pipelines", []) or [])
    if str(p.get("name", "")).endswith("_gold")
]
if saved:
    with st.expander(f"Saved Gold Pipelines ({len(saved)})", expanded=False):
        for i, p in enumerate(saved):
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{p.get('name', 'Unnamed')}**")
                src_tbls = ", ".join(
                    t for s in p.get("sources", []) for t in s.get("tables", [])
                )
                st.caption(f"Silver tables: {src_tbls or '—'}")
            with c2:
                if p.get("last_run"):
                    st.caption(f"Last run: {p['last_run'][:16]}")
            with c3:
                if st.button("Re-run", key=f"gold_rerun_{i}"):
                    all_tbls = [
                        t for s in p.get("sources", []) for t in s.get("tables", [])
                    ]
                    st.session_state["gold_rerun_tables"] = all_tbls
                    raw_base = p.get("name", "").removesuffix("_gold")
                    st.session_state["gold_pipeline_name_input"] = raw_base
                    st.rerun()
    st.divider()

# ── 1. Pipeline Name ───────────────────────────────────────────────────────────
st.subheader("1 — Pipeline Name")
gold_name_raw = st.text_input(
    "Name *",
    key="gold_pipeline_name_input",
    placeholder="e.g. daily_sales",
    help="Required. Your pipeline will be saved as `<name>_gold`.",
)
if gold_name_raw:
    gold_pipeline_name = f"{gold_name_raw.strip()}_gold"
    st.caption(f"Pipeline name: **`{gold_pipeline_name}`**")
else:
    gold_pipeline_name = None
    st.caption(
        "Enter a name above. The pipeline will be saved as `<name>_gold`."
    )

st.divider()

# ── 2. Silver Table Selection ─────────────────────────────────────────────────
st.subheader("2 — Silver Tables")
silver_tables = _scan_silver_tables()

selected_silver = st.session_state.get("gold_rerun_tables", [])

if not silver_tables:
    st.warning(
        "No Silver tables found in `data/silver/`. "
        "Run **Bronze & Silver Pipeline** first."
    )
    selected_silver = []
else:
    st.caption(
        f"{len(silver_tables)} Silver table(s) available — "
        "select the ones you want to aggregate into Gold."
    )

    # Header row
    hc = st.columns([0.05, 0.35, 0.18, 0.18, 0.24])
    hc[1].markdown("**Table**")
    hc[2].markdown("**Rows**")
    hc[3].markdown("**Columns**")
    hc[4].markdown("**Directory**")

    selected_silver = []
    for display, dir_name, row_count, col_count in silver_tables:
        # Pre-check if this was a re-run selection
        precheck = dir_name in st.session_state.get("gold_rerun_tables", [])
        rc_cols = st.columns([0.05, 0.35, 0.18, 0.18, 0.24])
        checked = rc_cols[0].checkbox(
            "",
            key=f"gold_sel_{dir_name}",
            value=precheck,
            label_visibility="collapsed",
        )
        rc_cols[1].markdown(f"`{display}`")
        rc_cols[2].markdown(
            f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
        )
        rc_cols[3].markdown(str(col_count))
        rc_cols[4].markdown(f"`data/silver/{dir_name}/`")
        if checked:
            selected_silver.append(dir_name)

    # Clear re-run pre-selection after first render
    st.session_state.pop("gold_rerun_tables", None)

st.divider()

# ── 3. Business Requirements ───────────────────────────────────────────────────
st.subheader("3 — Business Requirements *(optional)*")
_render_chatbot(selected_silver, config)

st.divider()

# ── 4. Schedule ────────────────────────────────────────────────────────────────
st.subheader("4 — Schedule")

gold_schedule_type = st.selectbox(
    "Run Schedule",
    ["Run Once", "Hourly", "Daily", "Weekly", "Custom Cron"],
    key="gold_schedule_type",
)
gold_schedule_config = {"type": gold_schedule_type}

if gold_schedule_type == "Daily":
    g_rt = st.time_input("Run at", value=time(8, 0), key="gold_rt_d")
    gold_schedule_config["time"] = g_rt.strftime("%H:%M")
    st.caption(f"Cron: `{g_rt.minute} {g_rt.hour} * * *`")
elif gold_schedule_type == "Weekly":
    gc1, gc2 = st.columns(2)
    with gc1:
        g_day = st.selectbox(
            "Day",
            ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"],
            key="gold_weekly_day",
        )
    with gc2:
        g_rt = st.time_input("Run at", value=time(8, 0), key="gold_rt_w")
    g_day_num = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"].index(g_day)
    gold_schedule_config["day"] = g_day
    gold_schedule_config["time"] = g_rt.strftime("%H:%M")
    st.caption(f"Cron: `{g_rt.minute} {g_rt.hour} * * {g_day_num}`")
elif gold_schedule_type == "Hourly":
    st.caption("Cron: `0 * * * *`")
    gold_schedule_config["cron"] = "0 * * * *"
elif gold_schedule_type == "Custom Cron":
    g_cron = st.text_input(
        "Cron Expression", placeholder="0 8 * * 1-5", key="gold_cron_expr",
    )
    gold_schedule_config["cron"] = g_cron
    if g_cron:
        st.caption(f"Expression: `{g_cron}`")

st.divider()

# ── 5. Run Gold (chatbot path) or Analyse & Plan (manual path) ────────────────
_chatbot_done = st.session_state.get("gc_state") == "done"

if _chatbot_done:
    st.subheader("5 — Run Gold")
else:
    st.subheader("5 — Analyse & Plan")

if not gold_pipeline_name:
    st.warning("Enter a pipeline name in Step 1 before continuing.")
elif not selected_silver:
    st.info("Select at least one Silver table in Step 2 to continue.")
elif _chatbot_done:
    # ── Direct run from chatbot plan ──────────────────────────────────────────
    st.success("Chat Assistant requirements are ready — no analysis step needed.")
    _req_text = st.session_state.get("gc_req_text", "")
    _source_tables = st.session_state.get("gc_tables", [])
    chatbot_plan = parse_requirements_to_plan(_req_text, _source_tables)

    with st.expander("📋 Plan summary", expanded=True):
        dest = chatbot_plan.get("destination", "—")
        st.markdown(f"**Destination:** `data/gold/{dest}/`")
        if chatbot_plan.get("grain"):
            st.markdown(f"**Grain:** {chatbot_plan['grain']}")
        st.markdown("**Source tables:** " + ", ".join(f"`{t}`" for t in chatbot_plan.get("source_tables", [])))
        if chatbot_plan.get("joins"):
            for j in chatbot_plan["joins"]:
                st.markdown(f"**Join:** `{j['fact']}` LEFT JOIN `{j['dim']}` ON `{j['on']}`")
        gb = chatbot_plan.get("group_by", [])
        if gb:
            st.markdown("**Group by:** " + ", ".join(f"`{c}`" for c in gb))
        aggs = chatbot_plan.get("aggregations", [])
        if aggs:
            rows = ["| Function | Column | Output |", "|---|---|---|"]
            for a in aggs:
                rows.append(f"| `{a['func']}` | `{a['col']}` | `{a['alias']}` |")
            st.markdown("\n".join(rows))
        for dc in chatbot_plan.get("derived_columns", []):
            st.markdown(f"**Derived:** `{dc['column']}` = `{dc['expression']}`")
        for f in chatbot_plan.get("filters", []):
            st.markdown(f"**Filter:** `{f}`")

    if st.button("▶ Run Gold", type="primary", key="gold_direct_run_btn"):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as tf:
            _json.dump(chatbot_plan, tf)
            _plan_file = tf.name

        run_env_g = {**os.environ, "PYTHONUNBUFFERED": "1"}
        log_box_g = st.empty()
        log_lines_g = []

        proc = subprocess.Popen(
            [sys.executable, str(_PROJECT_ROOT / "src" / "run_silver_gold.py"),
             "--agent-plan-file", _plan_file],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=run_env_g, cwd=str(_PROJECT_ROOT),
        )
        while True:
            line = proc.stdout.readline()
            if line == "" and proc.poll() is not None:
                break
            if line:
                log_lines_g.append(line.rstrip())
                log_box_g.code("\n".join(log_lines_g[-40:]), language="text")
        rc = proc.returncode

        if rc == 0:
            st.success(f"Gold complete! Table `{dest}` written to `data/gold/`")
            config.reload()
            pipelines = config.get("pipelines", []) or []
            run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
            entry = {
                "name": gold_pipeline_name,
                "schedule": gold_schedule_type.lower().replace(" ", "_"),
                "schedule_config": gold_schedule_config,
                "sources": [{"source_type": "silver", "tables": chatbot_plan.get("source_tables", [])}],
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "last_run": run_ts,
                "last_status": "success",
            }
            names = [p.get("name") for p in pipelines]
            if gold_pipeline_name in names:
                pipelines[names.index(gold_pipeline_name)] = entry
            else:
                pipelines.append(entry)
            config.set("pipelines", pipelines)
            config.save()
            st.info(f"Pipeline **{gold_pipeline_name}** saved to config.yaml")
            doc = agent_gold_doc(
                pipeline_name=gold_pipeline_name,
                plan=chatbot_plan,
                silver_path=_PROJECT_ROOT / config.get("paths.silver", "data/silver"),
                gold_path=_PROJECT_ROOT / config.get("paths.gold", "data/gold"),
                schedule_config=gold_schedule_config,
                run_ts=run_ts,
                status="success",
            )
            doc_path = save_pipeline_doc(_PROJECT_ROOT, gold_pipeline_name, doc)
            st.caption(f"📄 Pipeline doc saved: `{doc_path}`")
            _gc_reset()
            st.session_state.pop("gold_plan", None)
            st.session_state.pop("gold_plan_confirmed", None)
        else:
            st.error("Run finished with errors. Check the log above.")
            config.reload()
            pipelines = config.get("pipelines", []) or []
            names = [p.get("name") for p in pipelines]
            run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
            if gold_pipeline_name in names:
                pipelines[names.index(gold_pipeline_name)]["last_run"] = run_ts
                pipelines[names.index(gold_pipeline_name)]["last_status"] = "failed"
                config.set("pipelines", pipelines)
                config.save()

else:
    st.caption("Selected: " + ", ".join(f"`{t}`" for t in selected_silver))

    if st.button("🔍 Analyse & Generate Plan", type="secondary", key="gold_analyse_btn"):
        st.session_state.pop("gold_plan", None)
        st.session_state.pop("gold_plan_confirmed", None)
        reqs = st.session_state.get("gold_requirements", "").strip()
        with st.spinner("Reading Silver schemas and generating Gold plan…"):
            cmd = [
                sys.executable,
                str(_PROJECT_ROOT / "src" / "analyse_gold.py"),
                "--tables", ",".join(selected_silver),
            ]
            if reqs:
                cmd.extend(["--requirements", reqs])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
            )
        if result.returncode != 0 or not result.stdout.strip():
            st.error(
                f"Analysis failed:\n```\n{result.stderr or result.stdout}\n```"
            )
        else:
            try:
                st.session_state["gold_plan"] = _json.loads(result.stdout)
            except Exception as exc:
                st.error(f"Could not parse analysis output: {exc}")

    # ── Plan display ──────────────────────────────────────────────────────────
    gold_plan = st.session_state.get("gold_plan")
    if gold_plan:
        global_qs = gold_plan.get("global_questions", [])
        tables_plan = gold_plan.get("tables", [])
        cross_hint = gold_plan.get("cross_table_hint")

        if global_qs:
            st.markdown("---")
            st.markdown("**Needs your input before this plan can run:**")
            for i, q in enumerate(global_qs):
                st.warning(q)
                st.text_input(
                    "Your answer",
                    key=f"gold_gq_{i}",
                    placeholder="Update Business Requirements above then re-analyse.",
                )

        # ── Cross-table join hint ─────────────────────────────────────────────
        join_unresolved = False
        if cross_hint:
            st.markdown("---")
            if cross_hint.get("join_confirmed"):
                st.success(f"**Join confirmed:** {cross_hint['question']}")
            else:
                st.warning(cross_hint["question"])
                st.caption(
                    "Add a `Joins:` section to **Business Requirements** (Step 3) "
                    "then click **🔍 Analyse & Generate Plan** again."
                )
                join_unresolved = True

        if tables_plan:
            st.markdown("---")
            if join_unresolved:
                st.markdown(
                    "**Preliminary per-table plans** *(join unresolved — resolve above first):*"
                )
            else:
                st.markdown("**Proposed Gold Plan — review before confirming:**")

            all_questions = []
            all_warnings = []

            for tp in tables_plan:
                src = tp["source_silver"]
                dest = tp["destination"]
                with st.expander(
                    f"📊 `{src}` → Gold: `{dest}`",
                    expanded=not join_unresolved,
                ):
                    # ── Summary property table ────────────────────────────────
                    props = [
                        ("Source", f"`{src}`"),
                        ("Destination", f"`data/gold/{dest}/`"),
                        ("Grain", tp["grain"]),
                    ]
                    if tp.get("filters"):
                        props.append(("Business Rules", "  \n".join(f"- {r}" for r in tp["filters"])))
                    if tp.get("joins"):
                        props.append(("Joins", "  \n".join(
                            f"- `{j['fact']}` LEFT JOIN `{j['dim']}` ON `{j['on']}`"
                            for j in tp["joins"]
                        )))
                    props.append((
                        "Group By",
                        ", ".join(f"`{c}`" for c in tp["group_by"]) or "—",
                    ))
                    props.append((
                        "Aggregations",
                        "  \n".join(
                            f"- `{a['func']}({a['col']})` → `{a['alias']}`"
                            for a in tp["aggregations"]
                        ),
                    ))

                    tbl_md = ["| Property | Value |", "|:---|:---|"]
                    for prop, val in props:
                        tbl_md.append(f"| **{prop}** | {val} |")
                    st.markdown("\n".join(tbl_md))

                    # ── Output schema table ───────────────────────────────────
                    st.markdown("**Output schema:**")
                    schema_rows = ["| Column | Type | Source / Logic |", "|---|---|---|"]
                    for col in tp["output_schema"]:
                        schema_rows.append(
                            f"| `{col['column']}` | `{col['type']}` | {col['source']} |"
                        )
                    st.markdown("\n".join(schema_rows))

                all_questions.extend(tp.get("questions", []))
                all_warnings.extend(tp.get("warnings", []))

            if all_warnings:
                st.markdown("**Warnings (auto-resolved — verify they make sense):**")
                for w in all_warnings:
                    st.warning(w)

            if all_questions:
                st.markdown("**Open questions — address these before confirming:**")
                for i, q in enumerate(all_questions):
                    st.error(q)
                    st.text_input(
                        "Your answer / correction",
                        key=f"gold_tq_{i}",
                        placeholder=(
                            "Update Business Requirements with the correct column names, "
                            "then click 🔍 Analyse again."
                        ),
                    )

            # ── Add more requirements ─────────────────────────────────────────
            st.markdown("---")
            with st.expander("✏️ Need to refine? Add more requirements", expanded=False):
                st.caption(
                    "Add joins, filters, column specs, etc. "
                    "These will be appended to Business Requirements (Step 3) and re-analysed."
                )
                extra_reqs = st.text_area(
                    "Additional requirements",
                    key="gold_extra_reqs",
                    height=100,
                    placeholder=(
                        "Joins:\n"
                        "  - table_a → table_b (on key_col)\n\n"
                        "Business rules:\n"
                        "  - Filter where status != 'cancelled'"
                    ),
                )
                if st.button("🔍 Re-analyse with these additions", key="gold_reanalyse_extra"):
                    current = st.session_state.get("gold_requirements", "").strip()
                    extra = extra_reqs.strip()
                    combined = (current + "\n\n" + extra).strip() if extra else current
                    st.session_state["gold_requirements"] = combined
                    st.session_state.pop("gold_plan", None)
                    st.session_state.pop("gold_plan_confirmed", None)
                    st.rerun()

            # ── Confirmation gate ─────────────────────────────────────────────
            blocking = bool(all_questions) or join_unresolved
            if not blocking:
                st.markdown("---")
                gold_confirmed = st.checkbox(
                    "✅ I confirm this plan — proceed to Run Gold",
                    key="gold_plan_confirmed",
                )

                if gold_confirmed:
                    st.divider()
                    st.subheader("6 — Run Gold")
                    gold_run_btn = st.button(
                        "▶ Run Gold", type="primary", key="gold_run_btn"
                    )

                    if gold_run_btn:
                        import json as _json_run
                        import tempfile

                        run_env_g = {**os.environ, "PYTHONUNBUFFERED": "1"}
                        log_box_g = st.empty()
                        status_box_g = st.empty()
                        gold_log_lines = []
                        gold_status = {t: "⏳" for t in selected_silver}

                        def _render_gold():
                            rows = ["| Silver Table | Gold Status |", "|---|---|"]
                            for tn, gs in gold_status.items():
                                rows.append(f"| `{tn}` | {gs} |")
                            status_box_g.markdown("\n".join(rows))

                        _render_gold()

                        # Write plan to temp file for joined execution
                        plan_file_arg = []
                        current_plan = st.session_state.get("gold_plan", {})
                        hint = (current_plan or {}).get("cross_table_hint") or {}
                        if hint.get("join_confirmed"):
                            with tempfile.NamedTemporaryFile(
                                mode="w", suffix=".json", delete=False, dir="/tmp"
                            ) as tf:
                                _json_run.dump(current_plan, tf)
                                plan_file_arg = ["--plan-file", tf.name]

                        if plan_file_arg:
                            gold_cmd = [
                                sys.executable,
                                str(_PROJECT_ROOT / "src" / "run_silver_gold.py"),
                            ] + plan_file_arg
                        else:
                            gold_cmd = [
                                sys.executable,
                                str(_PROJECT_ROOT / "src" / "run_silver_gold.py"),
                                "--silver-tables", ",".join(selected_silver),
                                "--layer", "gold",
                            ]

                        proc = subprocess.Popen(
                            gold_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            env=run_env_g,
                            cwd=str(_PROJECT_ROOT),
                        )
                        while True:
                            line = proc.stdout.readline()
                            if line == "" and proc.poll() is not None:
                                break
                            if line:
                                line = line.rstrip()
                                gold_log_lines.append(line)
                                log_box_g.code(
                                    "\n".join(gold_log_lines[-40:]), language="text"
                                )
                                for tn in gold_status:
                                    base_tn = (
                                        tn[:-7] if tn.endswith("_silver") else tn
                                    )
                                    dest_name = hint.get("destination", "")
                                    if (
                                        f"[Gold] SUCCESS: {base_tn}" in line
                                        or f"[Gold] SUCCESS: {base_tn}_summary" in line
                                        or (dest_name and f"[Gold] SUCCESS: {dest_name}" in line)
                                    ):
                                        gold_status[tn] = "✅"
                                    elif f"[Gold] Skipping {base_tn}" in line:
                                        gold_status[tn] = "⏭"
                                    elif f"ERROR: {tn}" in line:
                                        gold_status[tn] = "❌"
                                _render_gold()
                        gold_rc = proc.returncode

                        if gold_rc == 0:
                            st.success("Gold complete!")

                            config.reload()
                            pipelines = config.get("pipelines", []) or []
                            gold_entry = {
                                "name": gold_pipeline_name,
                                "schedule": gold_schedule_type.lower().replace(" ", "_"),
                                "schedule_config": gold_schedule_config,
                                "sources": [
                                    {"source_type": "silver", "tables": selected_silver}
                                ],
                                "created_at": datetime.now(timezone.utc).strftime(
                                    "%Y-%m-%d"
                                ),
                                "last_run": datetime.now(timezone.utc).strftime(
                                    "%Y-%m-%dT%H:%M"
                                ),
                                "last_status": "success",
                            }
                            names = [p.get("name") for p in pipelines]
                            if gold_entry["name"] in names:
                                pipelines[names.index(gold_entry["name"])] = gold_entry
                            else:
                                pipelines.append(gold_entry)
                            config.set("pipelines", pipelines)
                            config.save()
                            st.info(
                                f"Pipeline **{gold_pipeline_name}** saved to config.yaml"
                            )

                            doc_content = gold_doc(
                                pipeline_name=gold_pipeline_name,
                                silver_tables=selected_silver,
                                silver_path=_PROJECT_ROOT / config.get("paths.silver", "data/silver"),
                                gold_path=_PROJECT_ROOT / config.get("paths.gold", "data/gold"),
                                gold_plan=st.session_state.get("gold_plan"),
                                schedule_config=gold_schedule_config,
                                run_ts=gold_entry["last_run"],
                            )
                            doc_path = save_pipeline_doc(
                                _PROJECT_ROOT, gold_pipeline_name, doc_content
                            )
                            st.caption(f"📄 Pipeline doc saved: `{doc_path}`")

                            st.session_state.pop("gold_plan", None)
                            st.session_state.pop("gold_plan_confirmed", None)
                        else:
                            st.error("Gold finished with errors. Check logs above.")
                            if gold_pipeline_name:
                                config.reload()
                                pipelines = config.get("pipelines", []) or []
                                names = [p.get("name") for p in pipelines]
                                run_ts_f = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
                                if gold_pipeline_name in names:
                                    pipelines[names.index(gold_pipeline_name)]["last_run"] = run_ts_f
                                    pipelines[names.index(gold_pipeline_name)]["last_status"] = "failed"
                                    config.set("pipelines", pipelines)
                                    config.save()
