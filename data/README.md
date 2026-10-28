# Dataset contract and acquisition

The original `PS_log.csv` is not committed. Obtain PaySim from its publisher:
[Synthetic Financial Datasets for Fraud Detection](https://www.kaggle.com/datasets/ealaxi/paysim1).
Observe the publisher's licence and terms. With authorised Kaggle access:

```bash
kaggle datasets download -d ealaxi/paysim1 -p data --unzip
python -m fraudrisk.pipeline --input data/PS_20174392719_1491204439457_log.csv
```

The filename may differ; `--input` accepts the actual local CSV path. Do not commit
Kaggle credentials, CSVs, model binaries or the analytical database.

Required fields: `step`, `type`, `amount`, `nameOrig`, `oldbalanceOrg`,
`newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`, `isFraud`,
`isFlaggedFraud`. `step` is a simulation-hour index, not a timestamp or reliable
hour of day. Currency is not inferred or converted to USD/INR.

The publisher cautions against using balance fields for detection because
detected fraud is cancelled. Consequently **all four balance fields are excluded
from modelling**, even though old balances might be available in a real system.
They are used only for clearly labelled retrospective descriptions.

`isFraud` is evaluation ground truth; `isFlaggedFraud` is an existing-control
benchmark. Neither is a model feature. Duplicate rows are reported and preserved:
there is no immutable event ID to prove that identical records are duplicates.
`row_id` is an ingestion reference, not an invented bank transaction identifier.

The `--demo` option generates a seeded 24,000-row integration fixture with the
same schema. **It is not PaySim, a PaySim sample or evidence of achievable fraud
detection performance.** Its manifest and reports retain this label.

The full PaySim data has millions of rows. Use adequate memory (an 8 GB+ machine
is a practical starting point; actual usage depends on versions and data).
Models fit at most 150,000 stratified training-period rows, configurable in
`config/analysis.json`. All validation and test rows are evaluated. SQL feature
construction uses the full available history and excludes the current step.
