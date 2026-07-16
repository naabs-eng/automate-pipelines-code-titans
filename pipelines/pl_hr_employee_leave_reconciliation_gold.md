# Pipeline: pl_hr_employee_leave_reconciliation_gold

**Type:** Gold (Agent-designed)  
**Last run:** 2026-07-12T12:50  
**Last run status:** ✅ Passed  
**Schedule:** Run once (manual trigger)  

---

## Overview

Gold table **`gold_departmental_leave_utilization`** was designed through a Gold Agent conversation. It aggregates Silver layer data to answer a specific business question.

```
data/silver/leave_logs_silver/  →  data/gold/gold_departmental_leave_utilization/
data/silver/pg_employees_silver/  →  data/gold/gold_departmental_leave_utilization/
```

---

## Source Silver Tables

### `data/silver/leave_logs_silver/`
**Rows:** 4  

| Column | Type |
|---|---|
| `leave_id` | `string` |
| `employee_id` | `int32` |
| `leave_type` | `string` |
| `start_date` | `date32[day]` |
| `end_date` | `date32[day]` |
| `approval_status` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/silver/pg_employees_silver/`
**Rows:** 3  

| Column | Type |
|---|---|
| `employee_id` | `int32` |
| `full_name` | `string` |
| `department` | `string` |
| `salary_usd` | `float` |
| `status` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Gold Table

### `data/gold/gold_departmental_leave_utilization/`

**Grain:** department  
**Group by:** `department`  
**Joins:**  
- `leave_logs_silver` LEFT JOIN `pg_employees_silver` ON `employee_id`
**Business rules applied:**  
- status='Active'
- approval_status = 'Approved'

**Aggregations:**

| Function | Input Column | Output Column |
|---|---|---|
| `COUNT` | `*` | `active_employees_count` |
| `SUM` | `datediff(end_date, start_date)` | `total_approved_leave_days` |
| `SUM` | `datediff(end_date, current_date())` | `total_pending_leave_days` |
| `AVG` | `salary_usd` | `average_salary` |

**Output rows:** 2  

**Output schema:**

| Column | Type |
|---|---|
| `department` | `string` |
| `active_employees_count` | `int64` |
| `total_approved_leave_days` | `int64` |
| `total_pending_leave_days` | `int64` |
| `average_salary` | `double` |

---

_Generated automatically by the Gold Agent after each run._