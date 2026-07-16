# Pipeline: pl_logistics_fleet_route_audit_gold

**Type:** Gold (Agent-designed)  
**Last run:** 2026-07-14T06:34  
**Last run status:** ✅ Passed  
**Schedule:** Run once (manual trigger)  

---

## Overview

Gold table **`gold_fleet_fuel_efficiency_metrics`** was designed through a Gold Agent conversation. It aggregates Silver layer data to answer a specific business question.

```
data/silver/pg_fleet_vehicles_silver/  →  data/gold/gold_fleet_fuel_efficiency_metrics/
data/silver/route_telemetry_silver/  →  data/gold/gold_fleet_fuel_efficiency_metrics/
```

---

## Source Silver Tables

### `data/silver/pg_fleet_vehicles_silver/`
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

### `data/silver/route_telemetry_silver/`
**Rows:** 4  

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

## Gold Table

### `data/gold/gold_fleet_fuel_efficiency_metrics/`

**Grain:** vehicle_id  
**Group by:** `vehicle_id`, `plate_number`, `model`, `status`  
**Joins:**  
- `pg_fleet_vehicles_silver` LEFT JOIN `route_telemetry_silver` ON `vehicle_id`
**Business rules applied:**  
- status <> 'Cancelled'

**Aggregations:**

| Function | Input Column | Output Column |
|---|---|---|
| `SUM` | `distance_miles` | `total_distance_covered` |
| `SUM` | `distance_miles)/sum(hours_taken` | `average_speed_mph` |
| `SUM` | `distance_miles)/sum(fuel_consumed_gallons` | `fuel_efficiency_mpg` |

**Output rows:** 3  

**Output schema:**

| Column | Type |
|---|---|
| `vehicle_id` | `int32` |
| `plate_number` | `string` |
| `model` | `string` |
| `environmental_class` | `string` |
| `total_distance_covered` | `double` |
| `average_speed_mph` | `double` |
| `fuel_efficiency_mpg` | `double` |

---

_Generated automatically by the Gold Agent after each run._