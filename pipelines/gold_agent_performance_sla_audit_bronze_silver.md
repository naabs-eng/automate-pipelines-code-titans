# Pipeline: gold_agent_performance_sla_audit_bronze_silver

**Type:** Bronze & Silver  
**Last run:** 2026-07-16T07:19  
**Last run status:** ✅ Passed  
**Schedule:** Run once (manual trigger)  

---

## Overview

This pipeline ingests raw data from the configured sources into the **Bronze** layer (faithful copy, no transforms), then promotes it to the **Silver** layer (snake_case column names, explicit type casts, null-filtered primary keys).

```
Source → data/bronze/<table>_bronze/ → data/silver/<table>_silver/
```

---

## Sources

### Source 1 — POSTGRESQL
**Connection:** `localhost:5432/`  
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `public.pg_support_agents` | `data/bronze/pg_support_agents_bronze/` |

### Source 2 — FILE
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `ticket_events.json` | `data/bronze/ticket_events_bronze/` |

---

## Bronze Layer

_Raw, unmodified copy of source data. Column names and types match the source._

### `data/bronze/pg_support_agents_bronze/`
**Rows:** 3  

| Column | Type |
|---|---|
| `agent_id` | `int32` |
| `first_name` | `string` |
| `last_name` | `string` |
| `tier_level` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/bronze/ticket_events_bronze/`
**Rows:** 6  

| Column | Type |
|---|---|
| `_corrupt_record` | `string` |
| `agent_id` | `int64` |
| `customer_id` | `int64` |
| `priority` | `string` |
| `resolved` | `bool` |
| `response_time_minutes` | `int64` |
| `ticket_id` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Silver Layer

_Cleaned, typed, snake_case. Every row has a non-null primary key._

### `data/silver/pg_support_agents_silver/`
**Rows:** 3  
**Inferred primary key:** `agent_id`  

| Column | Type |
|---|---|
| `agent_id` | `int32` |
| `first_name` | `string` |
| `last_name` | `string` |
| `tier_level` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/silver/ticket_events_silver/`
**Rows:** 4  
**Inferred primary key:** `agent_id`  

| Column | Type |
|---|---|
| `_corrupt_record` | `string` |
| `agent_id` | `int32` |
| `customer_id` | `int32` |
| `priority` | `string` |
| `resolved` | `string` |
| `response_time_minutes` | `int32` |
| `ticket_id` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Data Flow

```
Source  →  data/bronze/pg_support_agents_bronze/  →  data/silver/pg_support_agents_silver/
Source  →  data/bronze/ticket_events_bronze/  →  data/silver/ticket_events_silver/
```

---

_Generated automatically by the Pipeline Runner after each run._