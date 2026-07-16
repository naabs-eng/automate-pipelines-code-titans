"""
Reads Silver Parquet schemas (via pyarrow — no Spark startup) and optional
business requirements text, then outputs a structured Gold plan as JSON.

Used by the Pipeline Runner UI to present a confirm-before-run plan to the user.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config_manager import ConfigManager  # noqa: E402

try:
    import pyarrow.parquet as pq
except ImportError:
    print(json.dumps({"error": "pyarrow not installed — run: pip install pyarrow"}))
    sys.exit(1)

_NUMERIC_SUBTYPES = {
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "float",
    "float16",
    "float32",
    "float64",
    "double",
    "decimal",
}
_DATE_SUBTYPES = {"date32", "date64", "timestamp", "time32", "time64"}
_AUDIT_PREFIX = "_"

# Keywords are matched as substrings of the lowercased line (case-insensitive contains).
_SECTION_KEYS = {
    "kpi": ["kpi", "kpis", "metric", "metrics"],
    "grain": ["grain", "target grain", "granularity"],
    "dimensions": ["dimension", "dimensions", "group by", "groupby", "slice by"],
    "measures": ["measure", "measures", "aggregate", "aggregation", "aggregations"],
    "joins": ["joins needed", "join needed", "joins:", "joins", "join"],
    "rules": ["business rule", "specific business rule", "rule", "filter"],
    "destination": ["destination table", "target gold table", "table name", "output table", "dest"],
    "output_schema": ["output schema", "output columns", "target schema", "schema"],
}

# Aggregation prefix patterns → (func, base_col_group)
_AGG_PATTERNS = [
    (re.compile(r"^total_(.+)$"), "SUM"),
    (re.compile(r"^sum_(.+)$"), "SUM"),
    (re.compile(r"^(.+)_total$"), "SUM"),
    (re.compile(r"^avg_(.+)$"), "AVG"),
    (re.compile(r"^average_(.+)$"), "AVG"),
    (re.compile(r"^(.+)_average$"), "AVG"),
    (re.compile(r"^(.+)_count$"), "COUNT"),
    (re.compile(r"^count_(.+)$"), "COUNT"),
    (re.compile(r"^total_(.+)_count$"), "COUNT"),
    (re.compile(r"^(.+)_transactions$"), "COUNT"),
    (re.compile(r"^last_(.+)$"), "MAX"),
    (re.compile(r"^latest_(.+)$"), "MAX"),
    (re.compile(r"^max_(.+)$"), "MAX"),
    (re.compile(r"^min_(.+)$"), "MIN"),
]


# ── Schema reading ────────────────────────────────────────────────────────────


def read_schema(silver_dir):
    parts = sorted(Path(silver_dir).glob("**/*.parquet"))
    if not parts:
        return None
    try:
        schema = pq.read_schema(str(parts[0]))
        return [{"name": schema.names[i], "type": str(schema.types[i])} for i in range(len(schema.names))]
    except Exception as e:
        return {"error": str(e)}


def classify_field(name, type_str):
    nl = name.lower()
    tl = type_str.lower()
    if nl.startswith(_AUDIT_PREFIX):
        return "audit"
    if nl.endswith("_id") or nl == "id":
        return "id"
    if any(d in tl for d in _DATE_SUBTYPES) or any(
        k in nl for k in ("date", "_at", "_time", "timestamp", "created", "updated", "_day", "_on")
    ):
        return "date"
    if any(n in tl for n in _NUMERIC_SUBTYPES):
        return "measure"
    return "dimension"


# ── Requirements parsing ──────────────────────────────────────────────────────


def parse_requirements(req_text):
    """
    Parse free-form requirements text into structured hints.

    Improvements over v1:
    - Substring keyword matching (handles "Target Gold Table Name:", numbered lists, etc.)
    - Handles "Key: value" bullets (extracts value to the matched section)
    - Accepts numbered lists (1. 2. 3.) as bullets
    - Collects output_schema bullets separately for parse_output_schema_cols()
    """
    result = {k: [] for k in _SECTION_KEYS}
    current = None

    for raw_line in req_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Strip leading bullet/number markers for keyword detection
        bare = re.sub(r"^[-*•\d]+\.?\s*", "", line).rstrip(":").strip().lower()

        # Check if this line signals a new section
        matched_section = None
        for section, keywords in _SECTION_KEYS.items():
            if any(kw in bare for kw in keywords):
                matched_section = section
                break

        if matched_section:
            current = matched_section
            # Also extract inline value: "Target Gold Table Name: myname" → capture "myname"
            colon_idx = line.find(":")
            if 0 < colon_idx < len(line) - 1:
                val = line[colon_idx + 1 :].strip().strip("`").strip()
                if val and not re.match(r"^[-*•\d]", val):
                    result[current].append(val)
            continue

        # Collect content under the current section
        if current is None:
            continue

        # Accept: - bullet  * bullet  • bullet  numbered list  plain indented line
        m = re.match(r"^[-*•\d]+\.?\s+(.+)$", line)
        content = m.group(1).strip() if m else line

        if not content:
            continue

        # Check if the bullet itself is a "Key: Value" inline pair
        kv = re.match(r"^(.+?):\s+(.+)$", content)
        if kv:
            key_part = kv.group(1).lower().strip()
            val_part = kv.group(2).strip().strip("`").strip()
            injected = False
            for section, keywords in _SECTION_KEYS.items():
                if any(kw in key_part for kw in keywords):
                    result[section].append(val_part)
                    injected = True
                    break
            if injected:
                continue  # Don't also add to current

        result[current].append(content)

    return result


def parse_output_schema_cols(bullets):
    """
    Extract {name, type} from output_schema bullets like:
      '`customer_id` (INT)'
      'customer_name (VARCHAR)'
      '`total_spend` (DECIMAL(18,2))'
    """
    # Matches: optional backtick + word + optional backtick + whitespace + (TYPE)
    # TYPE may contain nested parens: DECIMAL(18,2)
    pattern = re.compile(r"`?(\w+)`?\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
    results = []
    seen = set()
    for text in bullets:
        m = pattern.search(text.strip())
        if m:
            name = m.group(1).strip()
            type_spec = m.group(2).strip()
            if name and name not in seen and not name.startswith("_"):
                results.append({"name": name, "type": type_spec})
                seen.add(name)
    return results


# ── Column mapping ────────────────────────────────────────────────────────────


def map_output_columns(requested_cols, tables_schemas):
    """
    For each requested output column, determine how it maps to available Silver columns.

    Returns a list of mapping dicts with status:
      direct            — exact column name found in one table
      direct_multiple   — exact name found in multiple tables (likely join key)
      aggregation_candidate — pattern match suggests SUM/COUNT/AVG/MAX/MIN
      derived_flag      — boolean derived column (is_X, has_X, flag_X)
      not_found         — no mapping detected
    """
    # Build col → [(table, type)] index
    col_index = {}
    for tname, fields in tables_schemas.items():
        for f in fields:
            col_index.setdefault(f["name"], []).append((tname, f["type"]))

    # Numeric columns (exclude IDs) → for aggregation candidate matching
    numeric_cols = {
        f["name"]: (tname, f["type"])
        for tname, fields in tables_schemas.items()
        for f in fields
        if any(t in f["type"].lower() for t in ("int", "float", "double", "decimal", "long"))
        and not f["name"].endswith("_id")
        and f["name"] != "id"
    }

    # Date/timestamp columns
    date_cols = {
        f["name"]: (tname, f["type"])
        for tname, fields in tables_schemas.items()
        for f in fields
        if any(t in f["type"].lower() for t in ("timestamp", "date32", "date64", "time"))
    }

    all_col_names = sorted(
        {f["name"] for fields in tables_schemas.values() for f in fields if not f["name"].startswith("_")}
    )

    results = []

    for rc in requested_cols:
        name = rc["name"]

        # 1. Direct exact match
        if name in col_index:
            found = col_index[name]
            results.append(
                {
                    "name": name,
                    "requested_type": rc["type"],
                    "status": "direct_multiple" if len(found) > 1 else "direct",
                    "found_in": found,
                    "suggestion": None,
                }
            )
            continue

        # 2. Boolean derived flag: is_X, has_X, flag_X
        if name.startswith(("is_", "has_", "flag_")):
            results.append(
                {
                    "name": name,
                    "requested_type": rc["type"],
                    "status": "derived_flag",
                    "found_in": [],
                    "suggestion": f"Describe the condition, e.g. `{name} = <column> > <threshold>`",
                }
            )
            continue

        # 3. Aggregation pattern matching
        agg_found = None
        for pat, func in _AGG_PATTERNS:
            m = pat.match(name)
            if not m:
                continue
            base = m.group(1)

            # COUNT patterns (no numeric col needed)
            if func == "COUNT":
                agg_found = {"func": "COUNT", "col": "*", "table": "(all)", "type": "int64"}
                break

            # Exact base col in numerics
            if base in numeric_cols:
                t, tp = numeric_cols[base]
                agg_found = {"func": func, "col": base, "table": t, "type": tp}
                break

            # Fuzzy: base is substring of a numeric col name
            fuzzy = [(c, t, tp) for c, (t, tp) in numeric_cols.items() if base in c or c in base]
            if fuzzy:
                c, t, tp = fuzzy[0]
                agg_found = {"func": func, "col": c, "table": t, "type": tp}
                break

        if agg_found:
            if agg_found["col"] == "*":
                suggestion = f"COUNT(*) as `{name}`"
            else:
                suggestion = f"{agg_found['func']}({agg_found['table']}.{agg_found['col']}) as `{name}`"
            results.append(
                {
                    "name": name,
                    "requested_type": rc["type"],
                    "status": "aggregation_candidate",
                    "found_in": [(agg_found["table"], agg_found["type"])] if agg_found["col"] != "*" else [],
                    "agg_match": agg_found,
                    "suggestion": suggestion,
                }
            )
            continue

        # 4. Date/timestamp pattern (last_X_at, updated_at, etc.)
        if any(k in name for k in ("_at", "_time", "timestamp", "_date", "last_", "latest_")):
            if date_cols:
                best_col, (best_t, best_tp) = list(date_cols.items())[0]
                results.append(
                    {
                        "name": name,
                        "requested_type": rc["type"],
                        "status": "aggregation_candidate",
                        "found_in": [(best_t, best_tp)],
                        "agg_match": {"func": "MAX", "col": best_col, "table": best_t, "type": best_tp},
                        "suggestion": f"MAX({best_t}.{best_col}) as `{name}`",
                    }
                )
                continue

        # 5. Not found
        results.append(
            {
                "name": name,
                "requested_type": rc["type"],
                "status": "not_found",
                "found_in": [],
                "suggestion": None,
                "available_cols": all_col_names[:12],
            }
        )

    return results


# ── Agent question generation ─────────────────────────────────────────────────


def generate_agent_questions(col_mapping, tables_schemas, cross_hint):
    """
    Generate targeted, conversational questions for the user based on:
    - Unresolved join requirements
    - Unmapped output columns (not_found)
    - Derived flag columns that need a condition
    - Aggregation candidates (informational, auto-approvable)
    """
    questions = []
    qid = 0

    # Table context for help text
    table_ctx = " | ".join(
        f"`{t}` [{', '.join(f['name'] for f in fields if not f['name'].startswith('_'))[:5]}"
        f"{'…' if len([f for f in fields if not f['name'].startswith('_')]) > 5 else ''}]"
        for t, fields in tables_schemas.items()
    )

    # ── Q: Join required ──────────────────────────────────────────────────────
    if cross_hint and not cross_hint.get("join_confirmed"):
        tbls = cross_hint.get("tables", [])
        key = cross_hint.get("suggested_join_key", "key_col")
        join_snippet = (
            f"Joins:\n  - {tbls[0]} → {tbls[1]} (on {key})"
            if len(tbls) >= 2
            else "Add a Joins: section to requirements"
        )
        questions.append(
            {
                "id": f"aq_{qid}",
                "type": "join_required",
                "column": None,
                "icon": "🔗",
                "title": "Join required between selected tables",
                "message": cross_hint["question"],
                "context": f"Available tables — {table_ctx}",
                "suggestion": join_snippet,
                "auto_approvable": False,
            }
        )
        qid += 1

    for m in col_mapping:
        status = m["status"]
        name = m["name"]

        # ── Q: Column not found anywhere ──────────────────────────────────────
        if status == "not_found":
            avail = m.get("available_cols", [])
            questions.append(
                {
                    "id": f"aq_{qid}",
                    "type": "column_not_found",
                    "column": name,
                    "icon": "❓",
                    "title": f"`{name}` not found in any selected Silver table",
                    "message": (
                        f"Your Output Schema requests **`{name}`** (`{m['requested_type']}`), "
                        f"but this column does not exist in the selected Silver tables."
                    ),
                    "context": f"Selected tables — {table_ctx}",
                    "suggestion": (
                        (
                            f"Did you mean one of: {', '.join(f'`{c}`' for c in avail[:6])}?\n"
                            "Or do you need to select an additional Silver table that contains this column?"
                        )
                        if avail
                        else "Select an additional Silver table that contains this column."
                    ),
                    "auto_approvable": False,
                }
            )
            qid += 1

        # ── Q: Derived boolean flag needs condition ───────────────────────────
        elif status == "derived_flag":
            questions.append(
                {
                    "id": f"aq_{qid}",
                    "type": "derived_flag",
                    "column": name,
                    "icon": "🏷️",
                    "title": f"`{name}` — derived boolean flag",
                    "message": (
                        f"**`{name}`** (`{m['requested_type']}`) looks like a computed boolean. "
                        "What is the condition that makes it TRUE?"
                    ),
                    "context": (
                        "Derived flags are computed after aggregation using an expression like "
                        "`total_spend > 300` or `total_transactions_count >= 5`."
                    ),
                    "suggestion": f"Business rules:\n  - {name} = <your condition here>",
                    "auto_approvable": False,
                }
            )
            qid += 1

        # ── Info: Aggregation auto-resolved (non-blocking) ────────────────────
        elif status == "aggregation_candidate":
            questions.append(
                {
                    "id": f"aq_{qid}",
                    "type": "aggregation_confirm",
                    "column": name,
                    "icon": "✅",
                    "title": f"`{name}` — aggregation auto-detected",
                    "message": (f"**`{name}`** (`{m['requested_type']}`): mapped to **`{m['suggestion']}`**"),
                    "context": (
                        f"Column `{m['agg_match']['col']}` ({m['agg_match']['type']}) "
                        f"found in `{m['agg_match']['table']}`."
                        if m.get("agg_match", {}).get("col") != "*"
                        else "COUNT(*) over all rows in the joined/filtered result."
                    ),
                    "suggestion": None,
                    "auto_approvable": True,
                }
            )
            qid += 1

        # ── Info: Ambiguous column in multiple tables (usually join key) ──────
        elif status == "direct_multiple":
            found_tables = [t for t, _ in m.get("found_in", [])]
            questions.append(
                {
                    "id": f"aq_{qid}",
                    "type": "ambiguous_column",
                    "column": name,
                    "icon": "ℹ️",
                    "title": f"`{name}` — join key (found in multiple tables)",
                    "message": (
                        f"**`{name}`** exists in: {', '.join(f'`{t}`' for t in found_tables)}. "
                        "It will be used as the join key and as a dimension column."
                    ),
                    "context": "No action needed — this is expected for join keys.",
                    "suggestion": None,
                    "auto_approvable": True,
                }
            )
            qid += 1

    return questions


# ── Plan builders ─────────────────────────────────────────────────────────────


def build_cross_table_plan(tables_schemas, req_hints, col_mapping, cross_hint):
    """
    Build a single joined Gold plan from column mapping + join info.
    Used when join is confirmed and output schema is provided.
    """
    dest_hints = req_hints.get("destination", [])
    tables = cross_hint.get("tables", [])
    join_key = cross_hint.get("suggested_join_key", "")

    # Resolve join from requirements spec if more specific
    req_join_key = join_key
    for raw in req_hints.get("joins", []):
        m = re.search(r"\(on\s+(\w+)\)", raw, re.IGNORECASE)
        if m:
            req_join_key = m.group(1)
            break

    dest_name = dest_hints[0].strip() if dest_hints else ("_".join(t.replace("_silver", "") for t in tables) + "_gold")

    joins = []
    if req_hints.get("joins"):
        for raw in req_hints["joins"]:
            m = re.match(r"(\w+)\s*[→>-]+\s*(\w+)\s*(?:\(on\s+(\w+)\))?", raw, re.IGNORECASE)
            if m:
                joins.append(
                    {
                        "fact": m.group(1),
                        "dim": m.group(2),
                        "on": m.group(3) or req_join_key,
                        "type": "left",
                    }
                )
    elif len(tables) >= 2:
        joins.append({"fact": tables[0], "dim": tables[1], "on": req_join_key, "type": "left"})

    # Build group_by and aggregations from col_mapping
    group_by = []
    aggregations = []
    output_schema = []

    for m in col_mapping:
        status = m["status"]
        name = m["name"]

        if status in ("direct", "direct_multiple"):
            group_by.append(name)
            found_type = m["found_in"][0][1] if m.get("found_in") else "string"
            source_table = m["found_in"][0][0] if m.get("found_in") else ""
            output_schema.append(
                {
                    "column": name,
                    "type": found_type,
                    "source": f"{source_table}.{name}",
                }
            )

        elif status == "aggregation_candidate":
            agg = m.get("agg_match", {})
            aggregations.append(
                {
                    "func": agg.get("func", "COUNT"),
                    "col": agg.get("col", "*"),
                    "alias": name,
                }
            )
            output_schema.append(
                {
                    "column": name,
                    "type": agg.get("type", "double"),
                    "source": m.get("suggestion", ""),
                }
            )

        elif status == "derived_flag":
            # Derived column — included in output schema, not in aggregations
            # Check if a rule describes it
            rule_val = ""
            for rule in req_hints.get("rules", []):
                if name in rule.lower():
                    rule_val = rule
                    break
            output_schema.append(
                {
                    "column": name,
                    "type": "boolean",
                    "source": f"derived: {rule_val}" if rule_val else "derived (post-aggregation)",
                }
            )

    if not aggregations:
        aggregations = [{"func": "COUNT", "col": "*", "alias": "record_count"}]

    grain = f"one row per ({', '.join(group_by)})" if group_by else "undetermined"
    filters = req_hints.get("rules", [])

    return {
        "source_silver": " + ".join(tables) if tables else "joined",
        "destination": dest_name,
        "grain": grain,
        "group_by": group_by,
        "aggregations": aggregations,
        "joins": joins,
        "filters": filters,
        "output_schema": output_schema,
        "questions": [],
        "warnings": [],
        "is_cross_table": True,
    }


def build_plan(table_name, fields, req_hints):
    classified = {f["name"]: classify_field(f["name"], f["type"]) for f in fields}
    type_map = {f["name"]: f["type"] for f in fields}

    id_cols = [n for n, c in classified.items() if c == "id"]
    dim_cols = [n for n, c in classified.items() if c == "dimension"]
    measure_cols = [n for n, c in classified.items() if c == "measure"]
    date_cols = [n for n, c in classified.items() if c == "date"]

    questions = []
    warnings = []
    all_col_names = set(f["name"] for f in fields)

    # ── Resolve group_by ──────────────────────────────────────────────────────
    req_dims = req_hints.get("dimensions", [])
    if req_dims:
        group_by = []
        for raw in req_dims:
            for col in re.split(r"[,\s]+", raw):
                col = col.strip()
                if not col:
                    continue
                if col in all_col_names:
                    group_by.append(col)
                else:
                    questions.append(
                        f"Column `{col}` (from Dimensions requirement) not found in "
                        f"`{table_name}` Silver schema. "
                        f"Available: {', '.join(sorted(all_col_names - {n for n in all_col_names if n.startswith('_')}))}"
                    )
        if not group_by:
            group_by = dim_cols[:2] + date_cols[:1]
    else:
        group_by = dim_cols[:2] + date_cols[:1]

    if not group_by:
        if id_cols:
            group_by = id_cols[:1]
            warnings.append(f"No dimension/date columns found in `{table_name}` — grouping by `{id_cols[0]}`.")
        else:
            questions.append(f"`{table_name}`: Cannot determine group-by columns. " "Add a Dimensions hint.")

    # ── Resolve aggregations ──────────────────────────────────────────────────
    req_measures = req_hints.get("measures", [])
    aggregations = [{"func": "COUNT", "col": "*", "alias": "record_count"}]

    if req_measures:
        for raw in req_measures:
            m = re.match(r"(SUM|AVG|COUNT|MAX|MIN|COUNT DISTINCT)\((\w+)\)\s*(?:as\s+(\w+))?", raw, re.IGNORECASE)
            if m:
                func, col, alias = m.group(1).upper(), m.group(2), m.group(3)
                if col != "*" and col not in all_col_names:
                    questions.append(
                        f"Column `{col}` (from Measures) not found in `{table_name}`. "
                        f"Available numeric columns: {', '.join(measure_cols) or 'none'}"
                    )
                    continue
                alias = alias or f"{func.lower()}_{col}"
                aggregations.append({"func": func, "col": col, "alias": alias})
            else:
                col = raw.strip()
                if col in all_col_names:
                    aggregations.append({"func": "SUM", "col": col, "alias": f"total_{col}"})
                    aggregations.append({"func": "AVG", "col": col, "alias": f"avg_{col}"})
                else:
                    questions.append(
                        f"Column `{col}` (from Measures) not found in `{table_name}`. "
                        f"Available numeric columns: {', '.join(measure_cols) or 'none'}"
                    )
    else:
        for col in measure_cols:
            aggregations.append({"func": "SUM", "col": col, "alias": f"total_{col}"})
            aggregations.append({"func": "AVG", "col": col, "alias": f"avg_{col}"})
        if not measure_cols:
            warnings.append(f"`{table_name}`: No numeric columns found — only record count aggregated.")

    # ── Destination ───────────────────────────────────────────────────────────
    req_dest = req_hints.get("destination", [])
    _base = table_name[:-7] if table_name.endswith("_silver") else table_name
    destination = req_dest[0].strip() if req_dest else f"{_base}_summary"

    # ── Grain ─────────────────────────────────────────────────────────────────
    req_grain = req_hints.get("grain", [])
    grain = req_grain[0] if req_grain else (f"one row per ({', '.join(group_by)})" if group_by else "undetermined")

    # ── Joins ─────────────────────────────────────────────────────────────────
    joins = []
    for raw in req_hints.get("joins", []):
        m = re.match(r"(\w+)\s*[→>-]+\s*(\w+)\s*(?:\(on\s+(\w+)\))?", raw, re.IGNORECASE)
        if m:
            joins.append({"fact": m.group(1), "dim": m.group(2), "on": m.group(3) or "", "type": "left"})

    # ── Output schema ─────────────────────────────────────────────────────────
    output_schema = []
    for col in group_by:
        output_schema.append(
            {
                "column": col,
                "type": type_map.get(col, "string"),
                "source": f"{table_name}.{col}",
            }
        )
    for agg in aggregations:
        t = "int64" if agg["col"] == "*" else type_map.get(agg["col"], "double")
        output_schema.append(
            {
                "column": agg["alias"],
                "type": t,
                "source": f"{agg['func']}({agg['col']})",
            }
        )

    return {
        "source_silver": table_name,
        "destination": destination,
        "grain": grain,
        "group_by": group_by,
        "aggregations": aggregations,
        "joins": joins,
        "filters": req_hints.get("rules", []),
        "output_schema": output_schema,
        "questions": questions,
        "warnings": warnings,
    }


# ── Cross-table join detection ────────────────────────────────────────────────


def detect_cross_table_join(tables_schemas, req_hints):
    """
    Returns a hint dict when multiple Silver tables likely need to be joined.
    Returns None when per-table plans are appropriate.
    """
    from collections import Counter

    table_names = list(tables_schemas.keys())
    if len(table_names) < 2:
        return None

    col_table_count = Counter()
    for fields in tables_schemas.values():
        for f in fields:
            col_table_count[f["name"]] += 1

    common_id_cols = sorted(
        [col for col, cnt in col_table_count.items() if cnt >= 2 and (col.endswith("_id") or col == "id")]
    )

    dest_hints = req_hints.get("destination", [])
    join_hints = req_hints.get("joins", [])
    join_confirmed = bool(join_hints)

    if not dest_hints and not common_id_cols:
        return None

    priority = ["customer_id", "user_id", "order_id", "product_id", "employee_id"]
    preferred_key = next(
        (k for k in priority if k in common_id_cols),
        common_id_cols[0] if common_id_cols else None,
    )
    dest = dest_hints[0].strip() if dest_hints else None

    if join_confirmed:
        question = (
            f"Join detected. Tables `{'`, `'.join(table_names)}` will be joined"
            + (f" on `{preferred_key}`" if preferred_key else "")
            + "."
        )
    else:
        join_example = f"Joins:\n  - {table_names[0]} → {table_names[1]} " f"(on {preferred_key or 'key_column'})"
        question = (
            f"Multiple Silver tables selected (`{'`, `'.join(table_names)}`). "
            + (
                f"Common join key detected: `{preferred_key}`. "
                if preferred_key
                else "No common join key auto-detected. "
            )
            + "**Should these be joined into a single Gold table?**"
            + f"\n\nIf yes, add to Business Requirements:\n```\n{join_example}\n```"
        )

    return {
        "tables": table_names,
        "common_join_keys": common_id_cols,
        "suggested_join_key": preferred_key,
        "destination": dest,
        "join_confirmed": join_confirmed,
        "question": question,
    }


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Analyse Silver schemas and generate a Gold plan")
    parser.add_argument("--tables", required=True, help="Comma-separated Silver table names")
    parser.add_argument("--requirements", default="", help="Free-form business requirements text")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    config = ConfigManager()
    silver_path = config.get("paths.silver", "./data/silver")

    req_text = args.requirements.strip()
    req_hints = parse_requirements(req_text) if req_text else {k: [] for k in _SECTION_KEYS}

    plan = {
        "tables": [],
        "global_questions": [],
        "cross_table_hint": None,
        "agent_questions": [],
        "output_schema_parsed": [],
    }

    # ── First pass: read all schemas ──────────────────────────────────────────
    tables_schemas = {}
    for table in tables:
        silver_dir = Path(silver_path) / table
        if not silver_dir.exists():
            plan["global_questions"].append(
                f"`{table}`: Silver directory `{silver_dir}` not found — has Silver run successfully?"
            )
            continue
        schema = read_schema(silver_dir)
        if schema is None:
            plan["global_questions"].append(f"`{table}`: No Parquet files in `{silver_dir}`.")
            continue
        if isinstance(schema, dict) and "error" in schema:
            plan["global_questions"].append(f"`{table}`: Could not read schema — {schema['error']}")
            continue
        tables_schemas[table] = [f for f in schema if not f["name"].startswith("_")]

    if not tables_schemas:
        print(json.dumps(plan, indent=2))
        return

    # ── Cross-table join detection ─────────────────────────────────────────────
    if len(tables_schemas) >= 2:
        plan["cross_table_hint"] = detect_cross_table_join(tables_schemas, req_hints)

    # ── Output schema parsing & column mapping ────────────────────────────────
    parsed_output_cols = []
    if req_hints.get("output_schema"):
        parsed_output_cols = parse_output_schema_cols(req_hints["output_schema"])
    plan["output_schema_parsed"] = parsed_output_cols

    col_mapping = []
    if parsed_output_cols and tables_schemas:
        col_mapping = map_output_columns(parsed_output_cols, tables_schemas)
        plan["agent_questions"] = generate_agent_questions(col_mapping, tables_schemas, plan.get("cross_table_hint"))

    # ── Plan generation ───────────────────────────────────────────────────────
    cross_hint = plan.get("cross_table_hint") or {}
    blocking_questions = [q for q in plan["agent_questions"] if not q.get("auto_approvable")]

    if cross_hint.get("join_confirmed") and parsed_output_cols and not blocking_questions:
        # All resolved → single joined plan
        plan["tables"] = [build_cross_table_plan(tables_schemas, req_hints, col_mapping, cross_hint)]
    else:
        # Per-table plans (fallback / no output schema specified)
        for table, non_audit in tables_schemas.items():
            plan["tables"].append(build_plan(table, non_audit, req_hints))

    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
