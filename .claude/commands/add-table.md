---
description: Scaffold all three medallion layers + config + main.py for a new source table
allowed-tools: Read, Bash
argument-hint: "<TableName> — e.g. Inventory, Returns, Suppliers"
---

## Context

New table to add: **$ARGUMENTS**

Current source files (read to extract exact patterns):
@src/bronze/ingestion.py
@src/silver/transformations.py
@src/gold/aggregations.py
@src/main.py
@config.yaml
@sql/create_schema.sql

Data modeling reference: @.claude/skills/data-modeling.md

## Task

Scaffold all the code needed to add the `$ARGUMENTS` table to the pipeline. Follow the EXACT patterns used for existing tables — do not invent new patterns.

### Step 1 — Gather Requirements

Before generating any code, ask the user (in a single message):
1. What columns should `dbo.$ARGUMENTS` have? (provide column name + SQL Server type for each)
2. Is this a **fact table** (contains measurements like quantity/price) or a **dimension table** (describes an entity)?
3. What are the foreign key relationships to existing tables?
4. What Gold aggregation(s) should this table enable? (or "none" if it's just a dimension join)

### Step 2 — Generate Scaffolding (present for review, do not write yet)

Based on the user's answers, generate and display:

**A. SQL DDL** (for `sql/create_schema.sql`):
```sql
-- dbo.$ARGUMENTS table
CREATE TABLE dbo.$ARGUMENTS (
    -- columns here
);
```

**B. Sample INSERT statements** (for `sql/insert_sample_data.sql`) — 5-10 rows

**C. `config.yaml` addition**:
```yaml
# Add to tables.source:
- name: "dbo.$ARGUMENTS"
  bronze_table: "<snake_case_plural>"
```

**D. Silver `transform_<snake_plural>()` method** — follow exact same pattern as `transform_products()`:
- `select()` with explicit `F.col().cast().alias()` for each column
- Derived column if it's a fact table (calculate a measure like `line_total`)
- `filter(F.col("pk_column").isNotNull())` as last step

**E. Gold `create_<metric_name>()` method** (only if a Gold aggregation is needed) — follow exact pattern

**F. `main.py` wiring additions**:
- Bronze read → Silver transform → Silver save
- Gold create → Gold save (if applicable)

### Step 3 — Confirm and Write

Show all generated code to the user and ask: "Shall I write these changes to all files?"

Only after explicit confirmation:
1. Append to `sql/create_schema.sql`
2. Append to `sql/insert_sample_data.sql`
3. Update `config.yaml` tables.source list
4. Add the `transform_<snake_plural>()` method to `src/silver/transformations.py`
5. Add the `create_<metric>()` method to `src/gold/aggregations.py` (if needed)
6. Add wiring to `src/main.py`

After writing, run `python -m py_compile src/silver/transformations.py src/gold/aggregations.py src/main.py` to verify no syntax errors.
