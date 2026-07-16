# Pipeline: gold_agent_performance_sla_audit_gold

**Type:** Gold (Agent-designed)  
**Last run:** 2026-07-16T07:23  
**Last run status:** ✅ Passed  
**Schedule:** Run once (manual trigger)  

---

## Overview

Gold table **`gold_agent_performance_sla_audit`** was designed through a Gold Agent conversation. It aggregates Silver layer data to answer a specific business question.

```
data/silver/pg_support_agents_silver/  →  data/gold/gold_agent_performance_sla_audit/
data/silver/ticket_events_silver/  →  data/gold/gold_agent_performance_sla_audit/
```

---

## Source Silver Tables

### `data/silver/pg_support_agents_silver/`
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

### `data/silver/ticket_events_silver/`
**Rows:** 4  

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

## Gold Table

### `data/gold/gold_agent_performance_sla_audit/`

**Grain:** one row per agent  
**Group by:** `agent_id`, `agent_full_name`, `support_tier`  
**Joins:**  
- `ticket_events_silver` LEFT JOIN `pg_support_agents_silver` ON `ticket_events_silver.agent_id = pg_support_agents_silver.agent_id`

**Aggregations:**

| Function | Input Column | Output Column |
|---|---|---|
| `COUNT` | `ticket_id` | `total_tickets_assigned` |
| `AVG` | `response_time_minutes` | `average_response_time_min` |
| `SUM` | `sla_breach_flag` | `sla_breach_count` |
| `SUM` | `resolved_count` | `total_resolved` |

**Derived columns:**

| Column | Expression |
|---|---|
| `sla_breach_flag` | `CASE WHEN (priority = 'Critical' AND response_time_minutes > 15) OR (priority = 'High' AND response_time_minutes > 30) OR (priority = 'Low' AND response_time_minutes > 120) THEN 1 ELSE 0 END` |
| `resolved_count` | `CASE WHEN resolved = 'true' THEN 1 ELSE 0 END` |
| `agent_full_name` | `COALESCE(CONCAT(pg_support_agents_silver.first_name, ' ', pg_support_agents_silver.last_name), 'AUTOMATED_BOT')` |
| `support_tier` | `COALESCE(pg_support_agents_silver.tier_level, 'AI_AGENT')` |
| `resolution_rate_percent` | `(CAST(total_resolved AS DECIMAL(5,2)) / CAST(total_tickets_assigned AS DECIMAL(5,2))) * 100` |

**Output rows:** 4  

**Output schema:**

| Column | Type |
|---|---|
| `agent_id` | `int32` |
| `agent_full_name` | `string` |
| `support_tier` | `string` |
| `total_tickets_assigned` | `int32` |
| `average_response_time_min` | `decimal128(6, 2)` |
| `sla_breach_count` | `int32` |
| `resolution_rate_percent` | `decimal128(5, 2)` |

---

_Generated automatically by the Gold Agent after each run._