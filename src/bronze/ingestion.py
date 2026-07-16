import getpass
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import functions as F


class BronzeLayer:
    _WATERMARKS_FILE = "data/bronze/.watermarks.json"

    def __init__(self, spark, config_manager, logger):
        self.spark = spark
        self.config = config_manager
        self.logger = logger
        self.bronze_path = Path(self.config.get("paths.bronze"))
        self.bronze_path.mkdir(parents=True, exist_ok=True)

    def _load_watermarks(self):
        wm = Path(self._WATERMARKS_FILE)
        return json.loads(wm.read_text()) if wm.exists() else {}

    def _save_watermark(self, table_name, data):
        wm = Path(self._WATERMARKS_FILE)
        wm.parent.mkdir(parents=True, exist_ok=True)
        watermarks = self._load_watermarks()
        watermarks[table_name] = data
        wm.write_text(json.dumps(watermarks, indent=2, default=str))

    def _add_audit_columns(self, df, source_name, mode):
        return (
            df.withColumn("_ingestion_timestamp", F.current_timestamp())
              .withColumn("_source_name", F.lit(source_name))
              .withColumn("_load_mode", F.lit(mode))
        )

    def _write_bronze(self, df, output_path, mode):
        """Write to Bronze with schema evolution support for incremental loads."""
        bronze_exists = output_path.exists() and any(output_path.iterdir())
        if mode == "incremental" and bronze_exists:
            existing = self.spark.read.parquet(str(output_path))
            existing_cols = {f.name: f.dataType for f in existing.schema}
            incoming_col_names = {f.name for f in df.schema}
            for col_name, col_type in existing_cols.items():
                if col_name not in incoming_col_names:
                    df = df.withColumn(col_name, F.lit(None).cast(col_type))
            df.coalesce(1).write.option("mergeSchema", "true").mode("append").parquet(str(output_path))
        else:
            df.coalesce(1).write.mode("overwrite").parquet(str(output_path))

    def ingest_from_postgresql(self, table_name, bronze_table_name, mode="full", watermark_col=None,
                               host=None, port=None, database=None):
        try:
            _host = host or self.config.get("postgresql.host")
            _port = port or self.config.get("postgresql.port")
            _database = database or self.config.get("postgresql.database")
            self.logger.info(
                f"Ingesting {table_name} from PostgreSQL {_host}:{_port}/{_database} (mode={mode})..."
            )

            jdbc_url = f"jdbc:postgresql://{_host}:{_port}/{_database}"
            props = {
                "user": os.environ.get("PG_USERNAME") or getpass.getuser(),
                "password": os.environ.get("PG_PASSWORD", ""),
                "driver": "org.postgresql.Driver",
            }

            if mode == "incremental" and watermark_col:
                watermarks = self._load_watermarks()
                last_value = watermarks.get(bronze_table_name, {}).get("last_watermark_value")
                if last_value:
                    query = f"(SELECT * FROM {table_name} WHERE {watermark_col} > '{last_value}') t"
                    df = self.spark.read.jdbc(url=jdbc_url, table=query, properties=props)
                else:
                    df = self.spark.read.jdbc(url=jdbc_url, table=table_name, properties=props)
            else:
                df = self.spark.read.jdbc(url=jdbc_url, table=table_name, properties=props)

            df = self._add_audit_columns(df, table_name, mode)
            output_path = self.bronze_path / bronze_table_name
            self._write_bronze(df, output_path, mode)

            row_count = df.count()
            self.logger.info(f"Successfully ingested {table_name} -> {bronze_table_name} ({row_count} rows)")

            wm_data = {
                "last_ingested": datetime.now(timezone.utc).isoformat(),
                "source_type": "postgresql",
                "mode": mode,
            }
            if watermark_col:
                max_val = df.agg(F.max(watermark_col)).collect()[0][0]
                wm_data["watermark_col"] = watermark_col
                wm_data["last_watermark_value"] = str(max_val) if max_val else None
            self._save_watermark(bronze_table_name, wm_data)

            return True
        except Exception as e:
            self.logger.error(f"Error ingesting {table_name} from PostgreSQL: {str(e)}")
            return False

    def ingest_from_file(self, file_path, file_format, bronze_table_name, mode="full"):
        try:
            path = Path(file_path)
            if not path.exists():
                self.logger.error(f"File not found: {file_path}")
                return False

            if not file_format:
                ext = path.suffix.lower().lstrip(".")
                file_format = {"tsv": "csv"}.get(ext, ext) or "csv"

            self.logger.info(f"Ingesting {path.name} (format={file_format}, mode={mode})...")

            if file_format in ("csv", "tsv"):
                sep = "\t" if file_format == "tsv" else ","
                df = (
                    self.spark.read
                    .option("comment", "/")
                    .csv(str(path), header=True, inferSchema=True, sep=sep)
                )
            elif file_format == "json":
                df = self.spark.read.json(str(path))
            elif file_format == "parquet":
                df = self.spark.read.parquet(str(path))
            else:
                self.logger.warning(f"Unknown format '{file_format}', attempting CSV read.")
                df = self.spark.read.csv(str(path), header=True, inferSchema=True)

            df = self._add_audit_columns(df, str(path), mode)
            output_path = self.bronze_path / bronze_table_name
            self._write_bronze(df, output_path, mode)

            row_count = df.count()
            self.logger.info(f"Successfully ingested {path.name} -> {bronze_table_name} ({row_count} rows)")

            self._save_watermark(bronze_table_name, {
                "last_ingested": datetime.now(timezone.utc).isoformat(),
                "source_type": "file",
                "mode": mode,
                "file_path": str(path),
            })
            return True
        except Exception as e:
            self.logger.error(f"Error ingesting file {file_path}: {str(e)}")
            return False

