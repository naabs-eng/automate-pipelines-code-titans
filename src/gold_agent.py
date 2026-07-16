"""
Gold Agent — Claude API-powered conversational pipeline architect.

Gathers all information needed to build a Gold aggregation table from a
user-provided target schema, then calls finalize_plan when ready.
"""
import json
import os
from pathlib import Path

import anthropic


class GoldAgent:
    MODEL = "claude-haiku-4-5-20251001"        # used for planning chat
    CODE_MODEL = "claude-sonnet-4-6"            # used for PySpark code generation

    SYSTEM_PROMPT = """You are a Gold layer pipeline architect for a Medallion Architecture \
(Bronze → Silver → Gold) data pipeline.

Your ONLY goal: gather all information needed to build a Gold aggregation table that matches \
the user's requested target schema, then call `finalize_plan` when you have everything.

## Gold Layer Rules (enforce these)
- Gold tables contain groupBy + aggregation ONLY — never row-level transforms
- Default join type is LEFT JOIN. Use FULL OUTER JOIN only when the user explicitly requests it.
- Never use INNER JOIN — it silently drops unmatched rows.
- All group_by columns must exist as actual columns in a Silver table
- Aggregations: SUM, COUNT, AVG, MAX, MIN only
- Derived boolean columns (is_X, has_X, flag_X) require an explicit condition from the user
- Never guess or fabricate column names — verify against actual Silver schemas

## Your Workflow
1. On the VERY FIRST user message, IMMEDIATELY call `list_silver_tables` to see what's available
2. Parse the target schema the user provided
3. For each requested output column, classify:
   - **Direct column** (exact name exists in Silver) → group_by dimension
   - **Aggregation** (total_X, sum_X, count_X, avg_X, max_X, min_X pattern) → aggregations
   - **Derived boolean** (is_X, has_X, flag_X) → needs a condition from the user
   - **Unknown** → call `read_silver_schema` on the most likely table; ask the user if still not found
4. Call `read_silver_schema` to verify column existence when needed
5. Ask ONLY questions that are genuinely unresolved — don't ask if you can infer the answer
6. For multi-table scenarios: confirm the join key (common _id column) with the user
7. Once ALL columns are mapped and confirmed → call `finalize_plan` IMMEDIATELY

## CRITICAL: When to call finalize_plan
- Call it AS SOON AS all columns are resolved and all business rules are clear
- Do NOT ask "next?", "anything else?", "shall I proceed?", or any open-ended follow-up
- Do NOT wait for the user to say "go ahead" or "done"
- If the user provides additional info (e.g. "join should be full join"), update your plan and call finalize_plan immediately — do not ask another question

## EXAMPLE — follow this EXACTLY
User: "gold_agent_stats: agent_id, agent_full_name, total_tickets (count), avg_response_time_min (avg of response_time_minutes), join ticket_events_silver with pg_support_agents_silver on agent_id, full join"
→ You call list_silver_tables (tool call)
→ You call read_silver_schema on relevant tables (tool call)
→ ALL info is clear — you call finalize_plan immediately (tool call) — NO TEXT SUMMARY FIRST
→ You do NOT output "Here is what I understood: ..." and stop

## ANTI-PATTERN — never do this
→ Output a bullet-point requirements summary in text
→ End the turn without calling finalize_plan
→ Wait for user to say "proceed" or "finalize"
This is WRONG. If you have all the info, call finalize_plan NOW in the same response.

## What you MUST confirm before calling finalize_plan
- Destination table name
- Source Silver table(s) — at least one
- Join key and join type (only if multiple tables)
- Which columns are group-by dimensions vs aggregated measures
- Aggregation function for each measure (SUM, COUNT, etc.)
- Condition expression for any derived boolean columns
- Any filters/business rules (or confirm there are none)

## Style
- Be concise and technical
- Present column mapping status clearly (✅ resolved, ❓ needs input)
- Ask one focused question at a time
- Once you have all answers, call `finalize_plan` immediately
"""

    TOOLS = [
        {
            "name": "list_silver_tables",
            "description": (
                "List all Silver tables currently available on disk with their column schemas "
                "and row counts. Call this first on every conversation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "read_silver_schema",
            "description": (
                "Read the full column schema of a specific Silver table. "
                "Use to verify whether a column exists or to check its data type."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Directory name of the Silver table, e.g. 'pg_customers_silver'",
                    }
                },
                "required": ["table_name"],
            },
        },
        {
            "name": "finalize_plan",
            "description": (
                "Call when all questions are resolved and the Gold plan is complete. "
                "This stores the plan so the user can review and execute it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "Gold table name, e.g. 'customer_value_summary'",
                    },
                    "source_tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Silver table directory names, e.g. ['transactions_silver']",
                    },
                    "joins": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fact": {"type": "string"},
                                "dim": {"type": "string"},
                                "on": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "description": "REQUIRED. Must be 'left' (default) or 'full' (FULL OUTER JOIN). Use 'full' when user asks for full/full outer join. NEVER 'inner'. NEVER omit this field.",
                                },
                            },
                            "required": ["fact", "dim", "on", "type"],
                        },
                        "description": "JOIN specs. type is REQUIRED: 'left' by default, 'full' when user explicitly asks for full/full outer join. Empty list if only one source table.",
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Dimension columns to group by",
                    },
                    "aggregations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "func": {"type": "string"},
                                "col": {"type": "string"},
                                "alias": {"type": "string"},
                            },
                            "required": ["func", "col", "alias"],
                        },
                        "description": "Aggregation expressions",
                    },
                    "derived_columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "expression": {"type": "string"},
                                "type": {"type": "string"},
                            },
                            "required": ["column", "expression"],
                        },
                        "description": "Post-aggregation computed columns, e.g. boolean flags",
                    },
                    "filters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pre-aggregation filter conditions (SQL expressions)",
                    },
                    "grain": {
                        "type": "string",
                        "description": "One-sentence row grain, e.g. 'one row per customer'",
                    },
                    "output_schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "type": {"type": "string"},
                                "source": {"type": "string"},
                            },
                        },
                        "description": "Ordered output columns with types and source expressions",
                    },
                },
                "required": ["destination", "source_tables", "group_by", "aggregations"],
            },
        },
    ]

    def __init__(self, silver_path: str, gold_path: str, api_key: str | None = None):
        self.silver_path = Path(silver_path)
        self.gold_path = Path(gold_path)
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.history: list[dict] = []
        self.final_plan: dict | None = None

    # ── Tool implementations ───────────────────────────────────────────────────

    def _tool_list_silver_tables(self) -> dict:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            return {"error": "pyarrow not installed — run: pip install pyarrow"}

        if not self.silver_path.exists():
            return {
                "tables": [],
                "message": "Silver directory not found. Run Bronze & Silver pipeline first.",
            }

        results = []
        for d in sorted(self.silver_path.iterdir()):
            if not d.is_dir():
                continue
            parts = sorted(d.glob("**/*.parquet"))
            if not parts:
                continue
            try:
                schema = pq.read_schema(str(parts[0]))
                pf = pq.ParquetFile(str(parts[0]))
                columns = [
                    {"name": schema.names[i], "type": str(schema.types[i])}
                    for i in range(len(schema.names))
                    if not schema.names[i].startswith("_")
                ]
                results.append(
                    {
                        "name": d.name,
                        "row_count": pf.metadata.num_rows,
                        "columns": columns,
                    }
                )
            except Exception as exc:
                results.append({"name": d.name, "error": str(exc)})

        return {"tables": results, "count": len(results)}

    def _tool_read_silver_schema(self, table_name: str) -> dict:
        table_dir = self.silver_path / table_name
        if not table_dir.exists():
            available = (
                [d.name for d in self.silver_path.iterdir() if d.is_dir()]
                if self.silver_path.exists()
                else []
            )
            return {"error": f"Table '{table_name}' not found.", "available": available}
        try:
            import pyarrow.parquet as pq

            parts = sorted(table_dir.glob("**/*.parquet"))
            if not parts:
                return {"error": f"No Parquet files in {table_dir}"}
            schema = pq.read_schema(str(parts[0]))
            return {
                "table": table_name,
                "columns": [
                    {"name": schema.names[i], "type": str(schema.types[i])}
                    for i in range(len(schema.names))
                    if not schema.names[i].startswith("_")
                ],
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _tool_finalize_plan(self, **kwargs) -> dict:
        self.final_plan = {
            "destination": kwargs.get("destination", ""),
            "source_tables": kwargs.get("source_tables", []),
            "joins": kwargs.get("joins", []),
            "group_by": kwargs.get("group_by", []),
            "aggregations": kwargs.get("aggregations", []),
            "derived_columns": kwargs.get("derived_columns", []),
            "filters": kwargs.get("filters", []),
            "grain": kwargs.get("grain", ""),
            "output_schema": kwargs.get("output_schema", []),
        }
        return {"status": "plan_finalized", "destination": self.final_plan["destination"]}

    def _run_tool(self, name: str, tool_input: dict) -> dict:
        if name == "list_silver_tables":
            return self._tool_list_silver_tables()
        if name == "read_silver_schema":
            return self._tool_read_silver_schema(**tool_input)
        if name == "finalize_plan":
            return self._tool_finalize_plan(**tool_input)
        return {"error": f"Unknown tool: {name}"}

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> dict:
        """
        Send a user message and return a response dict:
        {
            "events": [
                {"type": "tool_call", "name": ..., "input": ..., "result": ...},
                {"type": "text", "content": ...},
            ],
            "final_plan": dict | None,
        }
        """
        self.history.append({"role": "user", "content": user_message})
        events: list[dict] = []

        while True:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
                tools=self.TOOLS,
                messages=self.history,
            )

            if response.stop_reason == "end_turn":
                text = "".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                self.history.append({"role": "assistant", "content": response.content})
                if text:
                    events.append({"type": "text", "content": text})
                break

            if response.stop_reason == "tool_use":
                self.history.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "text" and block.text:
                        events.append({"type": "text", "content": block.text})
                    if block.type == "tool_use":
                        result = self._run_tool(block.name, block.input)
                        events.append(
                            {
                                "type": "tool_call",
                                "name": block.name,
                                "input": block.input,
                                "result": result,
                            }
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result),
                            }
                        )
                self.history.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — capture any text and break
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            if text:
                events.append({"type": "text", "content": text})
            break

        return {"events": events, "final_plan": self.final_plan}

    def generate_execution_code(self, plan: dict) -> str:
        """
        Second LLM call: takes the finalized plan + actual Silver schemas and returns
        a complete, self-contained PySpark Python script ready to execute.
        No static interpreter — the LLM writes correct code for the specific plan.
        """
        schemas_info = {}
        for table in plan.get("source_tables", []):
            result = self._tool_read_silver_schema(table)
            if "columns" in result:
                schemas_info[table] = result["columns"]

        prompt = f"""Write a complete, executable PySpark Python script that runs this Gold aggregation plan.

PLAN:
{json.dumps(plan, indent=2)}

ACTUAL SILVER SCHEMAS (use only these exact column names — do not invent columns):
{json.dumps(schemas_info, indent=2)}

STRICT RULES:
- Import: pyspark.sql, pyspark.sql.functions as F, sys, os
- Create SparkSession: SparkSession.builder.appName("{plan.get('destination', 'gold_job')}").getOrCreate()
- Set log level to WARN: spark.sparkContext.setLogLevel("WARN")
- Read each Silver table: spark.read.parquet("{self.silver_path}/<table_name>")
- After reading, drop any "_corrupt_record" column if present using: df = df.drop("_corrupt_record") if "_corrupt_record" in df.columns else df
- Never use INNER JOIN
- For each join, use the join type specified in the plan ("left" or "full")
- For FULL OUTER JOIN where both tables share the same key column name, use the string form: df.join(dim, "col", "full") — PySpark automatically coalesces the key from both sides, so dimension-only rows keep their key value (no None). Do NOT use the expression form df["col"] == dim["col"] for full outer joins.
- For LEFT JOIN, use: df.join(dim, df["col"] == dim["col"], "left") then drop the dim's copy of the key column
- Apply pre-aggregation filters with .filter(F.expr("..."))
- Apply groupBy then agg()
- Apply derived boolean columns after agg using F.when(F.expr("condition"), True).otherwise(False)
- Write result: .coalesce(1).write.mode("overwrite").parquet("{self.gold_path}/{plan.get('destination')}")
- On success: print("[Gold] SUCCESS: {plan.get('destination')}") then sys.exit(0)
- Wrap entire logic in try/except Exception as e: print(f"[Gold] ERROR: {{e}}"); sys.exit(1)

OUTPUT: Return ONLY raw Python code. No markdown fences, no comments, no explanation.
"""

        response = self.client.messages.create(
            model=self.CODE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.content[0].text.strip()
        # Strip accidental markdown fences
        if code.startswith("```"):
            lines = code.splitlines()
            end = len(lines) - 1 if lines[-1].strip().startswith("```") else len(lines)
            code = "\n".join(lines[1:end])
        return code

    def reset(self):
        self.history = []
        self.final_plan = None
