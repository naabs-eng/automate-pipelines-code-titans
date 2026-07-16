# Pipeline: pl_enrich_customer_transactions_bronze_silver

**Type:** Bronze & Silver  
**Last run:** 2026-07-11T09:59  
**Schedule:** Daily at 08:00  `00 08 * * *`  

---

## Overview

This pipeline ingests raw data from the configured sources into the **Bronze** layer (faithful copy, no transforms), then promotes it to the **Silver** layer (snake_case column names, explicit type casts, null-filtered primary keys).

```
Source → data/bronze/<table>_bronze/ → data/silver/<table>_silver/
```

---

## Sources

### Source 1 — POSTGRESQL
**Connection:** `localhost:5432/postgres`  
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `pg_customers` | `data/bronze/pg_customers_bronze/` |

### Source 2 — FILE
**Load mode:** full  

| Source Table | Bronze Directory |
|---|---|
| `transactions.json` | `data/bronze/transactions_bronze/` |

---

## Bronze Layer

_Raw, unmodified copy of source data. Column names and types match the source._

### `data/bronze/pg_customers_bronze/`
**Rows:** 3  

| Column | Type |
|---|---|
| `customer_id` | `int32` |
| `first_name` | `string` |
| `email` | `string` |
| `tier` | `string` |
| `signup_date` | `date32[day]` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/bronze/transactions_bronze/`
**Rows:** 8  

| Column | Type |
|---|---|
| `_corrupt_record` | `string` |
| `amount` | `double` |
| `customer_id` | `int64` |
| `transaction_id` | `string` |
| `txn_timestamp` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Silver Layer

_Cleaned, typed, snake_case. Every row has a non-null primary key._

### `data/silver/pg_customers_silver/`
**Rows:** 3  
**Inferred primary key:** `customer_id`  

| Column | Type |
|---|---|
| `customer_id` | `int32` |
| `first_name` | `string` |
| `email` | `string` |
| `tier` | `string` |
| `signup_date` | `date32[day]` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

### `data/silver/transactions_silver/`
**Rows:** 4  
**Inferred primary key:** `customer_id`  

| Column | Type |
|---|---|
| `_corrupt_record` | `string` |
| `amount` | `float` |
| `customer_id` | `int32` |
| `transaction_id` | `string` |
| `txn_timestamp` | `string` |
| `_ingestion_timestamp` | `timestamp[ns]` |
| `_source_name` | `string` |
| `_load_mode` | `string` |

---

## Data Flow

```
Source  →  data/bronze/pg_customers_bronze/  →  data/silver/pg_customers_silver/
Source  →  data/bronze/transactions_bronze/  →  data/silver/transactions_silver/
```

---

_Generated automatically by the Pipeline Runner after each successful run._