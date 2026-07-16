# Pipeline: pl_enrich_customer_transactions_gold

**Type:** Gold (Agent-designed)  
**Last run:** 2026-07-16T07:40  
**Last run status:** ✅ Passed  
**Schedule:** Run once (manual trigger)  

---

## Overview

Gold table **`gold_customer_revenue_summary`** was designed through a Gold Agent conversation. It aggregates Silver layer data to answer a specific business question.

```
data/silver/pg_customers_silver/  →  data/gold/gold_customer_revenue_summary/
data/silver/transactions_silver/  →  data/gold/gold_customer_revenue_summary/
```

---

## Source Silver Tables

### `data/silver/pg_customers_silver/`
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

### `data/silver/transactions_silver/`
**Rows:** 4  

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

## Gold Table

### `data/gold/gold_customer_revenue_summary/`

**Grain:** one row per customer  
**Group by:** `customer_id`, `first_name`, `tier`  
**Joins:**  
- `pg_customers_silver` LEFT JOIN `transactions_silver` ON `customer_id`

**Aggregations:**

| Function | Input Column | Output Column |
|---|---|---|
| `COUNT` | `*` | `total_transactions_count` |
| `SUM` | `amount` | `total_spend` |
| `AVG` | `amount` | `average_order_value` |
| `MAX` | `txn_timestamp` | `last_active_at` |

**Output rows:** 3  

**Output schema:**

| Column | Type |
|---|---|
| `customer_id` | `int32` |
| `customer_name` | `string` |
| `membership_tier` | `string` |
| `total_transactions_count` | `int64` |
| `total_spend` | `double` |
| `average_order_value` | `double` |
| `last_active_at` | `string` |

---

_Generated automatically by the Gold Agent after each run._