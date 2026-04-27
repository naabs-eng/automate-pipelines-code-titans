from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, FloatType, TimestampType
from pathlib import Path

class SilverLayer:
    def __init__(self, spark, config_manager, logger):
        self.spark = spark
        self.config = config_manager
        self.logger = logger
        self.silver_path = Path(self.config.get('paths.silver'))
        self.silver_path.mkdir(parents=True, exist_ok=True)

    def transform_products(self, bronze_df):
        try:
            self.logger.info("Transforming products data...")
            df = bronze_df.select(
                F.col("ProductID").cast("int").alias("product_id"),
                F.col("ProductName").cast("string").alias("product_name"),
                F.col("Category").cast("string").alias("category"),
                F.col("UnitPrice").cast("float").alias("unit_price")
            )
            df = df.filter(F.col("product_id").isNotNull())
            return df
        except Exception as e:
            self.logger.error(f"Error transforming products: {str(e)}")
            return None

    def transform_customers(self, bronze_df):
        try:
            self.logger.info("Transforming customers data...")
            df = bronze_df.select(
                F.col("CustomerID").cast("int").alias("customer_id"),
                F.col("CustomerName").cast("string").alias("customer_name"),
                F.col("Email").cast("string").alias("email"),
                F.col("Country").cast("string").alias("country")
            )
            df = df.filter(F.col("customer_id").isNotNull())
            return df
        except Exception as e:
            self.logger.error(f"Error transforming customers: {str(e)}")
            return None

    def transform_orders(self, bronze_df):
        try:
            self.logger.info("Transforming orders data...")
            df = bronze_df.select(
                F.col("OrderID").cast("int").alias("order_id"),
                F.col("CustomerID").cast("int").alias("customer_id"),
                F.col("OrderDate").cast("timestamp").alias("order_date")
            )
            df = df.filter(F.col("order_id").isNotNull())
            return df
        except Exception as e:
            self.logger.error(f"Error transforming orders: {str(e)}")
            return None

    def transform_order_items(self, bronze_df):
        try:
            self.logger.info("Transforming order items data...")
            df = bronze_df.select(
                F.col("OrderItemID").cast("int").alias("order_item_id"),
                F.col("OrderID").cast("int").alias("order_id"),
                F.col("ProductID").cast("int").alias("product_id"),
                F.col("Quantity").cast("int").alias("quantity"),
                F.col("UnitPrice").cast("float").alias("unit_price")
            )
            df = df.withColumn("line_total", F.col("quantity") * F.col("unit_price"))
            df = df.filter(F.col("order_item_id").isNotNull())
            return df
        except Exception as e:
            self.logger.error(f"Error transforming order items: {str(e)}")
            return None

    def save_silver_table(self, df, table_name):
        try:
            output_path = self.silver_path / table_name
            df.coalesce(1).write.mode("overwrite").parquet(str(output_path))
            self.logger.info(f"Saved silver layer table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error saving {table_name}: {str(e)}")
