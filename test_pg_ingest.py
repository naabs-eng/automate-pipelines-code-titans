import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from pyspark.sql import SparkSession

load_dotenv()

from bronze.ingestion import BronzeLayer
from config.config_manager import ConfigManager
from utils.logger import PipelineLogger

config = ConfigManager()
logger_manager = PipelineLogger(config.get("paths.logs", "./logs"))
logger = logger_manager.get_logger("PGTest")

base = Path(__file__).parent
pg_driver = str(base / config.get("spark.pg_driver_path"))

spark = (
    SparkSession.builder.appName("PGTest")
    .master("local[*]")
    .config("spark.driver.extraClassPath", pg_driver)
    .config("spark.executor.extraClassPath", pg_driver)
    .getOrCreate()
)

spark.sparkContext.setLogLevel("ERROR")

bronze = BronzeLayer(spark, config, logger)
bronze.ingest_all_pg_tables()

print("\n=== Bronze output ===")
for table in ["suppliers", "inventory", "shipments"]:
    path = Path(config.get("paths.bronze")) / table
    if path.exists():
        df = spark.read.parquet(str(path))
        print(f"\n{table} ({df.count()} rows):")
        df.show()
    else:
        print(f"{table}: not found")

spark.stop()
