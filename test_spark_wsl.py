import os
import sys

sys.path.insert(0, "src")
os.environ["JAVA_HOME"] = "/usr/lib/jvm/java-17-openjdk-amd64"
os.environ["PATH"] = os.environ["JAVA_HOME"] + "/bin:" + os.environ["PATH"]

from dotenv import load_dotenv
from pyspark.sql import SparkSession

load_dotenv(".env")

spark = SparkSession.builder.master("local").appName("test").getOrCreate()
print("Spark started OK")
spark.stop()
print("Done")
