"""Run: python -m fraudrisk.pipeline --demo OR --input data/PS_log.csv."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import os
import tempfile
from pathlib import Path
import duckdb
import joblib
import numpy as np
import pandas as pd
from .data import make_demo, validate
from .evaluation import FEATURES, NUMERIC, fit_models, time_split, metrics, select_threshold, ranking_metrics, rule_flags, psi
from .reporting import write_reports

ROOT = Path(__file__).resolve().parents[2]

def build_features(df, con):
    con.register("input_frame", df)
    con.execute("CREATE OR REPLACE TABLE transactions AS SELECT * FROM input_frame")
    con.execute((ROOT/"sql/features.sql").read_text())
    return con.execute("SELECT * FROM features ORDER BY step, row_id").df()

def run(input_path=None, output_dir="outputs", demo=False, config_path=None):
    """Build in a fresh database; publish artifacts only after a successful run."""
    out=Path(output_dir).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fraud-build-",dir=out.parent) as temp:
        stage=Path(temp)
        result=_run_into(input_path,stage,demo,config_path)
        out.mkdir(parents=True,exist_ok=True)
        previous=[]
        if (out/"manifest.json").exists():
            previous=json.loads((out/"manifest.json").read_text()).get("generated_artifacts",[])
        names=sorted(p.name for p in stage.iterdir() if p.is_file())
        result["generated_artifacts"]=names
        (stage/"manifest.json").write_text(json.dumps(result,indent=2))
        # Manifest goes last: consumers use it to identify a completed run.
        for name in [x for x in names if x!="manifest.json"]+["manifest.json"]:
            if name=="fraud.duckdb":
                (out/"fraud.duckdb.wal").unlink(missing_ok=True)
            os.replace(stage/name,out/name)
        for name in set(previous)-set(names):
            if Path(name).name==name and (out/name).is_file():
                (out/name).unlink()
        return result

def _run_into(input_path=None, output_dir="outputs", demo=False, config_path=None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(config_path or ROOT/"config/analysis.json").read_text())
    if demo:
        input_path = out/"integration_fixture.csv"
        make_demo(input_path, seed=cfg["seed"])
    if not input_path or not Path(input_path).is_file():
        raise FileNotFoundError("Supply --input data/PS_log.csv; see data/README.md. --demo is a separate synthetic integration fixture.")
    path = Path(input_path)
    raw, dq = validate(pd.read_csv(path))
    pd.DataFrame([{"check": k, "value": v} for k,v in dq.items()]).to_csv(out/"data_quality.csv", index=False)
    con = duckdb.connect(str(out/"fraud.duckdb"))
    try:
        df = build_features(raw, con)
        train, val, test = time_split(df, cfg)
        models, fit_rows = fit_models(train, cfg)
        choices, sweeps = [], []
        for name, model in models.items():
            scores = model.predict_proba(val[FEATURES])[:,1]
            threshold, table = select_threshold(val, scores, cfg)
            table["model"] = name
            sweeps.append(table)
            choices.append(dict(model=name, threshold=threshold,
                **metrics(val, scores>=threshold, cfg), **ranking_metrics(val, scores)))
        validation = pd.DataFrame(choices)
        selected = validation.sort_values(["scenario_total_cost", "model"]).iloc[0]
        selected_name, threshold = str(selected.model), float(selected.threshold)
        model = models[selected_name]
        # Model and threshold are locked before any test predictions or labels are evaluated.
        scores = model.predict_proba(test[FEATURES])[:,1]
        pred = scores>=threshold
        test["score"] = scores
        test["risk_score"] = np.round(scores*100, 1)
        test["prediction"] = pred.astype(int)
        test["risk_band"] = np.where(pred, "Review", "Monitor")
        rules = rule_flags(test, cfg)
        union = np.logical_or.reduce(list(rules.values()))
        policies = {**rules, "rules_union":union, "selected_model":pred, "hybrid_union":pred|union}
        evaluations = []
        for name, p in policies.items():
            evaluations.append(dict(policy=name, **metrics(test,p,cfg)))
        comparison = pd.DataFrame(evaluations)
        for name, p in rules.items():
            test[name] = p.astype(int)
        reasons = pd.Series("", index=test.index)
        for name, flag in rules.items():
            reasons = reasons + np.where(flag, name+";", "")
        test["triggered_rules"] = reasons.str.rstrip(";")
        test["reason_code"] = np.where(pred, "MODEL_THRESHOLD", "BELOW_THRESHOLD")
        # Outcome labels are displayed only as retrospective evaluation, not detection inputs.
        test["outcome"] = np.select([pred & test.isFraud.eq(1), pred & test.isFraud.eq(0),
            ~pred & test.isFraud.eq(1)], ["TP", "FP", "FN"], default="TN")
        validation.to_csv(out/"validation_models.csv", index=False)
        pd.concat(sweeps, ignore_index=True).to_csv(out/"validation_thresholds.csv", index=False)
        comparison.to_csv(out/"policy_comparison.csv", index=False)
        test.to_csv(out/"test_scored.csv", index=False)
        queue = test[pred].sort_values(["score", "amount"], ascending=False).copy()
        queue["case_id"] = "CASE-" + queue.row_id.astype(str)
        queue["status"] = "Unreviewed"
        queue["owner"] = cfg["rule_owner"]
        queue["created_step"] = queue.step
        queue["due_step"] = queue.step+1
        queue["closed_step"] = np.nan
        # No closure duration is invented; this is an offline queue simulation.
        queue.to_csv(out/"alert_queue.csv", index=False)
        con.register("test_frame",test)
        con.execute("CREATE OR REPLACE TABLE test_scored AS SELECT * FROM test_frame")
        con.register("rule_registry",pd.read_csv(ROOT/"config/rule_registry.csv"))
        con.execute((ROOT/"sql/monitoring.sql").read_text())
        for table in ["hourly_monitoring", "recipient_investigation", "rule_performance"]:
            con.execute(f"SELECT * FROM {table}").df().to_csv(out/f"{table}.csv",index=False)
        drift=[]
        for name in NUMERIC:
            value=psi(val[name].fillna(0),test[name].fillna(0))
            drift.append(dict(feature=name,psi=value,status="Investigate" if value>=.2 else "Watch" if value>=.1 else "Stable"))
        pd.DataFrame(drift).to_csv(out/"drift.csv",index=False)
        operational=[]
        for row in evaluations:
            if not row["capacity_feasible"]:
                operational.append(dict(policy=row["policy"],issue="PEAK_CAPACITY_BREACH",owner=cfg["rule_owner"],
                    evidence=f"Peak {row['peak_alerts_per_step']} exceeds {cfg['review_capacity_per_step']} per hourly step",
                    action="Do not enforce; review queue capacity and validate a revised policy on a new period"))
        for row in drift:
            if row["status"]=="Investigate":
                operational.append(dict(policy="selected_model",issue="POPULATION_DRIFT",owner="Data Science",
                    evidence=f"{row['feature']} PSI={row['psi']:.3f}",action="Review feature population and delayed outcome metrics"))
        pd.DataFrame(operational,columns=["policy","issue","owner","evidence","action"]).to_csv(out/"monitoring_alerts.csv",index=False)
        # Sensitivity evaluates the locked policy; it never retunes using test outcomes.
        pd.DataFrame([dict(action_success_fraction=x, **metrics(test,pred,{**cfg,"action_success_fraction":x}))
                      for x in [.25,.5,.75]]).to_csv(out/"cost_sensitivity.csv",index=False)
        # Retrospective balance checks: descriptive only, no causal or prepayment claims.
        balance=pd.DataFrame([dict(isFraud=int(label),rows=len(g),
            sender_zero_share=float(g.newbalanceOrig.eq(0).mean()),
            destination_unchanged_share=float(g.newbalanceDest.eq(g.oldbalanceDest).mean()))
            for label,g in df.groupby("isFraud")])
        balance.to_csv(out/"retrospective_balances.csv",index=False)
        con.execute("SELECT type,COUNT(*) AS transactions,SUM(isFraud) AS fraud_cases,AVG(isFraud) AS fraud_rate FROM transactions GROUP BY type ORDER BY type").df().to_csv(out/"type_summary.csv",index=False)
        val_scores=model.predict_proba(val[FEATURES])[:,1]
        pd.DataFrame([dict(period=name,**ranking_metrics(part,s)) for name,part,s in
                      [("validation",val,val_scores),("test",test,scores)]]).to_csv(out/"ranking_metrics.csv",index=False)
        imp=models[selected_name].named_steps["model"]
        names=models[selected_name].named_steps["prepare"].get_feature_names_out()
        values=imp.feature_importances_ if hasattr(imp,"feature_importances_") else np.abs(imp.coef_[0])
        pd.DataFrame(dict(feature=names,importance=values)).sort_values("importance",ascending=False).to_csv(out/"feature_importance.csv",index=False)
        joblib.dump(model,out/"model.joblib")
        digest=hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):
                digest.update(chunk)
        manifest=dict(mode="INTEGRATION FIXTURE — NOT PAYSIM RESULTS" if demo else "USER-SUPPLIED PAYSIM CSV",
            input_sha256=digest.hexdigest(),input_rows=len(df),fit_rows=fit_rows,
            selected_model=selected_name,threshold=threshold,features=FEATURES,config=cfg,
            splits={name:dict(rows=len(part),first_step=int(part.step.min()),last_step=int(part.step.max()),fraud=int(part.isFraud.sum()))
                    for name,part in zip(["train","validation","test"],[train,val,test])},
            python=platform.python_version(),versions={p:importlib.metadata.version(p) for p in ["pandas","numpy","scikit-learn","duckdb"]},
            decision="Offline triage simulation; no transaction is actually blocked or loss prevented")
        (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
        write_reports(out,manifest,test,comparison,df)
        return manifest
    finally:
        con.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input",type=Path)
    mode.add_argument("--demo",action="store_true")
    p.add_argument("--output",default="outputs")
    p.add_argument("--config",type=Path)
    args=p.parse_args()
    result=run(args.input,args.output,args.demo,args.config)
    print(json.dumps({k:result[k] for k in ["mode","input_rows","selected_model","threshold"]},indent=2))

if __name__=="__main__":
    main()
