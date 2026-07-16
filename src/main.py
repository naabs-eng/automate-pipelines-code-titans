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
    pg_driver = str(base / config.get("spark.pg_driver_path"))

    spark = (
        SparkSession.builder.appName(config.get("spark.app_name"))
        .master(config.get("spark.master"))
        .config("spark.driver.memory", config.get("spark.memory"))
        .config("spark.executor.memory", config.get("spark.executor_memory"))
        .config("spark.driver.extraClassPath", pg_driver)
        .config("spark.executor.extraClassPath", pg_driver)
        .getOrCreate()
    )

    logger.info("Starting data pipeline...")

    try:
        BronzeLayer(spark, config, logger)
        logger.info("Bronze layer initialized")

        logger.info("Bronze ingestion completed. Use run_bronze.py / run_silver_gold.py via the Streamlit UI.")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
