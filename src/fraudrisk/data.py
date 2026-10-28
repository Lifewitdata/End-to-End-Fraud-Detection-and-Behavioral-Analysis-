"""Strict schema checks and an explicitly separate synthetic integration fixture."""
from pathlib import Path
import numpy as np
import pandas as pd

TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
REQUIRED = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud"]

def validate(df):
    missing = sorted(set(REQUIRED) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    d = df[REQUIRED].copy()
    for c in ["step", "amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest",
              "newbalanceDest", "isFraud", "isFlaggedFraud"]:
        d[c] = pd.to_numeric(d[c], errors="raise")
    checks = {"missing_cells": int(d.isna().sum().sum()),
              "unknown_types": int((~d.type.isin(TYPES)).sum()),
              "negative_amounts": int((d.amount < 0).sum()),
              "invalid_steps": int(((d.step < 1) | (d.step % 1 != 0)).sum()),
              "invalid_labels": int((~d.isFraud.isin([0, 1])).sum()),
              "invalid_existing_flags": int((~d.isFlaggedFraud.isin([0, 1])).sum()),
              "empty_account_ids": int(d[["nameOrig", "nameDest"]].apply(lambda x: x.astype(str).str.strip().eq("")).sum().sum()),
              "nonfinite_numeric": int((~np.isfinite(d.select_dtypes("number"))).sum().sum())}
    if any(checks.values()):
        raise ValueError(f"Data validation failed: {checks}")
    checks["duplicate_rows_preserved"] = int(d.duplicated().sum())
    # No immutable transaction ID exists in PaySim. Identical rows are not proof
    # of ingestion duplication; preserve them and report for review.
    checks["zero_amounts_retained"] = int(d.amount.eq(0).sum())
    checks["rows"] = len(d)
    d["step"] = d.step.astype("int64")
    d["row_id"] = np.arange(len(d))
    return d, checks

def make_demo(path, seed=42, rows=24000):
    """Overlapping labelled fixture; NOT a PaySim sample or performance benchmark."""
    rng = np.random.default_rng(seed)
    step = rng.integers(1, 241, rows)
    typ = rng.choice(sorted(TYPES), rows, p=[.2, .25, .05, .3, .2])
    amount = np.round(rng.lognormal(9.0, 1.5, rows), 2)
    risk = .008 + .04 * np.isin(typ, ["TRANSFER", "CASH_OUT"]) + .04 * (amount > 100000)
    fraud = rng.binomial(1, risk)
    old = rng.lognormal(10, 1.8, rows)
    dest = rng.lognormal(10, 1.8, rows)
    data = pd.DataFrame(dict(step=step, type=typ, amount=amount,
        nameOrig=[f"C{x}" for x in rng.integers(0, 1800, rows)],
        oldbalanceOrg=old, newbalanceOrig=np.maximum(0, old-amount),
        nameDest=[f"C{x}" for x in rng.integers(2000, 2400, rows)],
        oldbalanceDest=dest, newbalanceDest=dest+amount,
        isFraud=fraud, isFlaggedFraud=((typ=="TRANSFER") & (amount>200000)).astype(int)))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False)
    return data
