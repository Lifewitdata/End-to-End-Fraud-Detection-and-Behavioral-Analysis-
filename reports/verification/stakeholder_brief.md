# Payment Fraud Risk — Decision Brief

**Run basis: INTEGRATION FIXTURE — NOT PAYSIM RESULTS.** All values are in dataset currency units. No real-world savings claim.

## Decision
Do not pilot the locked policy: its test-period peak workload breaches configured capacity. Use a new validation period for any revision.
Evaluate the locked logistic_regression triage policy against the existing flag.
The model and threshold (0.232788) were selected using validation-period scenario cost,
subject to peak hourly alert capacity. Test results were evaluated afterward.

## Test evidence
| Measure | Selected model | Existing flag |
|---|---:|---:|
| Alerts | 3,497 | 14 |
| Precision | 3.75% | 7.14% |
| Recall | 90.34% | 0.69% |
| Fraud value captured for review | 4,965,435.82 | 241,137.86 |
| Fraud value missed | 319,879.66 | 5,044,177.62 |
| Peak alerts / hourly step | 103 | 1 |
| Scenario net benefit | 2,458,500.91 | 120,472.93 |

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
- Action effectiveness (50%), review cost and friction are configurable assumptions.
  See cost_sensitivity.csv. A lower-cost policy can still miss valuable cases.
- This is a synthetic-data evaluation; labels are treated as complete. Real labels are delayed and incomplete.
- No real timestamps, devices, locations, logins or investigation closure events are available.
  No actual investigation duration, account takeover cause or regulatory compliance is claimed.
- Step is an hourly simulation index. No calendar dates or within-step event order are invented.
- Confirmed counts and drift require review; no emails, blocks or filings are sent by this project.
