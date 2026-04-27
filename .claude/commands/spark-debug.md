---
description: Parse pipeline logs for Spark errors and provide targeted fixes for known failure patterns
allowed-tools: Bash, Read
argument-hint: "[keyword] — optional error term to filter on (e.g. JDBC, OOM, Analysis)"
---

## Context

Latest log file:
!`python -c "import pathlib; logs=sorted(pathlib.Path('logs').glob('*.log')); f=logs[-1] if logs else None; print(f) if f else print('No log files found in logs/')" 2>&1`

All ERROR and WARN lines from latest log:
!`python -c "
import pathlib
logs = sorted(pathlib.Path('logs').glob('*.log'))
if logs:
    lines = open(logs[-1]).readlines()
    errors = [l.strip() for l in lines if 'ERROR' in l or 'WARN' in l or 'Exception' in l or 'Traceback' in l]
    keyword = '$ARGUMENTS'.strip()
    if keyword:
        errors = [l for l in errors if keyword.lower() in l.lower()]
    print('\n'.join(errors[-30:]) if errors else 'No errors found')
else:
    print('No log files found')
" 2>&1`

Source references:
@src/bronze/ingestion.py
@src/main.py

SQL Server integration patterns: @.claude/skills/sql-server-integration.md
PySpark patterns: @.claude/skills/pyspark-patterns.md

## Task

Diagnose the errors shown above and provide targeted fixes for this specific pipeline.

### Known Error Patterns — Match and Explain

For each error or warning found, check against these patterns:

**JDBC / SQL Server Errors**:
- `ClassNotFoundException: com.microsoft.sqlserver.jdbc.SQLServerDriver` → JDBC jar not on Spark classpath. Fix: add `spark.jars` config pointing to `drivers/mssql-jdbc-*.jar`
- `No suitable driver found for jdbc:sqlserver` → Same fix as above
- `Login failed for user ''` → Windows auth broken. Fix: remove `user`/`password` options, add `integratedSecurity=true;authenticationScheme=NativeAuthentication` to JDBC URL in `src/bronze/ingestion.py`
- `TCP/IP connection to localhost:1433 has failed` → SQL Server TCP not enabled. Fix: enable TCP/IP in SQL Server Configuration Manager, set port 1433
- `SSL handshake failed` → TLS mismatch for local dev. Fix: add `encrypt=false;trustServerCertificate=true` to JDBC URL

**PySpark / Analysis Errors**:
- `AnalysisException: Path does not exist: data/silver/` → Bronze layer didn't complete before Silver tried to read. Fix: check Bronze ran successfully; verify `data/bronze/` dirs are non-empty
- `AnalysisException: cannot resolve column 'product_id'` → Column name mismatch (Bronze has PascalCase `ProductID`, Silver tried to read snake_case). Fix: check Silver `transform_products()` casts with `.alias("product_id")` before saving; don't read bronze with snake_case expectation
- `AnalysisException: Column 'line_total' does not exist` → Silver `transform_order_items()` didn't add the `withColumn("line_total", ...)` derivation. Fix: check `src/silver/transformations.py`

**Memory / Performance Errors**:
- `java.lang.OutOfMemoryError: Java heap space` → Spark driver memory too low. Fix: increase `spark.memory` in `config.yaml` to `"8g"` or add `.config("spark.sql.shuffle.partitions", "2")` for local dev
- `java.lang.OutOfMemoryError: GC overhead limit exceeded` → Same fix

**Python / Import Errors**:
- `ModuleNotFoundError: No module named 'pyspark'` → `pip install pyspark` not run or wrong virtual env
- `ModuleNotFoundError: No module named 'src'` → `python src/main.py` run from wrong directory; must run from project root
- `FileNotFoundError: config.yaml` → Same as above; `ConfigManager` resolves `config.yaml` relative to CWD

### For Each Error Found

1. Quote the specific error line
2. Explain what it means in the context of THIS pipeline
3. Show the exact fix (file path + line change or command to run)
4. If it's a config fix, show the exact `config.yaml` change

If no errors found in logs: check if the pipeline has been run yet. If not, suggest running `/run-pipeline` first and checking that the JDBC driver jar exists in `drivers/`.
