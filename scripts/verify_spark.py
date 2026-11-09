"""Compare Spark and DuckDB features on a generated fixture with boundary cases."""
import json,tempfile
from pathlib import Path
import duckdb
import pandas as pd
from pyspark.sql import SparkSession,functions as F
from fraudrisk.data import make_demo,validate
from fraudrisk.pipeline import build_features
from fraudrisk.evaluation import FEATURES
from fraudrisk.spark_prepare import prepare,features
spark=SparkSession.builder.master('local[2]').appName('fraud-feature-parity').config('spark.ui.enabled','false').config('spark.sql.shuffle.partitions','2').getOrCreate()
spark.sparkContext.setLogLevel('ERROR')
try:
    with tempfile.TemporaryDirectory() as temp:
        raw=make_demo(Path(temp)/'fixture.csv',rows=1200)
        raw.loc[:4,'nameOrig']='boundary-sender';raw.loc[:4,'nameDest']='boundary-recipient'
        raw.loc[:4,'step']=[1,2,2,25,26];raw.loc[:4,'amount']=[0,20,9999,40,50]
        d,_=validate(raw)
        with duckdb.connect() as con: expected=build_features(d,con).sort_values('row_id')
        source=spark.createDataFrame(d.to_dict('records'))
        actual=features(prepare(source)).toPandas().sort_values('row_id')
        pd.testing.assert_frame_equal(expected[FEATURES].reset_index(drop=True),actual[FEATURES].reset_index(drop=True),check_dtype=False,rtol=1e-10,atol=1e-10)
        rejected=0
        for col,value in [('amount',-1.0),('type','UNKNOWN'),('step',1.5)]:
            try: prepare(source.withColumn(col,F.lit(value)))
            except ValueError: rejected+=1
        assert rejected==3
        report={'status':'PASS','rows':len(d),'feature_columns':FEATURES,'invalid_input_checks':rejected,
                'spark_version':spark.version,'execution':'local[2], not Databricks',
                'coverage':'same-step exclusion, 24h boundary, zero denominators, null history, distinct counterparties'}
        path=Path('reports/verification/spark_parity.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally: spark.stop()
