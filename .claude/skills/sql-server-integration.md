---
name: SQL Server Integration
description: Use when working with SQL Server connectivity (JDBC or ODBC), configuring the JDBC driver, debugging connection errors, or managing SQL Server credentials in this pipeline.
---

# SQL Server Integration — ClaudeDataPipeline

## Two Connection Methods

| Method | Used For | Library | Where in Project |
|---|---|---|---|
| JDBC | Bulk reads from SQL Server into Spark | `spark.read.format("jdbc")` | `src/bronze/ingestion.py` |
| ODBC | Schema validation, ad-hoc queries | `pyodbc` | `src/config/config_manager.py` (available but unused in pipeline) |

---

## JDBC — Correct Configuration

### Connection URL for Windows Integrated Auth (Trusted Connection)

```python
# CORRECT — integratedSecurity goes in the URL, not as user/password options
jdbc_url = (
    f"jdbc:sqlserver://{server};"
    f"databaseName={database};"
    "integratedSecurity=true;"
    "authenticationScheme=NativeAuthentication"
)

df = spark.read \
    .format("jdbc") \
    .option("url", jdbc_url) \
    .option("dbtable", "dbo.Products") \
    .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
    .load()
```

**Current bug in `src/bronze/ingestion.py`**: The code passes `.option("user", "")` and `.option("password", "")`. For Windows auth, these should be omitted entirely and `integratedSecurity=true` should be in the URL. The current code may fail silently or cause auth errors.

### Connection URL for SQL Auth (Username/Password)

```python
# Load credentials from environment — never hardcode
import os
from dotenv import load_dotenv
load_dotenv()

jdbc_url = f"jdbc:sqlserver://{server};databaseName={database}"

df = spark.read \
    .format("jdbc") \
    .option("url", jdbc_url) \
    .option("dbtable", "dbo.Products") \
    .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
    .option("user", os.getenv("SQL_USER")) \
    .option("password", os.getenv("SQL_PASSWORD")) \
    .load()
```

Add to `.env` (gitignored):
```
SQL_USER=your_sql_login
SQL_PASSWORD=your_password
```

---

## JDBC Driver Jar — Required Setup

PySpark cannot connect to SQL Server without the MSSQL JDBC jar. This is the most common first-run failure.

**Steps**:
1. Download from Microsoft: `mssql-jdbc-12.4.2.jre11.jar` (use JRE11 version for Java 11 compatibility)
2. Place in `drivers/` folder (create it at project root)
3. Add to `config.yaml`:
   ```yaml
   spark:
     jdbc_driver_path: "drivers/mssql-jdbc-12.4.2.jre11.jar"
   ```
4. Wire in `main.py` SparkSession builder:
   ```python
   .config("spark.jars", config.get('spark.jdbc_driver_path'))
   ```
5. Add `drivers/` to `.gitignore` (binary file, don't commit)

---

## ODBC Connection String (pyodbc)

Used for validation queries outside of Spark:

```python
import pyodbc

connection_string = (
    "Driver={ODBC Driver 17 for SQL Server};"
    "Server=localhost;"
    "Database=SalesDB;"
    "Trusted_Connection=yes"
)
conn = pyodbc.connect(connection_string)
```

For a named SQL Server instance (e.g. `SQLEXPRESS`):
```
Server=localhost\SQLEXPRESS
```

---

## Table Reference Format

Always use fully-qualified names: `dbo.TableName`

```python
# In JDBC dbtable option:
.option("dbtable", "dbo.Products")       # correct
.option("dbtable", "Products")           # may fail depending on default schema

# In SQL queries (if using dbtable with a subquery):
.option("dbtable", "(SELECT * FROM dbo.Products WHERE UnitPrice > 0) AS p")
```

---

## SQL Server Configuration for Local Dev

In **SQL Server Configuration Manager**:
1. Enable TCP/IP protocol: `SQL Server Network Configuration → Protocols for SQLSERVER → TCP/IP → Enable`
2. Set TCP port to 1433: `TCP/IP Properties → IP Addresses → IPAll → TCP Port = 1433`
3. Ensure SQL Server Browser service is running (needed for named instances)
4. Restart SQL Server service after changes

---

## Common Connection Failures & Fixes

| Error | Cause | Fix |
|---|---|---|
| `ClassNotFoundException: com.microsoft.sqlserver.jdbc.SQLServerDriver` | JDBC jar not on Spark classpath | Add jar to `spark.jars` in SparkSession config |
| `No suitable driver found for jdbc:sqlserver` | Same as above | Same fix |
| `Login failed for user ''` | Windows auth not configured in JDBC URL | Use `integratedSecurity=true` in URL, remove user/password options |
| `TCP/IP connection to localhost:1433 failed` | TCP/IP not enabled in SQL Server Config Manager | Enable TCP/IP, set port 1433, restart SQL Server service |
| `Cannot open server 'localhost'` | SQL Server Browser not running, or named instance needs `\\INSTANCE` | Use `localhost\SQLEXPRESS` for named instances |
| `pyodbc.Error: ('IM002', ...)` | ODBC Driver 17 not installed | Install "Microsoft ODBC Driver 17 for SQL Server" from Microsoft's website |
| `com.microsoft.sqlserver.jdbc.SQLServerException: The driver could not establish a secure connection` | SSL/TLS version mismatch | Add `encrypt=false;trustServerCertificate=true` to JDBC URL for local dev |

For local dev with self-signed certificate, add to JDBC URL:
```
;encrypt=false;trustServerCertificate=true
```

Full example for local dev:
```python
jdbc_url = (
    f"jdbc:sqlserver://localhost;"
    f"databaseName=SalesDB;"
    "integratedSecurity=true;"
    "authenticationScheme=NativeAuthentication;"
    "encrypt=false;"
    "trustServerCertificate=true"
)
```

---

## SQL Server Schema for This Project

```sql
-- Verify tables exist
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_NAME;

-- Verify row counts
SELECT 'Products' as tbl, COUNT(*) as rows FROM dbo.Products
UNION ALL SELECT 'Customers', COUNT(*) FROM dbo.Customers
UNION ALL SELECT 'Orders', COUNT(*) FROM dbo.Orders
UNION ALL SELECT 'OrderItems', COUNT(*) FROM dbo.OrderItems;
```

Run via sqlcmd (command line):
```bash
sqlcmd -S localhost -d SalesDB -E -Q "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo'"
```
