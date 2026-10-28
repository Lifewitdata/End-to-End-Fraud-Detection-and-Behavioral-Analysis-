"""Generated evidence and a portable offline interactive report."""
from html import escape
import json
import pandas as pd
import plotly.express as px

def write_reports(out, manifest, test, comparison, history):
    mode=manifest["mode"]
    selected=comparison.set_index("policy").loc["selected_model"]
    baseline=comparison.set_index("policy").loc["R01_existing_flag"]
    fmt=lambda x:f"{x:,.2f}"
    recommendation=("Do not pilot the locked policy: its test-period peak workload breaches configured capacity. Use a new validation period for any revision."
                    if not bool(selected.capacity_feasible) else
                    "Consider a controlled retrospective review before a pilot; confirm label quality, operational capacity and customer-friction assumptions.")
    text=f"""# Payment Fraud Risk — Decision Brief

**Run basis: {mode}.** All values are in dataset currency units. No real-world savings claim.

## Decision
{recommendation}
Evaluate the locked {manifest['selected_model']} triage policy against the existing flag.
The model and threshold ({manifest['threshold']:.6f}) were selected using validation-period scenario cost,
subject to peak hourly alert capacity. Test results were evaluated afterward.

## Test evidence
| Measure | Selected model | Existing flag |
|---|---:|---:|
| Alerts | {int(selected.alerts):,} | {int(baseline.alerts):,} |
| Precision | {selected.precision:.2%} | {baseline.precision:.2%} |
| Recall | {selected.recall:.2%} | {baseline.recall:.2%} |
| Fraud value captured for review | {fmt(selected.captured_fraud_value)} | {fmt(baseline.captured_fraud_value)} |
| Fraud value missed | {fmt(selected.missed_fraud_value)} | {fmt(baseline.missed_fraud_value)} |
| Peak alerts / hourly step | {int(selected.peak_alerts_per_step)} | {int(baseline.peak_alerts_per_step)} |
| Scenario net benefit | {fmt(selected.scenario_net_benefit)} | {fmt(baseline.scenario_net_benefit)} |

No-alert periods have zero observed alert precision by convention; interpret counts alongside rates.

## Stakeholder actions
| Owner | Action | Acceptance measure | Rollback trigger |
|---|---|---|---|
| Risk | Review false positives and missed cases; approve a pilot threshold | Peak workload within configured capacity; review value recall | Capacity breach or unacceptable confirmed missed value |
| Product | Test proportionate customer confirmation before a hold | Measured completion and complaint rates in a future pilot | Material deterioration against agreed customer baseline |
| Engineering | Validate event timing, immutable IDs and replay results | No future-event features; reproducible input hash and SQL totals | Any temporal leakage or reconciliation failure |
| Compliance | Review permitted data use, retention and escalation policy | Institution-specific review recorded before deployment | Missing required governance approval |

## Limits and assumptions
- Captured fraud value is transaction value surfaced for review, not proven prevented loss.
- Action effectiveness ({manifest['config']['action_success_fraction']:.0%}), review cost and friction are configurable assumptions.
  See cost_sensitivity.csv. A lower-cost policy can still miss valuable cases.
- This is a synthetic-data evaluation; labels are treated as complete. Real labels are delayed and incomplete.
- No real timestamps, devices, locations, logins or investigation closure events are available.
  No actual investigation duration, account takeover cause or regulatory compliance is claimed.
- Step is an hourly simulation index. No calendar dates or within-step event order are invented.
- Confirmed counts and drift require review; no emails, blocks or filings are sent by this project.
"""
    (out/"stakeholder_brief.md").write_text(text)
    sections=[f"# Retrospective investigation examples\n\nRun: **{mode}**. Hypotheses require verification; labels do not establish root cause.\n"]
    chosen=set()
    for outcome,title in [("FN","Missed fraud"),("TP","Detected fraud"),("FP","Legitimate alert")]:
        candidates=test[(test.outcome==outcome)&(~test.row_id.isin(chosen))].sort_values("amount",ascending=False)
        if candidates.empty:
            sections.append(f"## {title}\nNo {outcome} case exists in this run. Do not invent an example.\n")
            continue
        row=candidates.iloc[0]
        chosen.add(row.row_id)
        events=history[((history.nameOrig==row.nameOrig)|(history.nameDest==row.nameDest)) &
                       (history.step<=row.step)].copy()
        timeline=events.groupby("step").agg(transactions=("row_id","size"),amount=("amount","sum"),confirmed_fraud=("isFraud","sum")).reset_index()
        timeline.to_csv(out/f"case_{outcome}_timeline.csv",index=False)
        sections.append(f"""## {title}: row {int(row.row_id)}
- Evidence: step {int(row.step)}, {row['type']}, amount {row.amount:,.2f}; sender {row.nameOrig}; recipient {row.nameDest}.
- Decision: {row.reason_code}; score {row.score:.6f}; outcome {outcome}.
- Prior 24-hour recipient activity: {int(row.recipient_count_24h)} transactions from {int(row.recipient_senders_24h)} senders.
- Existing/rule evidence: {row.triggered_rules or 'No configured rule triggered'}.
- Working hypothesis: {'The locked policy did not rank this labelled case above its operating threshold.' if outcome=='FN' else 'The available signals met the review threshold; this does not prove an account was compromised.' if outcome=='TP' else 'Legitimate activity overlapped the model risk pattern, creating avoidable review workload.'}
- Proposed response: {'Investigate historical recipient patterns and test a candidate control on a new validation period.' if outcome=='FN' else 'Review sender/recipient history and request additional evidence before any hold.' if outcome=='TP' else 'Review the reason and transaction context; test segment-aware refinements before changing the threshold.'}
- Owner: Payments Risk, supported by Product and Data Engineering.
- Evidence timeline: case_{outcome}_timeline.csv. Same-step ordering is unknown.
- Root cause status: **Unverified**. Device compromise, customer authorisation and control execution are unavailable.
""")
    (out/"investigations.md").write_text("\n".join(sections))
    hourly=pd.read_csv(out/"hourly_monitoring.csv")
    # Counts remain counts. Do not multiply a rolling count by transaction volume.
    hourly=hourly.set_index("step").reindex(range(int(hourly.step.min()),int(hourly.step.max())+1),fill_value=0).rename_axis("step").reset_index()
    hourly["fraud_count_24h_average"]=hourly.confirmed_fraud.rolling(24,min_periods=1).mean()
    hourly.to_csv(out/"hourly_chart.csv",index=False)
    charts=[px.line(hourly,x="step",y=["alerts","confirmed_fraud","fraud_count_24h_average"],title="Alert workload and observed fraud"),
            px.bar(comparison,x="policy",y=["tp","fp","fn"],barmode="group",title="Policy outcomes on the same test period"),
            px.bar(comparison,x="policy",y="scenario_net_benefit",title="Scenario benefit after assumed action, review and friction costs"),
            px.line(pd.read_csv(out/"validation_thresholds.csv"),x="threshold",y="scenario_total_cost",color="model",title="Validation-only threshold selection")]
    parts=[]
    for i,chart in enumerate(charts):
        chart.update_layout(template="plotly_white",font_family="Arial",height=420,margin=dict(l=40,r=30,t=60,b=100))
        parts.append(chart.to_html(full_html=False,include_plotlyjs=True if i==0 else False))
    cards="".join(f'<div class="card"><small>{label}</small><strong>{value}</strong></div>' for label,value in [
        ("Alerts",f"{int(selected.alerts):,}"),("Precision",f"{selected.precision:.1%}"),("Recall",f"{selected.recall:.1%}"),("Missed value",fmt(selected.missed_fraud_value))])
    table=test.loc[test.outcome.isin(["FN","TP","FP"]),["row_id","step","type","amount","score","outcome","triggered_rules"]].sort_values("amount",ascending=False).head(40).to_html(index=False,escape=True,float_format=lambda x:f"{x:,.3f}")
    html=f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Payment Fraud Risk Observatory</title>
<style>body{{margin:0;background:#f3f6fa;color:#14263e;font:16px Arial}}main{{max-width:1200px;margin:auto;padding:36px 24px}}h1{{font-size:36px;margin:12px 0}}.tag{{color:#007c78;font-weight:bold;letter-spacing:2px}}.notice{{background:#fff2ce;border-left:4px solid #d79416;padding:16px;margin:24px 0}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}.card,section{{background:white;border:1px solid #dee5ee;border-radius:12px;padding:20px;margin:10px 0}}strong{{display:block;font-size:28px;margin-top:8px}}small{{color:#526780}}section{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:9px;border-bottom:1px solid #e5e9ed;text-align:left}}@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:27px}}}}</style></head><body><main>
<div class="tag">RISK & COMPLIANCE / OFFLINE ANALYTICS</div><h1>Payment Fraud Risk Observatory</h1><p>Detection quality, review capacity and business trade-offs.</p>
<div class="notice">{escape(mode)}. Synthetic evaluation, not production outcomes. Score is an uncalibrated ranking, not a verified fraud probability. Value is in dataset currency units.</div>
<div class="cards">{cards}</div><p>Locked model: {escape(manifest['selected_model'])}. Threshold selected on validation, then frozen for testing.</p>
{''.join('<section>'+x+'</section>' for x in parts)}<section><h2>Retrospective investigation sample</h2><p>Highest-value test examples; outcome labels are evaluation evidence.</p>{table}</section><p>Read stakeholder_brief.md and investigations.md for assumptions, decisions and case evidence.</p></main></body></html>"""
    (out/"dashboard.html").write_text(html)
