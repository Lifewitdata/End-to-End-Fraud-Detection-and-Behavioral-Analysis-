"""Run from project root: python -m streamlit run dashboard/app.py"""
import json
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Payment Fraud Risk Observatory",layout="wide")
root=Path(__file__).resolve().parents[1]
out=Path(os.environ.get("FRAUD_OUTPUT_DIR",str(root/"outputs")))
st.title("Payment Fraud Risk Observatory")
if not (out/"manifest.json").exists():
    st.info("Run python -m fraudrisk.pipeline --demo, or supply --input data/PS_log.csv, before opening this dashboard.")
    st.stop()
manifest=json.loads((out/"manifest.json").read_text())
st.warning(manifest["mode"]+". Offline analysis; no actual payment blocks, savings or completed investigations.")
st.caption("Scores rank risk; they are not calibrated probabilities. All values use dataset currency units.")
@st.cache_data
def load(path,stamp):
    return pd.read_csv(path)
def read(name):
    path=out/name
    return load(str(path),path.stat().st_mtime_ns)

pages=st.tabs(["Overview","Investigation queue","Rule & model evaluation","Drift & data quality","Decision brief"])
with pages[0]:
    policies=read("policy_comparison.csv")
    m=policies.set_index("policy").loc["selected_model"]
    if not bool(m.capacity_feasible):
        st.error("The locked model breaches peak review capacity in the test period. Revise on a new validation period before a pilot.")
    cols=st.columns(4)
    for col,label,value in zip(cols,["Review alerts","Alert precision","Fraud recall","Missed fraud value"],
                               [f"{int(m.alerts):,}",f"{m.precision:.1%}",f"{m.recall:.1%}",f"{m.missed_fraud_value:,.2f}"]):
        col.metric(label,value)
    st.plotly_chart(px.line(read("hourly_chart.csv"),x="step",y=["alerts","confirmed_fraud","fraud_count_24h_average"]),width="stretch")
    st.caption("Step is a simulation hour; the rolling series averages fraud counts over 24 hourly steps.")
    st.dataframe(read("type_summary.csv"),hide_index=True)
with pages[1]:
    q=read("alert_queue.csv")
    choice=st.selectbox("Transaction type",["All"]+sorted(q.type.dropna().unique().tolist()))
    if choice!="All":
        q=q[q.type==choice]
    st.write(f"{len(q):,} alerts. Case status is Unreviewed; due_step is a proposed SLA, not a measured response time.")
    st.dataframe(q.head(1000),hide_index=True)
    st.download_button("Download filtered review queue",q.to_csv(index=False),"review_queue.csv","text/csv")
    st.markdown((out/"investigations.md").read_text())
with pages[2]:
    st.caption("Model/threshold selected on validation cost. Test policy comparisons use frozen settings and are retrospective.")
    st.dataframe(read("validation_models.csv"),hide_index=True)
    st.dataframe(policies,hide_index=True)
    st.plotly_chart(px.bar(policies,x="policy",y=["tp","fp","fn"],barmode="group"),width="stretch")
    st.dataframe(read("ranking_metrics.csv"),hide_index=True)
    st.subheader("Cost sensitivity of the locked policy")
    st.dataframe(read("cost_sensitivity.csv"),hide_index=True)
    st.caption("No test-threshold slider is provided: changing thresholds against these labels would invalidate the final test.")
with pages[3]:
    st.dataframe(read("monitoring_alerts.csv"),hide_index=True)
    st.dataframe(read("drift.csv"),hide_index=True)
    st.caption("PSI compares validation and test populations; 0.10/0.20 are illustrative review triggers, not universal standards.")
    st.dataframe(read("data_quality.csv"),hide_index=True)
    st.json(manifest)
with pages[4]:
    st.markdown((out/"stakeholder_brief.md").read_text())
