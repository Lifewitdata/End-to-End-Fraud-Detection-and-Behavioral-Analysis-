# Databricks notebook source
# MAGIC %md
# MAGIC # Payment transaction preparation and historical features
# MAGIC Optional cloud path; local parity is not proof of Databricks execution.
# MAGIC Install this repository on the cluster first. PaySim is simulated data.

# COMMAND ----------
dbutils.widgets.text('input_csv','')
dbutils.widgets.text('output_delta_path','')
source_path=dbutils.widgets.get('input_csv')
output_path=dbutils.widgets.get('output_delta_path')
assert source_path and output_path,'Set input CSV and a new Delta output path.'

# COMMAND ----------
from fraudrisk.spark_prepare import prepare,features
from pyspark.sql import functions as F
source=spark.read.option('header',True).csv(source_path)
prepared=features(prepare(source)).cache()

# COMMAND ----------
# MAGIC %md
# MAGIC Features exclude all events in the current simulation hour.
# MAGIC row_id is an ingestion reference, not an immutable source transaction ID.
# MAGIC Duplicate-looking rows are retained because replay cannot be proven.

# COMMAND ----------
display(prepared.groupBy('type').agg(F.count('*').alias('transactions'),F.sum('amount').alias('transaction_value')))
assert prepared.count()==source.count(),'Row-count reconciliation failed'
prepared.write.format('delta').mode('errorifexists').save(output_path)
prepared.unpersist()
