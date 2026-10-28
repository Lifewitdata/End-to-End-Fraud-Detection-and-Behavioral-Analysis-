# Retrospective investigation examples

Run: **INTEGRATION FIXTURE — NOT PAYSIM RESULTS**. Hypotheses require verification; labels do not establish root cause.

## Missed fraud: row 23044
- Evidence: step 235, DEBIT, amount 111,819.69; sender C654; recipient C2037.
- Decision: BELOW_THRESHOLD; score 0.182157; outcome FN.
- Prior 24-hour recipient activity: 5 transactions from 5 senders.
- Existing/rule evidence: No configured rule triggered.
- Working hypothesis: The locked policy did not rank this labelled case above its operating threshold.
- Proposed response: Investigate historical recipient patterns and test a candidate control on a new validation period.
- Owner: Payments Risk, supported by Product and Data Engineering.
- Evidence timeline: case_FN_timeline.csv. Same-step ordering is unknown.
- Root cause status: **Unverified**. Device compromise, customer authorisation and control execution are unavailable.

## Detected fraud: row 19032
- Evidence: step 198, TRANSFER, amount 241,137.86; sender C304; recipient C2221.
- Decision: MODEL_THRESHOLD; score 0.738197; outcome TP.
- Prior 24-hour recipient activity: 5 transactions from 5 senders.
- Existing/rule evidence: R01_existing_flag;R02_large_transfer_cashout.
- Working hypothesis: The available signals met the review threshold; this does not prove an account was compromised.
- Proposed response: Review sender/recipient history and request additional evidence before any hold.
- Owner: Payments Risk, supported by Product and Data Engineering.
- Evidence timeline: case_TP_timeline.csv. Same-step ordering is unknown.
- Root cause status: **Unverified**. Device compromise, customer authorisation and control execution are unavailable.

## Legitimate alert: row 9164
- Evidence: step 228, CASH_IN, amount 2,680,224.03; sender C123; recipient C2383.
- Decision: MODEL_THRESHOLD; score 0.424055; outcome FP.
- Prior 24-hour recipient activity: 4 transactions from 4 senders.
- Existing/rule evidence: No configured rule triggered.
- Working hypothesis: Legitimate activity overlapped the model risk pattern, creating avoidable review workload.
- Proposed response: Review the reason and transaction context; test segment-aware refinements before changing the threshold.
- Owner: Payments Risk, supported by Product and Data Engineering.
- Evidence timeline: case_FP_timeline.csv. Same-step ordering is unknown.
- Root cause status: **Unverified**. Device compromise, customer authorisation and control execution are unavailable.
