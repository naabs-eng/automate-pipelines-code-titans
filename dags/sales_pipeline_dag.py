import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path("/mnt/c/Users/AbinashBhagat/Desktop/ClaudeDataPipeline")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import os

os.environ.setdefault("JAVA_HOME", "/usr/lib/jvm/java-17-openjdk-amd64")
os.environ.setdefault("HADOOP_HOME", "/mnt/c/hadoop")
os.environ["PATH"] = os.environ["JAVA_HOME"] + "/bin:" + os.environ.get("PATH", "")

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# WSL2 mirrored networking mode allows localhost to reach Windows SQL Server directly

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def run_bronze():
    from pyspark.sql import SparkSession

    from bronze.ingestion import BronzeLayer
    from config.config_manager import ConfigManager
    from utils.logger import PipelineLogger

    config = ConfigManager(str(PROJECT_ROOT / "config.yaml"))
    logger = PipelineLogger(str(PROJECT_ROOT / "logs")).get_logger("Bronze")
    jdbc_driver = str(PROJECT_ROOT / config.get("spark.jdbc_driver_path"))

    spark = (
        SparkSession.builder.appName("SalesPipeline-Bronze")
        .master("local[*]")
        .config("spark.jars", jdbc_driver)
        .getOrCreate()
    )
    try:
        BronzeLayer(spark, config, logger).ingest_all_tables()
    finally:
        spark.stop()


def run_silver():
    from pyspark.sql import SparkSession

    from config.config_manager import ConfigManager
    from silver.transformations import SilverLayer
    from utils.logger import PipelineLogger

    config = ConfigManager(str(PROJECT_ROOT / "config.yaml"))
    logger = PipelineLogger(str(PROJECT_ROOT / "logs")).get_logger("Silver")
    jdbc_driver = str(PROJECT_ROOT / config.get("spark.jdbc_driver_path"))

    spark = (
        SparkSession.builder.appName("SalesPipeline-Silver")
        .master("local[*]")
        .config("spark.jars", jdbc_driver)
        .getOrCreate()
    )
    try:
        silver = SilverLayer(spark, config, logger)
        bronze_path = PROJECT_ROOT / config.get("paths.bronze")
        for table in ["products", "customers", "orders", "order_items"]:
            df = spark.read.parquet(str(bronze_path / table))
            transform = getattr(silver, f"transform_{table}")
            result = transform(df)
            if result:
                silver.save_silver_table(result, table)
    finally:
        spark.stop()


def run_gold():
    from pyspark.sql import SparkSession

    from config.config_manager import ConfigManager
    from gold.aggregations import GoldLayer
    from silver.transformations import SilverLayer
    from utils.logger import PipelineLogger

    config = ConfigManager(str(PROJECT_ROOT / "config.yaml"))
    logger = PipelineLogger(str(PROJECT_ROOT / "logs")).get_logger("Gold")
    jdbc_driver = str(PROJECT_ROOT / config.get("spark.jdbc_driver_path"))

    spark = (
        SparkSession.builder.appName("SalesPipeline-Gold")
        .master("local[*]")
        .config("spark.jars", jdbc_driver)
        .getOrCreate()
    )
    try:
        silver = SilverLayer(spark, config, logger)
        gold = GoldLayer(spark, config, logger)
        silver_path = PROJECT_ROOT / config.get("paths.silver")

        silver_orders = spark.read.parquet(str(silver_path / "orders"))
        silver_order_items = spark.read.parquet(str(silver_path / "order_items"))
        silver_products = spark.read.parquet(str(silver_path / "products"))

        sales_summary = gold.create_sales_summary(silver_orders, silver_order_items, silver_products)
        if sales_summary:
            gold.save_gold_table(sales_summary, "sales_summary")
            daily = gold.create_daily_sales_by_category(sales_summary)
            if daily:
                gold.save_gold_table(daily, "daily_sales_by_category")
            perf = gold.create_product_performance(sales_summary)
            if perf:
                gold.save_gold_table(perf, "product_performance")
    finally:
        spark.stop()


with DAG(
    dag_id="sales_pipeline",
    description="Bronze → Silver → Gold medallion ETL pipeline",
    default_args=default_args,
    start_date=datetime(2026, 4, 28),
    schedule_interval="0 6 * * *",
    catchup=False,
    tags=["sales", "etl"],
) as dag:
    bronze_task = PythonOperator(task_id="bronze_ingestion", python_callable=run_bronze)
    silver_task = PythonOperator(task_id="silver_transformation", python_callable=run_silver)
    gold_task = PythonOperator(task_id="gold_aggregation", python_callable=run_gold)

    bronze_task >> silver_task >> gold_task
