# Pipeline: pl_logistics_fleet_route_audit_bronze_silver

**Type:** Bronze & Silver  
**Last run:** 2026-07-14T06:02  
**Last run status:** ✅ Passed  
**Schedule:** Daily at 15:30  `30 15 * * *`  

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
| `public.pg_fleet_vehicles` | `data/bronze/pg_fleet_vehicles_bronze/` |

### Source 2 — FILE
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `route_telemetry.csv` | `data/bronze/route_telemetry_bronze/` |

---

## Bronze Layer

_Raw, unmodified copy of source data. Column names and types match the source._

### `data/bronze/pg_fleet_vehicles_bronze/`
**Rows:** 3  

| Column | Type |
|---|---|
| `vehicle_id` | `int32` |
| `plate_number` | `string` |
| `model` | `string` |
| `driver_assigned` | `string` |
| `fuel_type` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/bronze/route_telemetry_bronze/`
**Rows:** 4  

| Column | Type |
|---|---|
| `dispatch_id` | `string` |
| `vehicle_id` | `int32` |
| `distance_miles` | `double` |
| `hours_taken` | `double` |
| `fuel_consumed_gallons` | `double` |
| `status` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Silver Layer

_Cleaned, typed, snake_case. Every row has a non-null primary key._

### `data/silver/pg_fleet_vehicles_silver/`
**Rows:** 3  
**Inferred primary key:** `vehicle_id`  

| Column | Type |
|---|---|
| `vehicle_id` | `int32` |
| `plate_number` | `string` |
| `model` | `string` |
| `driver_assigned` | `string` |
| `fuel_type` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/silver/route_telemetry_silver/`
**Rows:** 4  
**Inferred primary key:** `dispatch_id`  

| Column | Type |
|---|---|
| `dispatch_id` | `string` |
| `vehicle_id` | `int32` |
| `distance_miles` | `float` |
| `hours_taken` | `float` |
| `fuel_consumed_gallons` | `float` |
| `status` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Data Flow

```
Source  →  data/bronze/pg_fleet_vehicles_bronze/  →  data/silver/pg_fleet_vehicles_silver/
Source  →  data/bronze/route_telemetry_bronze/  →  data/silver/route_telemetry_silver/
```

---

_Generated automatically by the Pipeline Runner after each run._