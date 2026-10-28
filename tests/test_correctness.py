import json
import duckdb
import numpy as np
import pandas as pd
import pytest
from fraudrisk.data import make_demo, validate
from fraudrisk.evaluation import FEATURES, metrics, select_threshold, time_split
from fraudrisk.pipeline import build_features, run, ROOT

@pytest.fixture(scope="module")
def cfg():
    return json.loads((ROOT/"config/analysis.json").read_text())

@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("input")/"demo.csv",rows=1200)

@pytest.mark.parametrize("column,value",[("amount",-1),("type","UNKNOWN"),("step",1.5),("isFraud",2),("nameOrig",""),("amount",np.inf)])
def test_rejects_invalid_inputs(raw,column,value):
    bad=raw.copy()
    bad[column]=bad[column].astype(object)
    bad.loc[0,column]=value
    with pytest.raises(ValueError):
        validate(bad)

def test_duplicates_preserved_and_reported(raw):
    combined=pd.concat([raw,raw.iloc[[0]]],ignore_index=True)
    d,report=validate(combined)
    assert len(d)==len(combined)
    assert report["duplicate_rows_preserved"]>=1

def test_same_step_and_future_are_excluded(raw):
    d,_=validate(raw.head(5))
    d["nameOrig"]="A"
    d["nameDest"]="B"
    d["step"]=[1,2,2,25,26]
    d["amount"]=[10,20,9999,40,50]
    with duckdb.connect() as con:
        f=build_features(d,con).set_index("row_id")
    assert f.loc[1,"sender_count_24h"]==1
    assert f.loc[2,"sender_count_24h"]==1
    assert f.loc[1,"sender_mean_24h"]==10
    assert f.loc[3,"sender_count_24h"]==3  # includes step1 at exact 24h boundary
    assert f.loc[4,"sender_count_24h"]==3  # excludes step1, includes both step2
    changed=d.copy()
    changed.loc[changed.step>=25,"amount"]=9999999
    with duckdb.connect() as con:
        newer=build_features(changed,con).set_index("row_id")
    pd.testing.assert_frame_equal(f.loc[[0,1,2],FEATURES],newer.loc[[0,1,2],FEATURES])

def test_no_balance_or_label_features():
    assert not any("balance" in c.lower() or "fraud" in c.lower() for c in FEATURES)
    assert "step" not in FEATURES

def test_chronological_disjoint_split(raw,cfg):
    d,_=validate(raw)
    tr,va,te=time_split(d,cfg)
    assert tr.step.max()<va.step.min()<te.step.min()
    assert va.step.max()<te.step.min()
    assert len(tr)+len(va)+len(te)==len(d)

def test_metrics_denominators_and_cost(cfg):
    d=pd.DataFrame(dict(step=[1,1,2,2],isFraud=[1,1,0,0],amount=[100,200,20,30]))
    m=metrics(d,[1,0,1,0],cfg)
    assert (m["tp"],m["fp"],m["fn"],m["tn"])==(1,1,1,1)
    assert m["precision"]==m["recall"]==m["false_positive_rate"]==.5
    assert m["captured_fraud_value"]==100 and m["missed_fraud_value"]==200
    assert m["scenario_total_cost"]==300-50+10+2

def test_no_alert_candidate_and_capacity(cfg):
    d=pd.DataFrame(dict(step=[1]*4,isFraud=[1,0,0,0],amount=[10,20,20,20]))
    t,table=select_threshold(d,np.array([.9,.8,.7,.6]),{**cfg,"review_capacity_per_step":0})
    chosen=table[table.threshold==t].iloc[0]
    assert chosen.alerts==0 and chosen.capacity_feasible

@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    out=tmp_path_factory.mktemp("run")
    manifest=run(output_dir=out,demo=True)
    return out,manifest

def test_pipeline_sql_and_python_agree(completed):
    out,manifest=completed
    scored=pd.read_csv(out/"test_scored.csv")
    hourly=pd.read_csv(out/"hourly_monitoring.csv")
    policies=pd.read_csv(out/"policy_comparison.csv").set_index("policy")
    rules=pd.read_csv(out/"rule_performance.csv").set_index("rule_id")
    assert hourly.transactions.sum()==len(scored)
    for col in ["true_positives","false_positives","false_negatives"]:
        short={"true_positives":"tp","false_positives":"fp","false_negatives":"fn"}[col]
        assert hourly[col].sum()==policies.loc["selected_model",short]
    for r in rules.index:
        assert rules.loc[r,"alerts"]==policies.loc[r,"alerts"]
        assert rules.loc[r,"true_positives"]==policies.loc[r,"tp"]
    assert scored.row_id.is_unique
    assert manifest["splits"]["validation"]["last_step"]<manifest["splits"]["test"]["first_step"]
    assert "INTEGRATION FIXTURE" in manifest["mode"]
    assert (out/"dashboard.html").stat().st_size>10000

def test_saved_policy_is_validation_choice(completed):
    out,manifest=completed
    val=pd.read_csv(out/"validation_models.csv").sort_values(["scenario_total_cost","model"])
    assert manifest["selected_model"]==val.iloc[0].model
    assert manifest["threshold"]==pytest.approx(val.iloc[0].threshold)
    assert (pd.read_csv(out/"alert_queue.csv").status=="Unreviewed").all()

def test_capacity_breach_is_reported(completed):
    out,manifest=completed
    policies=pd.read_csv(out/"policy_comparison.csv").set_index("policy")
    alerts=pd.read_csv(out/"monitoring_alerts.csv")
    for name,row in policies.iterrows():
        if not row.capacity_feasible:
            assert ((alerts.policy==name)&(alerts.issue=="PEAK_CAPACITY_BREACH")).any()
