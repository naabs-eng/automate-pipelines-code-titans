import os
import sys
from pathlib import Path

PROJECT_ROOT = Path("/mnt/c/Users/AbinashBhagat/Desktop/ClaudeDataPipeline")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

os.environ["JAVA_HOME"] = "/usr/lib/jvm/java-17-openjdk-amd64"
os.environ["PATH"] = os.environ["JAVA_HOME"] + "/bin:" + os.environ["PATH"]
os.environ["HADOOP_HOME"] = "/mnt/c/hadoop"

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from config.config_manager import ConfigManager
from utils.logger import PipelineLogger

config = ConfigManager(str(PROJECT_ROOT / "config.yaml"))
logger = PipelineLogger(str(PROJECT_ROOT / "logs")).get_logger("Test")
jdbc_driver = str(PROJECT_ROOT / config.get("spark.jdbc_driver_path"))

print(f"Server: {config.get('sql_server.server')}")
print(f"JDBC driver: {jdbc_driver}")
print(f"Driver exists: {Path(jdbc_driver).exists()}")

from pyspark.sql import SparkSession

spark = (
    SparkSession.builder.appName("Test")
    .master("local[*]")
    .config("spark.jars", jdbc_driver)
    .getOrCreate()
)

from bronze.ingestion import BronzeLayer

bronze = BronzeLayer(spark, config, logger)
bronze.ingest_all_tables()
spark.stop()
print("Done")
