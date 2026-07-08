import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from pyspark.sql import SparkSession

load_dotenv()

from bronze.ingestion import BronzeLayer
from config.config_manager import ConfigManager
from utils.logger import PipelineLogger


def main():
    parser = argparse.ArgumentParser(description="Run Bronze ingestion for specific tables")
    parser.add_argument("--source", required=True, choices=["postgresql", "sqlserver"],
                        help="Source type")
    parser.add_argument("--tables", required=True,
                        help="Comma-separated list of fully qualified table names (e.g. public.suppliers,public.inventory)")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    if not tables:
        print("ERROR: No tables specified")
        sys.exit(1)

    config = ConfigManager()
    logger_manager = PipelineLogger(config.get("paths.logs", "./logs"))
    logger = logger_manager.get_logger("BronzeRunner")

    base = Path(__file__).parent.parent
    pg_driver = str(base / config.get("spark.pg_driver_path"))
    jdbc_driver = str(base / config.get("spark.jdbc_driver_path"))
    all_drivers = f"{jdbc_driver}:{pg_driver}"

    print(f"Starting Bronze ingestion | source={args.source} | tables={tables}")

    spark = (
        SparkSession.builder.appName("BronzeRunner")
        .master(config.get("spark.master", "local[*]"))
        .config("spark.driver.memory", config.get("spark.memory", "2g"))
        .config("spark.driver.extraClassPath", all_drivers)
        .config("spark.executor.extraClassPath", all_drivers)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    bronze = BronzeLayer(spark, config, logger)
    success_tables = []
    failed_tables = []

    for table in tables:
        bronze_name = table.split(".")[-1]
        if args.source == "postgresql":
            ok = bronze.ingest_from_postgresql(table, bronze_name)
        else:
            ok = bronze.ingest_from_sql_server(table, bronze_name)

        if ok:
            success_tables.append(table)
            print(f"SUCCESS: {table} -> data/bronze/{bronze_name}")
        else:
            failed_tables.append(table)
            print(f"FAILED: {table}")

    spark.stop()

    print(f"\nDone. {len(success_tables)} succeeded, {len(failed_tables)} failed.")
    if failed_tables:
        print(f"Failed tables: {', '.join(failed_tables)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
