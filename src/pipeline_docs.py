"""
Generates a Markdown documentation file for a pipeline after a successful run.
Saved to pipelines/<pipeline_name>.md at the project root.

Uses pyarrow for schema reads — no Spark startup required.
"""

from pathlib import Path

try:
    import pyarrow.parquet as pq

    _HAS_PYARROW = True
except ImportError:
    _HAS_PYARROW = False


# ── Schema helpers ─────────────────────────────────────────────────────────────


def _read_parquet_meta(directory):
    """Return (columns, row_count) for the first Parquet file found in `directory`."""
    if not _HAS_PYARROW:
        return [], "pyarrow not installed"
    parts = sorted(Path(directory).glob("**/*.parquet"))
    if not parts:
        return [], 0
    try:
        schema = pq.read_schema(str(parts[0]))
        pf = pq.ParquetFile(str(parts[0]))
        columns = [(schema.names[i], str(schema.types[i])) for i in range(len(schema.names))]
        return columns, pf.metadata.num_rows
    except Exception as exc:
        return [], f"error: {exc}"


def _schema_table(columns):
    if not columns:
        return "_No columns found._"
    rows = ["| Column | Type |", "|---|---|"]
    for name, dtype in columns:
        rows.append(f"| `{name}` | `{dtype}` |")
    return "\n".join(rows)


def _schedule_summary(schedule_config):
    stype = schedule_config.get("type", "Run Once")
    if stype == "Run Once":
        return "Run once (manual trigger)"
    if stype == "Hourly":
        return "Every hour  `0 * * * *`"
    if stype == "Daily":
        t = schedule_config.get("time", "08:00")
        h, m = t.split(":")
        return f"Daily at {t}  `{m} {h} * * *`"
    if stype == "Weekly":
        day = schedule_config.get("day", "Monday")
        t = schedule_config.get("time", "08:00")
        h, m = t.split(":")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dn = days.index(day) if day in days else 0
        return f"Weekly on {day} at {t}  `{m} {h} * * {dn}`"
    if stype == "Custom Cron":
        expr = schedule_config.get("cron", "")
        return f"Custom cron: `{expr}`"
    return stype


def _safe_filename(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


# ── Document generators ────────────────────────────────────────────────────────


def bronze_silver_doc(
    pipeline_name,
    sources,
    bronze_path,
    silver_path,
    bronze_names,
    schedule_config,
    run_ts,
    status="success",
):
    bronze_path = Path(bronze_path)
    silver_path = Path(silver_path)
    status_badge = "✅ Passed" if status == "success" else "❌ Failed"

    lines = [
        f"# Pipeline: {pipeline_name}",
        "",
        "**Type:** Bronze & Silver  ",
        f"**Last run:** {run_ts}  ",
        f"**Last run status:** {status_badge}  ",
        f"**Schedule:** {_schedule_summary(schedule_config)}  ",
        "",
        "---",
        "",
        "## Overview",
        "",
        "This pipeline ingests raw data from the configured sources into the **Bronze** "
        "layer (faithful copy, no transforms), then promotes it to the **Silver** layer "
        "(snake_case column names, explicit type casts, null-filtered primary keys).",
        "",
        "```",
        "Source → data/bronze/<table>_bronze/ → data/silver/<table>_silver/",
        "```",
        "",
        "---",
        "",
        "## Sources",
        "",
    ]

    for i, s in enumerate(sources, 1):
        stype = s.get("source_type", "unknown")
        mode = s.get("mode", "full")
        conn = s.get("connection", {})
        tables = s.get("tables", [])

        lines.append(f"### Source {i} — {stype.upper()}")
        if stype == "postgresql":
            host = conn.get("host", "localhost")
            port = conn.get("port", 5432)
            db = conn.get("database", "")
            lines.append(f"**Connection:** `{host}:{port}/{db}`  ")
        lines.append(f"**Load mode:** {mode}  ")
        lines.append("")
        lines.append("| Source Table | Bronze Directory |")
        lines.append("|---|---|")
        for t in tables:
            stem = Path(t).stem if stype == "file" else t.split(".")[-1]
            lines.append(f"| `{t}` | `data/bronze/{stem}_bronze/` |")
        lines.append("")

    lines += [
        "---",
        "",
        "## Bronze Layer",
        "",
        "_Raw, unmodified copy of source data. Column names and types match the source._",
        "",
    ]

    for bn in bronze_names:
        cols, row_count = _read_parquet_meta(bronze_path / bn)
        rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
        lines.append(f"### `data/bronze/{bn}/`")
        lines.append(f"**Rows:** {rc_str}  ")
        lines.append("")
        lines.append(_schema_table(cols))
        lines.append("")

    lines += [
        "---",
        "",
        "## Silver Layer",
        "",
        "_Cleaned, typed, snake_case. Every row has a non-null primary key._",
        "",
    ]

    for bn in bronze_names:
        sn = f"{bn[:-7]}_silver" if bn.endswith("_bronze") else f"{bn}_silver"
        cols, row_count = _read_parquet_meta(silver_path / sn)
        rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
        lines.append(f"### `data/silver/{sn}/`")
        lines.append(f"**Rows:** {rc_str}  ")
        if cols:
            pk_candidates = [c for c, _ in cols if c.endswith("_id")]
            if pk_candidates:
                lines.append(f"**Inferred primary key:** `{pk_candidates[0]}`  ")
        lines.append("")
        lines.append(_schema_table(cols))
        lines.append("")

    lines += [
        "---",
        "",
        "## Data Flow",
        "",
        "```",
    ]
    for bn in bronze_names:
        sn = f"{bn[:-7]}_silver" if bn.endswith("_bronze") else f"{bn}_silver"
        lines.append(f"Source  →  data/bronze/{bn}/  →  data/silver/{sn}/")
    lines += [
        "```",
        "",
        "---",
        "",
        "_Generated automatically by the Pipeline Runner after each run._",
    ]

    return "\n".join(lines)


def gold_doc(
    pipeline_name,
    silver_tables,
    silver_path,
    gold_path,
    gold_plan,
    schedule_config,
    run_ts,
    status="success",
):
    silver_path = Path(silver_path)
    gold_path = Path(gold_path)
    status_badge = "✅ Passed" if status == "success" else "❌ Failed"

    lines = [
        f"# Pipeline: {pipeline_name}",
        "",
        "**Type:** Gold  ",
        f"**Last run:** {run_ts}  ",
        f"**Last run status:** {status_badge}  ",
        f"**Schedule:** {_schedule_summary(schedule_config)}  ",
        "",
        "---",
        "",
        "## Overview",
        "",
        "This pipeline reads from the Silver layer and produces business-ready Gold "
        "aggregation tables. Gold tables group and aggregate Silver data to answer "
        "specific business questions.",
        "",
        "```",
        "data/silver/<table>_silver/  →  data/gold/<table>_summary/",
        "```",
        "",
        "---",
        "",
        "## Silver Inputs",
        "",
        "| Silver Table | Rows | Columns |",
        "|---|---|---|",
    ]

    for st_name in silver_tables:
        cols, row_count = _read_parquet_meta(silver_path / st_name)
        rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
        lines.append(f"| `{st_name}` | {rc_str} | {len(cols)} |")

    lines += ["", "---", "", "## Gold Layer", ""]

    plan_by_source = {}
    if gold_plan and gold_plan.get("tables"):
        for tp in gold_plan["tables"]:
            plan_by_source[tp["source_silver"]] = tp

    for st_name in silver_tables:
        base = st_name[:-7] if st_name.endswith("_silver") else st_name
        gold_table = f"{base}_summary"
        tp = plan_by_source.get(st_name)

        cols, row_count = _read_parquet_meta(gold_path / gold_table)
        rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)

        lines.append(f"### `data/gold/{gold_table}/`")
        lines.append(f"**Rows:** {rc_str}  ")

        if tp:
            lines.append(f"**Grain:** {tp.get('grain', '—')}  ")
            if tp.get("group_by"):
                lines.append("**Group by:** " + ", ".join(f"`{c}`" for c in tp["group_by"]) + "  ")
            if tp.get("filters"):
                lines.append("**Business rules applied:**  ")
                for r in tp["filters"]:
                    lines.append(f"- {r}")
            if tp.get("joins"):
                lines.append("**Joins:**  ")
                for j in tp["joins"]:
                    lines.append(f"- `{j['fact']}` LEFT JOIN `{j['dim']}` ON `{j['on']}`")

        lines.append("")

        if tp and tp.get("aggregations"):
            lines.append("**Aggregations:**")
            lines.append("")
            lines.append("| Function | Input Column | Output Column |")
            lines.append("|---|---|---|")
            for agg in tp["aggregations"]:
                lines.append(f"| `{agg['func']}` | `{agg['col']}` | `{agg['alias']}` |")
            lines.append("")

        lines.append("**Output schema:**")
        lines.append("")
        lines.append(_schema_table(cols))
        lines.append("")

    lines += [
        "---",
        "",
        "## Data Flow",
        "",
        "```",
    ]
    for st_name in silver_tables:
        base = st_name[:-7] if st_name.endswith("_silver") else st_name
        lines.append(f"data/silver/{st_name}/  →  data/gold/{base}_summary/")
    lines += [
        "```",
        "",
        "---",
        "",
        "_Generated automatically by the Pipeline Runner after each run._",
    ]

    return "\n".join(lines)


def agent_gold_doc(
    pipeline_name,
    plan,
    silver_path,
    gold_path,
    schedule_config,
    run_ts,
    status="success",
):
    """Generate pipeline doc for a Gold table designed by the Gold Agent chatbot."""
    silver_path = Path(silver_path)
    gold_path = Path(gold_path)
    status_badge = "✅ Passed" if status == "success" else "❌ Failed"

    destination = plan.get("destination", pipeline_name)
    source_tables = plan.get("source_tables", [])
    joins = plan.get("joins", [])
    group_by = plan.get("group_by", [])
    aggregations = plan.get("aggregations", [])
    derived_columns = plan.get("derived_columns", [])
    filters = plan.get("filters", [])
    grain = plan.get("grain", "")

    lines = [
        f"# Pipeline: {pipeline_name}",
        "",
        "**Type:** Gold (Agent-designed)  ",
        f"**Last run:** {run_ts}  ",
        f"**Last run status:** {status_badge}  ",
        f"**Schedule:** {_schedule_summary(schedule_config)}  ",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"Gold table **`{destination}`** was designed through a Gold Agent conversation. "
        "It aggregates Silver layer data to answer a specific business question.",
        "",
        "```",
    ]
    for st_name in source_tables:
        lines.append(f"data/silver/{st_name}/  →  data/gold/{destination}/")
    lines += ["```", "", "---", "", "## Source Silver Tables", ""]

    for st_name in source_tables:
        cols, row_count = _read_parquet_meta(silver_path / st_name)
        rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
        lines.append(f"### `data/silver/{st_name}/`")
        lines.append(f"**Rows:** {rc_str}  ")
        lines.append("")
        lines.append(_schema_table(cols))
        lines.append("")

    lines += ["---", "", "## Gold Table", "", f"### `data/gold/{destination}/`", ""]

    if grain:
        lines.append(f"**Grain:** {grain}  ")
    if group_by:
        lines.append("**Group by:** " + ", ".join(f"`{c}`" for c in group_by) + "  ")
    if joins:
        lines.append("**Joins:**  ")
        for j in joins:
            lines.append(f"- `{j['fact']}` LEFT JOIN `{j['dim']}` ON `{j['on']}`")
    if filters:
        lines.append("**Business rules applied:**  ")
        for r in filters:
            lines.append(f"- {r}")

    lines.append("")

    if aggregations:
        lines += ["**Aggregations:**", "", "| Function | Input Column | Output Column |", "|---|---|---|"]
        for agg in aggregations:
            lines.append(f"| `{agg['func']}` | `{agg['col']}` | `{agg['alias']}` |")
        lines.append("")

    if derived_columns:
        lines += ["**Derived columns:**", "", "| Column | Expression |", "|---|---|"]
        for dc in derived_columns:
            lines.append(f"| `{dc['column']}` | `{dc['expression']}` |")
        lines.append("")

    cols, row_count = _read_parquet_meta(gold_path / destination)
    rc_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
    lines.append(f"**Output rows:** {rc_str}  ")
    lines.append("")
    lines.append("**Output schema:**")
    lines.append("")
    lines.append(_schema_table(cols))
    lines += [
        "",
        "---",
        "",
        "_Generated automatically by the Gold Agent after each run._",
    ]

    return "\n".join(lines)


# ── Save ───────────────────────────────────────────────────────────────────────


def save_pipeline_doc(project_root, pipeline_name, content):
    """Write content to pipelines/<pipeline_name>.md. Returns the file path."""
    docs_dir = Path(project_root) / "pipelines"
    docs_dir.mkdir(exist_ok=True)
    path = docs_dir / f"{_safe_filename(pipeline_name)}.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


def load_pipeline_doc(project_root, pipeline_name):
    """Return the markdown content for a pipeline, or None if not found."""
    path = Path(project_root) / "pipelines" / f"{_safe_filename(pipeline_name)}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
