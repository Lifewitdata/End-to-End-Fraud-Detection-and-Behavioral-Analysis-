# Evaluation protocol and known limitations

## Prediction time and temporal safety
The main model represents predecision triage using current transaction amount,
type and strictly prior-step history. Features are calculated in DuckDB. Events
within the same hour are excluded from one another's history, since their order
is unknown. The 24-hour window includes `step-24` through `step-1`. Previous
validation/test events may update history, as in an online replay; their labels
are never features. Raw IDs are used for history grouping, not model predictors.

The first 60% of distinct steps train models; the next 20% select model and
threshold; the final 20% evaluate the locked policy. No step spans splits. Median
imputation, scaling and categorical encoding fit on training only. The original
full-data 75th percentile feature is removed. No post-balance features or SMOTE
are used. Class-weighted logistic regression and random forest are compared.

Cold-start averages are missing and imputed using training medians. Ratios
default to one when no nonzero prior average exists; counts expose cold starts.
Recipient histories are useful; sender histories may be sparse in PaySim.

## Model and threshold selection
Candidates include uniform and validation-score-quantile thresholds and a
no-alert policy. Select minimum estimated scenario cost, subject to validation
peak alerts per hourly step. Select the model by the same validation objective.
The full test set is then evaluated once with frozen settings. Rule settings
are predeclared in configuration; the hybrid is a comparison, not automatically
chosen from test outcomes. A test capacity breach is explicitly reported.

Weighted model scores are **not calibrated probabilities**. `risk_score` is just
100 times the ranking score. If trustworthy probabilities are needed, reserve
another calibration period or use appropriate temporal cross-validation.

## Metrics
- Precision = TP / (TP+FP); recall = TP / (TP+FN).
- False-positive rate = FP / (FP+TN), distinct from the false share of alerts.
- Average precision summarises precision-recall ranking; it is not trapezoidal PR-AUC.
- Precision@100 uses the highest scores and stable input order to break ties.
- Value recall = detected labelled-fraud amount / total labelled-fraud amount.
- Zero-denominator count rates are reported as zero; inspect support counts.

## Business scenario
`scenario_total_cost = fraud_value - captured_value * action_success_fraction
+ alerts * review_cost_units + FP * false_alert_friction_units`.
Net benefit compares this scenario to no intervention. Action success, review
and friction costs are assumptions in dataset units, not measured savings.
Overlapping rules are evaluated individually, but union/hybrid policies deduplicate
each transaction. The sensitivity table changes action success on the fixed test
policy; it does not optimise test thresholds.

## Investigations and monitoring
Case studies cover a missed fraud, caught fraud and legitimate alert when those
outcomes exist. They include a timeline and observed signals, but mark root
causes unverified. Fraud labels alone cannot prove mule activity or compromise.
PSI compares validation/test populations with reference-defined bins. 0.10/0.20
are configurable-design review conventions, not regulatory standards. Labelled
KPIs assume complete outcomes; production reporting needs maturity windows and
explicit pending states. No case closing times are fabricated.

## Claims corrected from the original notebook
- The original output showed 49.8% unchanged destination balances, not ~99%.
- Original counts were 4,097 TRANSFER and 4,116 CASH_OUT fraud cases; TRANSFER was
  not 100% of fraud. Those are historical saved outputs, not rerun results.
- A zero observed fraud count in a simulator is not evidence that a payment type
  is safe in production. All types remain in the pipeline.
- The original rolling count was incorrectly multiplied by average transaction
  volume. The replacement fills hourly gaps and plots a rolling count average.
- The original test-tuned threshold and economic claims are withdrawn. Run the
  corrected pipeline on the source data to obtain new estimates.

## Source
[PaySim publisher and balance-field warning](https://www.kaggle.com/datasets/ealaxi/paysim1).
The full dataset could not be downloaded in the implementation environment
(publisher endpoint returned a permissions error). Committed validation evidence
therefore uses only the separately identified integration fixture.
