from pathlib import Path

from pyspark.sql import functions as F


class GoldLayer:
    def __init__(self, spark, config_manager, logger):
        self.spark = spark
        self.config = config_manager
        self.logger = logger
        self.gold_path = Path(self.config.get("paths.gold"))
        self.gold_path.mkdir(parents=True, exist_ok=True)

    def create_sales_summary(self, orders_df, order_items_df, products_df):
        try:
            self.logger.info("Creating sales summary...")

            df = (
                order_items_df.join(products_df, "product_id", "left")
                .join(orders_df, "order_id", "left")
                .select(
                    F.col("order_date"),
                    F.col("product_id"),
                    F.col("product_name"),
                    F.col("category"),
                    F.col("quantity"),
                    F.col("unit_price"),
                    F.col("line_total"),
                )
            )

            return df
        except Exception as e:
            self.logger.error(f"Error creating sales summary: {str(e)}")
            return None

    def create_daily_sales_by_category(self, sales_summary_df):
        try:
            self.logger.info("Creating daily sales by category...")

            df = (
                sales_summary_df.groupBy(F.col("order_date"), F.col("category"))
                .agg(F.sum("quantity").alias("total_quantity"), F.sum("line_total").alias("total_sales"))
                .orderBy("order_date", "category")
            )

            return df
        except Exception as e:
            self.logger.error(f"Error creating daily sales by category: {str(e)}")
            return None

    def create_product_performance(self, sales_summary_df):
        try:
            self.logger.info("Creating product performance...")

            df = (
                sales_summary_df.groupBy(F.col("product_id"), F.col("product_name"), F.col("category"))
                .agg(
                    F.sum("quantity").alias("total_quantity_sold"),
                    F.sum("line_total").alias("total_revenue"),
                    F.avg("unit_price").alias("avg_price"),
                )
                .orderBy(F.desc("total_revenue"))
            )

            return df
        except Exception as e:
            self.logger.error(f"Error creating product performance: {str(e)}")
            return None

    def save_gold_table(self, df, table_name):
        try:
            output_path = self.gold_path / table_name
            df.coalesce(1).write.mode("overwrite").parquet(str(output_path))
            self.logger.info(f"Saved gold layer table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error saving {table_name}: {str(e)}")
