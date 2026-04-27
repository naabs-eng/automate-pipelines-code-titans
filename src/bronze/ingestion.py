from pyspark.sql import SparkSession
import pyodbc
from pathlib import Path

class BronzeLayer:
    def __init__(self, spark, config_manager, logger):
        self.spark = spark
        self.config = config_manager
        self.logger = logger
        self.bronze_path = Path(self.config.get('paths.bronze'))
        self.bronze_path.mkdir(parents=True, exist_ok=True)

    def ingest_from_sql_server(self, table_name, bronze_table_name):
        try:
            self.logger.info(f"Ingesting {table_name} from SQL Server...")

            connection_string = self.config.get_sql_server_connection_string()

            df = self.spark.read \
                .format("jdbc") \
                .option("url", f"jdbc:sqlserver://{self.config.get('sql_server.server')};databaseName={self.config.get('sql_server.database')}") \
                .option("dbtable", table_name) \
                .option("user", "") \
                .option("password", "") \
                .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
                .load()

            output_path = self.bronze_path / bronze_table_name
            df.coalesce(1).write.mode("overwrite").parquet(str(output_path))

            self.logger.info(f"Successfully ingested {table_name} -> {bronze_table_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error ingesting {table_name}: {str(e)}")
            return False

    def ingest_all_tables(self):
        tables = self.config.get('tables.source', [])
        for table in tables:
            self.ingest_from_sql_server(table['name'], table['bronze_table'])
