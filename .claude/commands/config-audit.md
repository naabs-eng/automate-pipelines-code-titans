---
description: Audit config.yaml for missing keys, unused keys, path validity, and credential security
allowed-tools: Read, Bash
---

## Context

Current config.yaml:
@config.yaml

All config.get() call sites:
!`grep -rn "config.get(" src/ 2>/dev/null`

## Task

Perform a complete audit of `config.yaml` against actual usage in the codebase.

### Check 1 — Key Coverage

Find every `config.get('some.key')` call across all `src/` files. For each key accessed:
- Does the key exist in `config.yaml`?
- Does it have a non-null value?
- If `config.get('key', default)` has a default, is the fallback value sensible?

Report any key accessed in code but missing from `config.yaml` — these cause silent `None` returns which can crash the pipeline unexpectedly.

### Check 2 — Required Keys Completeness

Verify all required top-level sections and their critical sub-keys exist:

```
sql_server:
  ✓ driver
  ✓ server
  ✓ database
  ✓ trusted_connection

spark:
  ✓ app_name
  ✓ master
  ✓ memory
  ✓ executor_memory
  ✗ jdbc_driver_path  ← MISSING: needed for JDBC driver jar path
  ✗ sql_shuffle_partitions  ← MISSING: defaults to 200 (too high for local dev)

pipeline:
  ✓ frequency
  ✓ data_format

paths:
  ✓ bronze
  ✓ silver
  ✓ gold
  ✓ logs

tables:
  ✓ source (list)
    each entry must have: name, bronze_table
```

### Check 3 — Security Audit

Scan `config.yaml` for any keys that look like raw credentials:
- Any key containing `password`, `secret`, `key`, `token`, `credential` with non-empty values
- Any connection string that embeds a username or password inline

If found, flag as a security issue and suggest moving to `.env` file (loaded via `python-dotenv`).

### Check 4 — Path Validity

Check that all path values in `paths:` section:
- Are relative paths (not absolute C:\ paths — relative paths work cross-platform and in CI)
- Match `.gitignore` entries (data/, logs/ should be gitignored)
- Directories exist or can be created by the pipeline

### Check 5 — Unused Keys

Find any keys in `config.yaml` that are never accessed via `config.get()` in the codebase. Flag these as potentially stale configuration.

### Report Format

Produce a structured report:
- **MISSING keys** (in code but not in config) — HIGH priority
- **SECURITY issues** (credentials in plaintext) — CRITICAL
- **RECOMMENDED additions** (missing best-practice keys like `spark.jdbc_driver_path`)
- **UNUSED keys** (in config but never accessed) — LOW priority
- **PASSED checks** — list of checks that are clean

Offer to apply any non-security fixes directly to `config.yaml`.
