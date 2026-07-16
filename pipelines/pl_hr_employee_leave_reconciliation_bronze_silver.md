# Pipeline: pl_hr_employee_leave_reconciliation_bronze_silver

**Type:** Bronze & Silver  
**Last run:** 2026-07-12T11:55  
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
| `pg_employees` | `data/bronze/pg_employees_bronze/` |

### Source 2 — FILE
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `leave_logs.csv` | `data/bronze/leave_logs_bronze/` |

---

## Bronze Layer

_Raw, unmodified copy of source data. Column names and types match the source._

### `data/bronze/pg_employees_bronze/`
**Rows:** 3  

| Column | Type |
|---|---|
| `employee_id` | `int32` |
| `full_name` | `string` |
| `department` | `string` |
| `salary_usd` | `decimal128(10, 2)` |
| `status` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/bronze/leave_logs_bronze/`
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

---

## Silver Layer

_Cleaned, typed, snake_case. Every row has a non-null primary key._

### `data/silver/pg_employees_silver/`
**Rows:** 3  
**Inferred primary key:** `employee_id`  

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

### `data/silver/leave_logs_silver/`
**Rows:** 4  
**Inferred primary key:** `leave_id`  

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

---

## Data Flow

```
Source  →  data/bronze/pg_employees_bronze/  →  data/silver/pg_employees_silver/
Source  →  data/bronze/leave_logs_bronze/  →  data/silver/leave_logs_silver/
```

---

_Generated automatically by the Pipeline Runner after each run._