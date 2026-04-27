# Sales Data Pipeline - Medallion Architecture

A Python + Apache Spark ETL pipeline using the medallion (bronze-silver-gold) architecture to process sales data from a local SQL Server.

## Architecture

### Medallion Layers

- **Bronze**: Raw data ingestion from SQL Server tables (Products, Customers, Orders, OrderItems)
- **Silver**: Cleaned and standardized data with type casting and validation
- **Gold**: Business-ready aggregated analytics (sales summary, daily sales by category, product performance)

## Project Structure

```
src/
├── bronze/          # Data ingestion from source systems
├── silver/          # Data transformation and cleaning
├── gold/            # Business aggregations and analytics
├── config/          # Configuration management
└── utils/           # Logging and utility functions

data/
├── bronze/          # Raw data (Parquet format)
├── silver/          # Transformed data
└── gold/            # Analytics data

logs/               # Pipeline execution logs
tests/              # Test files
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure SQL Server Connection

Edit `config.yaml` with your SQL Server details:

```yaml
sql_server:
  driver: "ODBC Driver 17 for SQL Server"
  server: "localhost"
  database: "SalesDB"
  trusted_connection: "yes"
```

### 3. Create Sample Data in SQL Server

Run the SQL scripts in `sql/` directory to create tables and sample data:

```sql
-- Run create_schema.sql in your SQL Server
-- This will create Products, Customers, Orders, and OrderItems tables
```

### 4. Run the Pipeline

```bash
python src/main.py
```

## Configuration (config.yaml)

- **SQL Server**: Connection details for source database
- **Spark**: Configuration for Spark session (master, memory, app name)
- **Paths**: Output directories for each medallion layer
- **Tables**: Source table mappings and bronze layer names

## Output

The pipeline generates Parquet files in:
- `data/bronze/` - Raw ingested data
- `data/silver/` - Cleaned and transformed data
- `data/gold/` - Aggregated analytics tables

## Data Flow

```
SQL Server → Bronze Layer (Raw) → Silver Layer (Clean) → Gold Layer (Analytics)
```

### Tables Generated

**Bronze Layer**:
- products
- customers
- orders
- order_items

**Silver Layer**:
- products (with standardized schema)
- customers (with standardized schema)
- orders (with date conversion)
- order_items (with calculated line_total)

**Gold Layer**:
- sales_summary (combined order and product information)
- daily_sales_by_category (aggregated daily sales by product category)
- product_performance (product-level metrics and revenue)

## Scheduling

To run daily, set up a scheduler:

**Windows Task Scheduler**:
- Create a task that runs: `python src/main.py`
- Schedule it to run daily at your preferred time

**Linux/Mac Cron**:
```bash
0 2 * * * cd /path/to/ClaudeDataPipeline && python src/main.py
```

## Logging

Pipeline logs are stored in `logs/` with timestamps. Check logs for:
- Data ingestion status
- Transformation details
- Error messages and debugging info

## Next Steps

1. Create SQL Server sample data (see sql/create_schema.sql)
2. Update config.yaml with your SQL Server connection details
3. Run `python src/main.py` to execute the pipeline
4. Verify output in `data/` directories
5. Set up scheduling for daily execution
