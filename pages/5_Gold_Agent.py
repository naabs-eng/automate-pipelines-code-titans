import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, time, timezone
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv()

from config.config_manager import ConfigManager
from gold_agent import GoldAgent
from pipeline_docs import agent_gold_doc, save_pipeline_doc

config = ConfigManager()
_SILVER_PATH = _PROJECT_ROOT / config.get("paths.silver", "data/silver")
_GOLD_PATH   = _PROJECT_ROOT / config.get("paths.gold",   "data/gold")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_path(raw):
    p = Path(raw)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _scan_silver_tables():
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
            schema    = pq.read_schema(str(parts[0]))
            pf        = pq.ParquetFile(str(parts[0]))
            row_count = pf.metadata.num_rows
            col_count = len(schema.names)
        except Exception:
            row_count = "?"
            col_count = "?"
        display = d.name[:-7] if d.name.endswith("_silver") else d.name
        results.append((display, d.name, row_count, col_count))
    return results


def _reset_chat():
    for k in ["ga_messages", "ga_agent", "ga_plan", "ga_started", "ga_selected_tables", "ga_plan_confirmed"]:
        st.session_state.pop(k, None)


def _auto_nudge_if_needed(agent: "GoldAgent", response: dict) -> dict:
    """If the agent returned text without calling finalize_plan, nudge it up to 3 times."""
    for _ in range(3):
        if response.get("final_plan"):
            break
        events = response.get("events", [])
        text_events = [e for e in events if e["type"] == "text"]
        if not text_events:
            break  # no text yet — still in tool-call loop, don't nudge
        try:
            nudge_resp = agent.chat(
                "You have all the information needed. "
                "Do NOT ask any more questions. "
                "Call finalize_plan RIGHT NOW with the complete plan including correct join type."
            )
            response["events"] = events + nudge_resp.get("events", [])
            if nudge_resp.get("final_plan"):
                response["final_plan"] = nudge_resp["final_plan"]
                break
        except Exception:
            break
    return response


def _render_tool_event(event: dict):
    name   = event["name"]
    inp    = event.get("input", {})
    result = event.get("result", {})
    label  = f"🔧 `{name}`"
    if name == "read_silver_schema" and inp.get("table_name"):
        label += f" — `{inp['table_name']}`"
    elif name == "finalize_plan":
        label += f" — `{result.get('destination', '')}`"
    with st.expander(label, expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Input")
            st.json(inp, expanded=False)
        with c2:
            st.caption("Result")
            st.json(result, expanded=False)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        "<style>[data-testid='stTextInputPasswordToggle']{display:none}</style>",
        unsafe_allow_html=True,
    )
    st.header("Gold Agent Settings")
    st.caption("Anthropic API Key")
    api_key_input = st.text_input(
        "Anthropic API Key",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Set ANTHROPIC_API_KEY in your .env file, or enter it here.",
        label_visibility="collapsed",
        placeholder="sk-ant-...",
    )
    effective_api_key = api_key_input or os.environ.get("ANTHROPIC_API_KEY", "")
    st.divider()
    if st.button("🔄 New Conversation", use_container_width=True):
        _reset_chat()
        st.rerun()
    st.divider()
    st.caption(
        "The agent uses **claude-haiku-4-5** to understand your requirements "
        "and map them to available Silver tables."
    )


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("🤖 Gold Agent")
st.caption(
    "Fill in the pipeline details, describe your business requirements in plain language, "
    "and the AI will ask targeted questions — then generate a plan for your confirmation."
)

if not effective_api_key:
    st.warning(
        "No Anthropic API key found. Set `ANTHROPIC_API_KEY` in your `.env` file "
        "or enter it in the sidebar."
    )
    st.stop()


# ── Session state init ─────────────────────────────────────────────────────────

if "ga_messages" not in st.session_state:
    st.session_state.ga_messages = []
if "ga_plan" not in st.session_state:
    st.session_state.ga_plan = None
if "ga_started" not in st.session_state:
    st.session_state.ga_started = False

if "ga_agent" not in st.session_state or st.session_state.get("ga_api_key") != effective_api_key:
    st.session_state.ga_agent = GoldAgent(
        silver_path=str(_SILVER_PATH),
        gold_path=str(_GOLD_PATH),
        api_key=effective_api_key,
    )
    st.session_state.ga_api_key = effective_api_key

_chat_started = st.session_state.get("ga_started", False)


# ── Saved Gold Pipelines ───────────────────────────────────────────────────────

saved = [
    p for p in (config.get("pipelines", []) or [])
    if str(p.get("name", "")).endswith("_gold")
]
if saved:
    with st.expander(f"Saved Gold Pipelines ({len(saved)})", expanded=False):
        for p in saved:
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{p.get('name', 'Unnamed')}**")
                src = ", ".join(t for s in p.get("sources", []) for t in s.get("tables", []))
                st.caption(f"Silver tables: {src or '—'}")
            with c2:
                if p.get("last_run"):
                    st.caption(f"Last run: {p['last_run'][:16]}")
            with c3:
                icon = "✅" if p.get("last_status") == "success" else ("❌" if p.get("last_status") == "failed" else "—")
                st.caption(icon)
    st.divider()


# ── 1 — Pipeline Name ──────────────────────────────────────────────────────────

st.subheader("1 — Pipeline Name")
gold_name_raw = st.text_input(
    "Name *",
    key="ga_pipeline_name_input",
    placeholder="e.g. daily_sales",
    help="Required. Pipeline will be saved as `<name>_gold`.",
    disabled=_chat_started,
)
if gold_name_raw:
    gold_pipeline_name = f"{gold_name_raw.strip()}_gold"
    st.caption(f"Pipeline name: **`{gold_pipeline_name}`**")
else:
    gold_pipeline_name = None
    st.caption("Enter a name above. Pipeline will be saved as `<name>_gold`.")

st.divider()


# ── 2 — Silver Tables ─────────────────────────────────────────────────────────

st.subheader("2 — Silver Tables")
silver_tables = _scan_silver_tables()

if not silver_tables:
    st.warning("No Silver tables found in `data/silver/`. Run **Bronze & Silver Pipeline** first.")
    selected_silver = []
else:
    st.caption(
        f"{len(silver_tables)} Silver table(s) available — "
        "select the ones to aggregate into Gold."
    )

    hc = st.columns([0.05, 0.35, 0.18, 0.18, 0.24])
    hc[1].markdown("**Table**")
    hc[2].markdown("**Rows**")
    hc[3].markdown("**Columns**")
    hc[4].markdown("**Directory**")

    selected_silver = []
    frozen = st.session_state.get("ga_selected_tables", [])
    for display, dir_name, row_count, col_count in silver_tables:
        precheck = dir_name in frozen if _chat_started else False
        rc_cols  = st.columns([0.05, 0.35, 0.18, 0.18, 0.24])
        checked  = rc_cols[0].checkbox(
            f"Select {dir_name}",
            key=f"ga_sel_{dir_name}",
            value=precheck,
            label_visibility="collapsed",
            disabled=_chat_started,
        )
        rc_cols[1].markdown(f"`{display}`")
        rc_cols[2].markdown(f"{row_count:,}" if isinstance(row_count, int) else str(row_count))
        rc_cols[3].markdown(str(col_count))
        rc_cols[4].markdown(f"`data/silver/{dir_name}/`")
        if checked:
            selected_silver.append(dir_name)

    # When chat is running, use the frozen selection
    if _chat_started:
        selected_silver = st.session_state.get("ga_selected_tables", selected_silver)

st.divider()


# ── 3 — Schedule ──────────────────────────────────────────────────────────────

st.subheader("3 — Schedule")

gold_schedule_type = st.selectbox(
    "Run Schedule",
    ["Run Once", "Hourly", "Daily", "Weekly", "Custom Cron"],
    key="ga_schedule_type",
    disabled=_chat_started,
)
gold_schedule_config = {"type": gold_schedule_type}

if gold_schedule_type == "Daily":
    g_rt = st.time_input("Run at", value=time(8, 0), key="ga_rt_d")
    gold_schedule_config["time"] = g_rt.strftime("%H:%M")
    st.caption(f"Cron: `{g_rt.minute} {g_rt.hour} * * *`")
elif gold_schedule_type == "Weekly":
    gc1, gc2 = st.columns(2)
    with gc1:
        g_day = st.selectbox(
            "Day",
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            key="ga_weekly_day",
            disabled=_chat_started,
        )
    with gc2:
        g_rt = st.time_input("Run at", value=time(8, 0), key="ga_rt_w")
    g_day_num = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(g_day)
    gold_schedule_config["day"] = g_day
    gold_schedule_config["time"] = g_rt.strftime("%H:%M")
    st.caption(f"Cron: `{g_rt.minute} {g_rt.hour} * * {g_day_num}`")
elif gold_schedule_type == "Hourly":
    st.caption("Cron: `0 * * * *`")
    gold_schedule_config["cron"] = "0 * * * *"
elif gold_schedule_type == "Custom Cron":
    g_cron = st.text_input(
        "Cron Expression", placeholder="0 8 * * 1-5", key="ga_cron_expr",
        disabled=_chat_started,
    )
    gold_schedule_config["cron"] = g_cron
    if g_cron:
        st.caption(f"Expression: `{g_cron}`")

st.divider()


# ── 4 — Business Requirements ─────────────────────────────────────────────────

st.subheader("4 — Business Requirements")

if not _chat_started:
    can_start = bool(gold_pipeline_name) and bool(selected_silver)

    if not gold_pipeline_name:
        st.warning("Enter a pipeline name in Step 1 first.")
    elif not selected_silver:
        st.info("Select at least one Silver table in Step 2 first.")
    else:
        st.caption(
            "Describe what you want the Gold table to contain. "
            "The AI agent will ask targeted follow-up questions if anything is unclear."
        )

    biz_reqs = st.text_area(
        "Describe your Gold table",
        key="ga_biz_reqs",
        height=130,
        placeholder=(
            "e.g. I want a table called customer_value_summary with: "
            "customer_id, customer_name, total_spend (sum of transaction amounts), "
            "transaction_count, is_premium (true if total spend > 300)"
        ),
        disabled=not can_start,
    )

    if can_start:
        if st.button(
            "▶ Start AI Planning",
            type="primary",
            key="ga_start_btn",
            disabled=not biz_reqs.strip(),
        ):
            st.session_state["ga_selected_tables"] = list(selected_silver)
            st.session_state["ga_started"] = True

            # First message — instruct agent to call list_silver_tables then finalize immediately
            tables_str    = ", ".join(f"`{t}`" for t in selected_silver)
            first_message = (
                f"Silver tables for this pipeline: {tables_str}. Use ONLY these tables.\n\n"
                f"Business requirements:\n{biz_reqs.strip()}\n\n"
                f"Instructions: Call list_silver_tables, call read_silver_schema on relevant tables, "
                f"then call finalize_plan immediately with the complete plan. "
                f"Do NOT ask any questions or wait for confirmation — proceed directly to finalize_plan."
            )

            # Display the user's requirements (without the tables prefix)
            st.session_state.ga_messages.append({"role": "user", "content": biz_reqs.strip()})

            agent: GoldAgent = st.session_state.ga_agent
            try:
                response = agent.chat(first_message)
                response  = _auto_nudge_if_needed(agent, response)
            except Exception as exc:
                st.error(f"API error: {exc}")
                st.session_state["ga_started"] = False
                st.stop()

            st.session_state.ga_messages.append({"role": "assistant", "events": response["events"]})
            if response["final_plan"]:
                st.session_state.ga_plan = response["final_plan"]

            st.rerun()
else:
    tables_str = ", ".join(f"`{t}`" for t in st.session_state.get("ga_selected_tables", []))
    st.info(f"Silver tables locked in: {tables_str}  \nUse **New Conversation** in the sidebar to start over.")

st.divider()


# ── 5 — AI Planning Chat ──────────────────────────────────────────────────────

if _chat_started:
    st.subheader("5 — AI Planning")

    for msg in st.session_state.ga_messages:
        role = msg["role"]
        with st.chat_message(role):
            if role == "user":
                st.markdown(msg.get("content", ""))
            else:
                for event in msg.get("events", []):
                    if event["type"] == "tool_call":
                        _render_tool_event(event)
                    elif event["type"] == "text":
                        st.markdown(event["content"])

    _plan_confirmed = st.session_state.get("ga_plan_confirmed", False)
    if _plan_confirmed:
        _chat_placeholder = "Plan confirmed — use New Conversation to start over."
        _chat_disabled = True
    elif st.session_state.ga_plan is not None:
        _chat_placeholder = "Request changes to the plan…"
        _chat_disabled = False
    else:
        _chat_placeholder = "Reply to the agent…"
        _chat_disabled = False

    user_input = st.chat_input(_chat_placeholder, disabled=_chat_disabled)
    if user_input:
        st.session_state.ga_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        agent: GoldAgent = st.session_state.ga_agent
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    response   = agent.chat(user_input)
                    response   = _auto_nudge_if_needed(agent, response)
                except Exception as exc:
                    st.error(f"API error: {exc}")
                    st.stop()
            events     = response["events"]
            final_plan = response["final_plan"]
            for event in events:
                if event["type"] == "tool_call":
                    _render_tool_event(event)
                elif event["type"] == "text":
                    st.markdown(event["content"])

        st.session_state.ga_messages.append({"role": "assistant", "events": events})
        if final_plan:
            st.session_state.ga_plan = final_plan
            st.session_state["ga_plan_confirmed"] = False  # reset on plan update
            st.rerun()

    st.divider()


# ── 6 — Review Plan ───────────────────────────────────────────────────────────

plan = st.session_state.ga_plan
if plan:
    st.subheader("6 — Review Plan")
    st.success("✅ Plan ready — review then confirm to proceed.")

    with st.expander("📋 Plan Details", expanded=True):
        dest = plan.get("destination", "—")
        st.markdown(f"**Destination table:** `data/gold/{dest}/`")
        if plan.get("grain"):
            st.markdown(f"**Grain:** {plan['grain']}")

        sources = plan.get("source_tables", [])
        st.markdown("**Source Silver tables:** " + ", ".join(f"`{t}`" for t in sources))

        if plan.get("joins"):
            st.markdown("**Joins:**")
            for j in plan["joins"]:
                jt = j.get("type", "left").upper()
                if jt == "FULL":
                    jt = "FULL OUTER"
                st.markdown(f"- `{j['fact']}` {jt} JOIN `{j['dim']}` ON `{j['on']}`")

        gb = plan.get("group_by", [])
        if gb:
            st.markdown("**Group by:** " + ", ".join(f"`{c}`" for c in gb))

        aggs = plan.get("aggregations", [])
        if aggs:
            rows = ["| Function | Column | Output |", "|---|---|---|"]
            for a in aggs:
                rows.append(f"| `{a['func']}` | `{a['col']}` | `{a['alias']}` |")
            st.markdown("\n".join(rows))

        for dc in plan.get("derived_columns", []):
            st.markdown(f"**Derived:** `{dc['column']}` = `{dc['expression']}`")

        for f in plan.get("filters", []):
            st.markdown(f"**Filter:** `{f}`")

        if plan.get("output_schema"):
            st.markdown("**Output schema:**")
            hdr = ["| Column | Type | Source |", "|---|---|---|"]
            for col in plan["output_schema"]:
                hdr.append(f"| `{col['column']}` | `{col['type']}` | {col.get('source', '')} |")
            st.markdown("\n".join(hdr))

    st.caption("Not satisfied? Type your change in the chat below — the agent will revise and resubmit the plan.")
    st.markdown("---")
    gold_confirmed = st.checkbox(
        "✅ I confirm this plan — proceed to Run Gold",
        key="ga_plan_confirmed",
    )

    if gold_confirmed:
        st.divider()
        st.subheader("7 — Run Gold")

        col_run, col_discard = st.columns([3, 1])
        with col_run:
            run_clicked = st.button(
                "▶ Run Gold", type="primary", key="ga_run_btn", use_container_width=True
            )
        with col_discard:
            if st.button("✕ Discard Plan", key="ga_discard_btn", use_container_width=True):
                st.session_state.ga_plan = None
                st.rerun()

        if run_clicked:
            # Generate PySpark execution code from the plan via LLM
            agent: GoldAgent = st.session_state.ga_agent
            with st.spinner("Generating PySpark execution script…"):
                try:
                    script = agent.generate_execution_code(plan)
                except Exception as exc:
                    st.error(f"Code generation failed: {exc}")
                    st.stop()

            with st.expander("🔍 Generated PySpark script", expanded=False):
                st.code(script, language="python")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as tf:
                tf.write(script)
                script_file = tf.name

            run_env   = {**os.environ, "PYTHONUNBUFFERED": "1"}
            log_box   = st.empty()
            log_lines = []

            proc = subprocess.Popen(
                [sys.executable, script_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=run_env,
                cwd=str(_PROJECT_ROOT),
            )
            while True:
                line = proc.stdout.readline()
                if line == "" and proc.poll() is not None:
                    break
                if line:
                    log_lines.append(line.rstrip())
                    log_box.code("\n".join(log_lines[-40:]), language="text")
            rc = proc.returncode

            # Derive pipeline name from frozen session state
            _frozen_name_raw = st.session_state.get("ga_pipeline_name_input", "")
            _pipeline_name   = f"{_frozen_name_raw.strip()}_gold" if _frozen_name_raw else gold_pipeline_name

            if rc == 0:
                st.success(f"Gold complete! Table `{plan['destination']}` written to `data/gold/`")
                config.reload()
                pipelines = config.get("pipelines", []) or []
                run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
                entry = {
                    "name": _pipeline_name,
                    "schedule": gold_schedule_type.lower().replace(" ", "_"),
                    "schedule_config": gold_schedule_config,
                    "sources": [{"source_type": "silver", "tables": plan.get("source_tables", [])}],
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "last_run": run_ts,
                    "last_status": "success",
                }
                names = [p.get("name") for p in pipelines]
                if _pipeline_name in names:
                    pipelines[names.index(_pipeline_name)] = entry
                else:
                    pipelines.append(entry)
                config.set("pipelines", pipelines)
                config.save()
                st.info(f"Pipeline **{_pipeline_name}** saved to config.yaml")

                doc = agent_gold_doc(
                    pipeline_name=_pipeline_name,
                    plan=plan,
                    silver_path=_SILVER_PATH,
                    gold_path=_GOLD_PATH,
                    schedule_config=gold_schedule_config,
                    run_ts=run_ts,
                    status="success",
                )
                doc_path = save_pipeline_doc(_PROJECT_ROOT, _pipeline_name, doc)
                st.caption(f"📄 Pipeline doc saved: `{doc_path}`")

                _reset_chat()
            else:
                st.error("Run finished with errors. Check the log above.")
                config.reload()
                pipelines = config.get("pipelines", []) or []
                names     = [p.get("name") for p in pipelines]
                run_ts    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
                if _pipeline_name and _pipeline_name in names:
                    pipelines[names.index(_pipeline_name)]["last_run"]    = run_ts
                    pipelines[names.index(_pipeline_name)]["last_status"] = "failed"
                    config.set("pipelines", pipelines)
                    config.save()
