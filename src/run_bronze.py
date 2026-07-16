import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402

load_dotenv()

from bronze.ingestion import BronzeLayer  # noqa: E402
from config.config_manager import ConfigManager  # noqa: E402
from utils.logger import PipelineLogger  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Run Bronze ingestion for specific tables")
    parser.add_argument("--source", required=True, choices=["postgresql", "file"], help="Source type")
    parser.add_argument(
        "--tables", required=True, help="Comma-separated table names (PostgreSQL: schema.table | File: filename.ext)"
    )
    parser.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental"],
        help="Load mode: full (overwrite) or incremental (append, schema-evolving)",
    )
    parser.add_argument(
        "--watermark-col", default=None, help="Column for incremental watermark (PostgreSQL only, optional)"
    )
    parser.add_argument("--pg-host", default=None, help="Override PostgreSQL host for this run")
    parser.add_argument("--pg-port", default=None, type=int, help="Override PostgreSQL port for this run")
    parser.add_argument("--pg-database", default=None, help="Override PostgreSQL database for this run")
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

    print(f"Starting Bronze ingestion | source={args.source} | mode={args.mode} | tables={tables}")

    spark = (
        SparkSession.builder.appName("BronzeRunner")
        .master(config.get("spark.master", "local[*]"))
        .config("spark.driver.memory", config.get("spark.memory", "2g"))
        .config("spark.driver.extraClassPath", pg_driver)
        .config("spark.executor.extraClassPath", pg_driver)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    bronze = BronzeLayer(spark, config, logger)
    success_tables = []
    failed_tables = []

    for table in tables:
        if args.source == "postgresql":
            bronze_name = f"{table.split('.')[-1]}_bronze"
            ok = bronze.ingest_from_postgresql(
                table,
                bronze_name,
                mode=args.mode,
                watermark_col=args.watermark_col,
                host=args.pg_host,
                port=args.pg_port,
                database=args.pg_database,
            )
        else:
            bronze_name = f"{Path(table).stem}_bronze"
            p = Path(table)
            # Use path as-is when absolute OR when it already contains a directory
            # component (e.g. ./data/sources/file.csv passed by the UI).
            # Only prepend the global base_dir for bare filenames (e.g. file.csv).
            if p.is_absolute() or p.parent != Path("."):
                file_path = str(p)
            else:
                file_path = str(Path(config.get("file_sources.base_dir", "./data/sources")) / table)
            file_format = p.suffix.lower().lstrip(".")
            ok = bronze.ingest_from_file(file_path, file_format, bronze_name, mode=args.mode)

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
