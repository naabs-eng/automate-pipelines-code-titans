from pyspark.sql import SparkSession
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from config.config_manager import ConfigManager
from utils.logger import PipelineLogger
from bronze.ingestion import BronzeLayer
from silver.transformations import SilverLayer
from gold.aggregations import GoldLayer


def main():
    config = ConfigManager()
    logger_manager = PipelineLogger(config.get("paths.logs", "./logs"))
    logger = logger_manager.get_logger("DataPipeline")

    jdbc_driver = str(Path(__file__).parent.parent / config.get("spark.jdbc_driver_path"))

    spark = (
        SparkSession.builder.appName(config.get("spark.app_name"))
        .master(config.get("spark.master"))
        .config("spark.driver.memory", config.get("spark.memory"))
        .config("spark.executor.memory", config.get("spark.executor_memory"))
        .config("spark.jars", jdbc_driver)
        .getOrCreate()
    )

    logger.info("Starting data pipeline...")

    try:
        bronze = BronzeLayer(spark, config, logger)
        logger.info("Bronze layer initialized")

        silver = SilverLayer(spark, config, logger)
        logger.info("Silver layer initialized")

        gold = GoldLayer(spark, config, logger)
        logger.info("Gold layer initialized")

        bronze.ingest_all_tables()

        bronze_products = spark.read.parquet(str(Path(config.get("paths.bronze")) / "products"))
        silver_products = silver.transform_products(bronze_products)
        if silver_products:
            silver.save_silver_table(silver_products, "products")

        bronze_customers = spark.read.parquet(str(Path(config.get("paths.bronze")) / "customers"))
        silver_customers = silver.transform_customers(bronze_customers)
        if silver_customers:
            silver.save_silver_table(silver_customers, "customers")

        bronze_orders = spark.read.parquet(str(Path(config.get("paths.bronze")) / "orders"))
        silver_orders = silver.transform_orders(bronze_orders)
        if silver_orders:
            silver.save_silver_table(silver_orders, "orders")

        bronze_order_items = spark.read.parquet(str(Path(config.get("paths.bronze")) / "order_items"))
        silver_order_items = silver.transform_order_items(bronze_order_items)
        if silver_order_items:
            silver.save_silver_table(silver_order_items, "order_items")

        sales_summary = gold.create_sales_summary(silver_orders, silver_order_items, silver_products)
        if sales_summary:
            gold.save_gold_table(sales_summary, "sales_summary")

            daily_sales = gold.create_daily_sales_by_category(sales_summary)
            if daily_sales:
                gold.save_gold_table(daily_sales, "daily_sales_by_category")

            product_perf = gold.create_product_performance(sales_summary)
            if product_perf:
                gold.save_gold_table(product_perf, "product_performance")

        logger.info("Data pipeline completed successfully!")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
