import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402

load_dotenv()

if sys.platform == "win32":
    java_home = r"C:\Program Files\Java\jdk-21.0.11"
    hadoop_home = r"C:\hadoop"
    os.environ.setdefault("JAVA_HOME", java_home)
    os.environ.setdefault("HADOOP_HOME", hadoop_home)
    os.environ["PATH"] = (
        os.path.join(java_home, "bin")
        + os.pathsep
        + os.path.join(hadoop_home, "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )

from bronze.ingestion import BronzeLayer  # noqa: E402
from config.config_manager import ConfigManager  # noqa: E402
from utils.logger import PipelineLogger  # noqa: E402


def main():
    config = ConfigManager()
    logger_manager = PipelineLogger(config.get("paths.logs", "./logs"))
    logger = logger_manager.get_logger("DataPipeline")

    base = Path(__file__).parent.parent
    jdbc_driver = str(base / config.get("spark.jdbc_driver_path"))
    pg_driver = str(base / config.get("spark.pg_driver_path"))
    all_drivers = f"{jdbc_driver}:{pg_driver}"

    spark = (
        SparkSession.builder.appName(config.get("spark.app_name"))
        .master(config.get("spark.master"))
        .config("spark.driver.memory", config.get("spark.memory"))
        .config("spark.executor.memory", config.get("spark.executor_memory"))
        .config("spark.driver.extraClassPath", all_drivers)
        .config("spark.executor.extraClassPath", all_drivers)
        .getOrCreate()
    )

    logger.info("Starting data pipeline...")

    try:
        bronze = BronzeLayer(spark, config, logger)
        logger.info("Bronze layer initialized")

        # Ingest from SQL Server
        bronze.ingest_all_tables()

        # Ingest from PostgreSQL
        bronze.ingest_all_pg_tables()

        # Silver and Gold transforms are handled dynamically via the /silver-gold skill.
        # Run: /silver-gold <table_name> [primary_key=<col>]

        logger.info("Bronze ingestion completed. Run /silver-gold <table> to transform.")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
