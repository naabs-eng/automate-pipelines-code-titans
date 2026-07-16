"""
Gold Builder chatbot utilities — pure Python, no Streamlit, no API.

Used by pages/3_Gold_Builder.py to power the hybrid rule-based chat
assistant for the Business Requirements step.
"""
import re
from pathlib import Path


# ── Schema parsing ─────────────────────────────────────────────────────────────

def parse_destination_schema(text: str) -> dict:
    """
    Parse user input like:
        "customer_value_summary: customer_id (INT), total_spend (DECIMAL), is_premium (BOOLEAN)"
    or
        "I want a table called customer_value_summary with customer_id, total_spend"

    Returns:
        {
          "destination": str | None,
          "columns": [{"name": str, "type": str | None}]
        }
    """
    text = text.strip()

    # Extract destination name
    destination = None
    # Pattern 1: "word:" at the start
    m = re.match(r'^(\w+)\s*:', text)
    if m:
        destination = m.group(1)
    else:
        # Pattern 2: "called X" or "named X" or "table X"
        m = re.search(r'\b(?:called|named|table)\s+(\w+)', text, re.IGNORECASE)
        if m:
            destination = m.group(1)
        else:
            # Pattern 3: first word/identifier before "with" or before the columns
            m = re.match(r'^(\w+)\b', text)
            if m:
                destination = m.group(1)

    # Extract columns: name (TYPE) patterns
    typed_cols = re.findall(r'(\w+)\s*\(([^)]+)\)', text)
    columns = []
    if typed_cols:
        for name, dtype in typed_cols:
            if name.lower() not in ("table", "called", "named", "with"):
                columns.append({"name": name, "type": dtype.strip().upper()})
    else:
        # Fallback: try comma-separated bare identifiers after the colon
        after_colon = re.split(r':', text, maxsplit=1)[-1] if ':' in text else text
        # Also try after "with"
        after_with = re.split(r'\bwith\b', after_colon, maxsplit=1, flags=re.IGNORECASE)[-1]
        bare = re.findall(r'\b([a-zA-Z_]\w*)\b', after_with)
        for name in bare:
            if name.lower() not in (
                "table", "called", "named", "with", "and", "the", "a", "an",
                "columns", "column", "fields", "field", "i", "want", "need"
            ) and name != destination:
                columns.append({"name": name, "type": None})

    return {"destination": destination, "columns": columns}


# ── Silver schema loading ──────────────────────────────────────────────────────

def load_silver_schemas(tables: list, silver_path: str) -> dict:
    """
    Read pyarrow schemas for selected Silver table directories.

    Returns:
        {table_name: [{"name": str, "type": str}]}
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return {}

    result = {}
    base = Path(silver_path)
    for table in tables:
        table_dir = base / table
        if not table_dir.exists():
            continue
        parts = sorted(table_dir.glob("**/*.parquet"))
        if not parts:
            continue
        try:
            schema = pq.read_schema(str(parts[0]))
            result[table] = [
                {"name": schema.names[i], "type": str(schema.types[i])}
                for i in range(len(schema.names))
                if not schema.names[i].startswith("_")
            ]
        except Exception:
            result[table] = []
    return result


# ── Column mapping ─────────────────────────────────────────────────────────────

# Aggregation function keywords → their canonical function names
_AGG_PREFIXES = {
    "total_": "SUM",
    "sum_": "SUM",
    "count_": "COUNT",
    "num_": "COUNT",
    "cnt_": "COUNT",
    "avg_": "AVG",
    "average_": "AVG",
    "mean_": "AVG",
    "max_": "MAX",
    "maximum_": "MAX",
    "min_": "MIN",
    "minimum_": "MIN",
    "last_": "MAX",
    "latest_": "MAX",
    "first_": "MIN",
    "earliest_": "MIN",
}

# Prefixes that operate on temporal (timestamp/date/string) columns, not just numeric
_TEMPORAL_AGG_PREFIXES = {"last_", "latest_", "first_", "earliest_"}

# Types considered numeric for aggregation candidates
_NUMERIC_TYPES = {"int8", "int16", "int32", "int64", "float", "double",
                  "decimal", "float32", "float64"}


def _is_numeric(dtype: str) -> bool:
    dt = dtype.lower()
    return any(t in dt for t in _NUMERIC_TYPES)


def _all_silver_columns(silver_schemas: dict) -> list:
    """Flat list of {"name", "type", "table"} across all Silver tables."""
    cols = []
    for table, schema in silver_schemas.items():
        for col in schema:
            cols.append({"name": col["name"], "type": col["type"], "table": table})
    return cols


def map_column(col_name: str, silver_schemas: dict) -> dict:
    """
    Classify a requested output column against available Silver schemas.

    Returns a dict with at minimum:
        {"status": str, "col": col_name, ...}

    Status values:
        "direct"                — exact match, resolved as group_by
        "aggregation"           — auto-resolved aggregation (func+col known)
        "aggregation_candidates"— prefix matched but multiple source cols to pick from
        "derived_boolean"       — is_/has_/flag_ prefix → need condition
        "fuzzy"                 — partial name match → confirm with user
        "not_found"             — no match found
    """
    all_cols = _all_silver_columns(silver_schemas)
    col_lower = col_name.lower()

    # ── COUNT(*) suffix shorthand ─────────────────────────────────────────────
    # total_transactions_count, order_count, num_records, etc. → COUNT(*)
    _stripped = col_lower
    for _p in _AGG_PREFIXES:
        if col_lower.startswith(_p):
            _stripped = col_lower[len(_p):]
            break
    if (
        _stripped.endswith("_count")
        or _stripped in ("count", "record_count", "row_count", "records")
        or col_lower in ("total_count", "count", "record_count", "row_count")
    ):
        return {
            "status": "aggregation",
            "col": col_name,
            "func": "COUNT",
            "source_col": "*",
            "alias": col_name,
        }

    # ── Direct exact match ────────────────────────────────────────────────────
    direct_matches = [c for c in all_cols if c["name"].lower() == col_lower]
    if direct_matches:
        tables = list({c["table"] for c in direct_matches})
        return {
            "status": "direct",
            "col": col_name,
            "source_tables": tables,
        }

    # ── Aggregation pattern match ─────────────────────────────────────────────
    for prefix, func in _AGG_PREFIXES.items():
        if col_lower.startswith(prefix):
            remainder = col_lower[len(prefix):]  # e.g. "amount", "price"
            is_temporal = prefix in _TEMPORAL_AGG_PREFIXES

            # COUNT(*) special case
            if prefix in ("count_", "num_", "cnt_"):
                # Look for a matching column; if none found, fall back to COUNT(*)
                candidates = [
                    c for c in all_cols
                    if c["name"].lower() == remainder or remainder in c["name"].lower()
                ]
                if not candidates:
                    return {
                        "status": "aggregation",
                        "col": col_name,
                        "func": "COUNT",
                        "source_col": "*",
                        "alias": col_name,
                    }

            # Exact match: numeric for standard prefixes, any type for temporal
            exact = [
                c for c in all_cols
                if c["name"].lower() == remainder
                and (is_temporal or _is_numeric(c["type"]))
            ]
            if len(exact) == 1:
                return {
                    "status": "aggregation",
                    "col": col_name,
                    "func": func,
                    "source_col": exact[0]["name"],
                    "source_table": exact[0]["table"],
                    "alias": col_name,
                }
            if len(exact) > 1:
                return {
                    "status": "aggregation_candidates",
                    "col": col_name,
                    "func": func,
                    "candidates": [
                        {"col": c["name"], "table": c["table"], "type": c["type"]}
                        for c in exact
                    ],
                    "alias": col_name,
                }

            # Fuzzy: name contains remainder, same type relaxation
            fuzzy_num = [
                c for c in all_cols
                if remainder in c["name"].lower()
                and (is_temporal or _is_numeric(c["type"]))
            ]
            if fuzzy_num:
                return {
                    "status": "aggregation_candidates",
                    "col": col_name,
                    "func": func,
                    "candidates": [
                        {"col": c["name"], "table": c["table"], "type": c["type"]}
                        for c in fuzzy_num[:5]
                    ],
                    "alias": col_name,
                }

            # Fallback for temporal: show all timestamp/date/string cols as candidates
            if is_temporal:
                temporal_all = [
                    c for c in all_cols
                    if any(t in c["type"].lower() for t in ("timestamp", "date", "string"))
                ]
                if temporal_all:
                    return {
                        "status": "aggregation_candidates",
                        "col": col_name,
                        "func": func,
                        "candidates": [
                            {"col": c["name"], "table": c["table"], "type": c["type"]}
                            for c in temporal_all[:5]
                        ],
                        "alias": col_name,
                    }

            # Fallback for SUM/AVG: show all numeric cols instead of falling to not_found
            if func in ("SUM", "AVG"):
                all_numeric = [c for c in all_cols if _is_numeric(c["type"])]
                if all_numeric:
                    return {
                        "status": "aggregation_candidates",
                        "col": col_name,
                        "func": func,
                        "candidates": [
                            {"col": c["name"], "table": c["table"], "type": c["type"]}
                            for c in all_numeric[:5]
                        ],
                        "alias": col_name,
                    }

    # ── Derived boolean ───────────────────────────────────────────────────────
    if any(col_lower.startswith(p) for p in ("is_", "has_", "flag_")):
        return {
            "status": "derived_boolean",
            "col": col_name,
        }

    # ── Fuzzy substring match ─────────────────────────────────────────────────
    fuzzy = [c for c in all_cols if col_lower in c["name"].lower() or c["name"].lower() in col_lower]
    if fuzzy:
        return {
            "status": "fuzzy",
            "col": col_name,
            "candidates": [
                {"col": c["name"], "table": c["table"], "type": c["type"]}
                for c in fuzzy[:4]
            ],
        }

    return {
        "status": "not_found",
        "col": col_name,
        "available": [{"col": c["name"], "table": c["table"]} for c in all_cols],
    }


# ── Join key detection ─────────────────────────────────────────────────────────

def detect_join_keys(silver_schemas: dict) -> list:
    """
    Return column names that appear in 2+ Silver tables (likely join keys).
    Priority order: *_id columns first, then others.
    """
    from collections import Counter
    counts = Counter()
    for schema in silver_schemas.values():
        for col in schema:
            counts[col["name"]] += 1

    shared = [name for name, cnt in counts.items() if cnt >= 2]
    # Put _id columns first
    id_cols = sorted([c for c in shared if c.endswith("_id")])
    other_cols = sorted([c for c in shared if not c.endswith("_id")])
    return id_cols + other_cols


# ── Requirements text builder ──────────────────────────────────────────────────

def build_requirements_text(
    destination: str,
    group_by: list,
    aggregations: list,
    derived_columns: list,
    joins: list,
    filters: list,
    requested_columns: list,
    grain: str = "",
    gb_aliases: dict = None,
) -> str:
    """
    Build a requirements text string compatible with analyse_gold.py parse_requirements().

    Args:
        destination: Gold table name
        group_by: list of Silver column name strings
        aggregations: [{"func": str, "col": str, "alias": str}]
        derived_columns: [{"col": str, "condition": str}]
        joins: [{"fact": str, "dim": str, "on": str}]
        filters: list of SQL filter strings
        requested_columns: [{"name": str, "type": str | None}] — for output schema
        gb_aliases: {silver_col: user_requested_name} — emitted as "col AS alias" in Dimensions
    """
    if gb_aliases is None:
        gb_aliases = {}
    lines = []

    lines.append("Destination table name:")
    lines.append(f"  - {destination}")
    lines.append("")

    if grain:
        lines.append("Target grain (one row = ?):")
        lines.append(f"  - {grain}")
        lines.append("")

    if group_by:
        lines.append("Dimensions:")
        dim_parts = []
        for col in group_by:
            alias = gb_aliases.get(col)
            if alias and alias != col:
                dim_parts.append(f"{col} AS {alias}")
            else:
                dim_parts.append(col)
        lines.append("  - " + ", ".join(dim_parts))
        lines.append("")

    if aggregations:
        lines.append("Measures:")
        for agg in aggregations:
            func = agg.get("func", "SUM")
            col = agg.get("source_col") or agg.get("col", "*")
            alias = agg.get("alias", col)
            lines.append(f"  - {func}({col}) as {alias}")
        lines.append("")

    if joins:
        lines.append("Joins:")
        for j in joins:
            lines.append(f"  - {j['fact']} -> {j['dim']} (on {j['on']})")
        lines.append("")

    if filters or derived_columns:
        lines.append("Business rules:")
        for f in filters:
            lines.append(f"  - {f}")
        for dc in derived_columns:
            col = dc.get("col", "")
            cond = dc.get("condition", "")
            lines.append(f"  - {col} = {cond}")
        lines.append("")

    if requested_columns:
        lines.append("Output schema:")
        for col in requested_columns:
            name = col.get("name", "")
            dtype = col.get("type", "")
            if dtype:
                lines.append(f"  - {name} ({dtype})")
            else:
                lines.append(f"  - {name}")
        lines.append("")

    return "\n".join(lines)


# ── Requirements text parser ───────────────────────────────────────────────────

def parse_requirements_to_plan(text: str, source_tables: list) -> dict:
    """
    Parse a requirements text (produced by build_requirements_text) back into
    an agent-plan dict compatible with run_silver_gold.run_agent_plan().

    Handles AS aliases in Dimensions: 'first_name AS customer_name'
    Returns column_aliases list so run_agent_plan can apply withColumnRenamed.
    """
    destination = ""
    grain = ""
    group_by = []
    aggregations = []
    derived_columns = []
    joins = []
    filters = []
    column_aliases = []

    section = None

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        lower = stripped.lower()

        # Section headers (detect by start of line, colon optional)
        if lower.startswith("destination table name"):
            section = "destination"
            continue
        if lower.startswith("target grain"):
            section = "grain"
            continue
        if lower.startswith("dimensions"):
            section = "dimensions"
            continue
        if lower.startswith("measures"):
            section = "measures"
            continue
        if lower.startswith("joins"):
            section = "joins"
            continue
        if lower.startswith("business rules"):
            section = "filters"
            continue
        if lower.startswith("output schema"):
            section = "output_schema"
            continue

        # Values — lines starting with "- "
        if not stripped.startswith("- "):
            continue
        val = stripped[2:].strip()
        if not val:
            continue

        if section == "destination":
            destination = val
        elif section == "grain":
            grain = val
        elif section == "dimensions":
            for part in val.split(","):
                part = part.strip()
                if not part:
                    continue
                as_m = re.match(r"(\w+)\s+(?:AS|as)\s+(\w+)", part)
                if as_m:
                    silver_col = as_m.group(1)
                    alias = as_m.group(2)
                    group_by.append(silver_col)
                    if silver_col != alias:
                        column_aliases.append({"from": silver_col, "to": alias})
                else:
                    group_by.append(part)
        elif section == "measures":
            # Use rfind to handle nested parens: SUM(datediff(a, b)) as alias
            _as_idx = val.rfind(" as ")
            if _as_idx == -1:
                _as_idx = val.rfind(" AS ")
            if _as_idx != -1:
                _expr = val[:_as_idx].strip()
                _alias = val[_as_idx + 4:].strip()
                _fp = _expr.find("(")
                _lp = _expr.rfind(")")
                if _fp > 0 and _lp > _fp and re.match(r'^\w+$', _expr[:_fp].strip()):
                    aggregations.append({
                        "func": _expr[:_fp].strip().upper(),
                        "col": _expr[_fp + 1:_lp].strip(),
                        "alias": _alias,
                    })
        elif section == "joins":
            # "fact -> dim (on key)" or with arrow variants
            m = re.match(r"(\w+)\s*[-→>]+\s*(\w+)\s*\(on\s+(\w+)\)", val, re.IGNORECASE)
            if m:
                joins.append({
                    "fact": m.group(1),
                    "dim": m.group(2),
                    "on": m.group(3),
                    "type": "left",
                })
        elif section == "filters":
            # derived boolean: is_/has_/flag_ col = expr
            dc_m = re.match(r"((?:is_|has_|flag_)\w+)\s*=\s*(.+)", val, re.IGNORECASE)
            if dc_m:
                derived_columns.append({
                    "column": dc_m.group(1),
                    "expression": dc_m.group(2).strip(),
                    "type": "boolean",
                })
            else:
                filters.append(val)

    return {
        "destination": destination,
        "source_tables": list(source_tables),
        "joins": joins,
        "group_by": group_by,
        "aggregations": aggregations,
        "derived_columns": derived_columns,
        "filters": filters,
        "grain": grain,
        "column_aliases": column_aliases,
    }