"""Strict schema checks and an explicitly separate synthetic integration fixture."""
from pathlib import Path
import numpy as np
import pandas as pd

TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
REQUIRED = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud"]

class DataValidationError(ValueError):
    """Counts and zero-based input positions, never raw account or cell values."""
    def __init__(self, checks, positions=None):
        self.checks=checks
        self.positions=positions or {}
        super().__init__(f"Data validation failed: {checks}")


def validate(df):
    missing=sorted(set(REQUIRED)-set(df.columns))
    if missing: raise DataValidationError({"missing_columns":missing})
    if df.empty: raise DataValidationError({"empty_dataset":1})
    d=df[REQUIRED].copy()
    numeric=[c for c in REQUIRED if c not in ["type","nameOrig","nameDest"]]
    invalid={};positions={}
    for c in numeric:
        converted=pd.to_numeric(d[c],errors="coerce")
        bad=converted.isna() & d[c].notna()
        if bad.any():
            invalid[c]=int(bad.sum());positions[c]=np.flatnonzero(bad)[:10].tolist()
        d[c]=converted
    if invalid: raise DataValidationError({"invalid_numeric_columns":invalid},positions)
    masks={
        "missing_rows":d.isna().any(axis=1),
        "unknown_types":~d.type.isin(TYPES),
        "negative_amounts":d.amount<0,
        "invalid_steps":(d.step<1)|(d.step%1!=0),
        "invalid_labels":~d.isFraud.isin([0,1]),
        "invalid_existing_flags":~d.isFlaggedFraud.isin([0,1]),
        "empty_account_ids":d.nameOrig.astype("string").str.strip().eq("")|d.nameDest.astype("string").str.strip().eq(""),
        "nonfinite_numeric_rows":(~np.isfinite(d[numeric])).any(axis=1),
    }
    checks={k:int(v.sum()) for k,v in masks.items()}
    checks["missing_cells"]=int(d.isna().sum().sum())
    if any(checks.values()):
        raise DataValidationError(checks,{k:np.flatnonzero(v.fillna(False))[:10].tolist() for k,v in masks.items() if v.any()})
    checks["duplicate_rows_preserved"]=int(d.duplicated().sum())
    checks["zero_amounts_retained"]=int(d.amount.eq(0).sum())
    checks["rows"]=len(d)
    d["step"]=d.step.astype("int64");d["row_id"]=np.arange(len(d))
    return d,checks

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
