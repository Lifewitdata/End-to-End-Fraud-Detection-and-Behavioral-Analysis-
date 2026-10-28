# Operating and reviewing the project

1. Install the package, acquire the source CSV and run the pipeline from the root.
2. Review `data_quality.csv` and `manifest.json`: input SHA-256, package versions,
   split boundaries, features, fit sample size, selected threshold and assumptions.
3. Reconcile `hourly_monitoring.csv` and SQL rule performance with policy counts.
4. Open `dashboard.html` locally or start the Streamlit app. Review workload,
   capacity alerts, false positives, value missed and population drift together.
5. Assign `alert_queue.csv` to a case-management system only after an authorised
   governance review. Generated cases remain Unreviewed. No actual block occurs.
6. Risk approves candidate rules; Product assesses customer impact; Engineering
   validates event timing and refresh reliability; Compliance reviews permitted
   use, retention and escalation requirements for the specific organisation.
7. Log any proposed change with rule/model version, owner, rationale, validation
   period, comparison, approval and rollback trigger. Use a new evaluation window
   after inspecting test results; do not repeatedly tune against the old test set.

CI rebuilds the integration fixture and checks correctness on pushes and pull
requests. It does not pretend to monitor a live bank or rerun the missing PaySim
CSV. For repeated source-data runs, invoke the CLI in the organisation's scheduler
with a new output directory per snapshot and retain its manifest. Label quality,
coverage and maturity must be checked before comparing weekly results.

This repository does not establish regulatory compliance. Retention rules,
privacy obligations, reporting deadlines and customer restrictions depend on
entity, product and jurisdiction. Keep that policy review separate from the
technical model evaluation and document its decision before any deployment.
