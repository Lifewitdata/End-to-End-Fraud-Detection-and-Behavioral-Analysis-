"""Time splits, predecision models, locked validation selection and explicit costs."""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC = ["log_amount", "sender_count_24h", "sender_mean_24h", "recipient_count_24h",
           "recipient_senders_24h", "recipient_mean_24h", "sender_amount_ratio", "recipient_amount_ratio"]
FEATURES = NUMERIC + ["type"]

def time_split(df, cfg):
    steps = np.sort(df.step.unique())
    if len(steps) < 10:
        raise ValueError("At least 10 distinct hourly steps are required")
    a = int(len(steps)*cfg["train_fraction"])
    b = int(len(steps)*(cfg["train_fraction"]+cfg["validation_fraction"]))
    parts = [df[df.step.isin(s)].copy() for s in [steps[:a], steps[a:b], steps[b:]]]
    for name, part in zip(["train", "validation", "test"], parts):
        if part.isFraud.nunique() != 2:
            raise ValueError(f"{name} must contain both classes; use a broader time range")
    return parts

def fit_models(train, cfg):
    sample = train
    if len(train) > cfg["max_train_rows"]:
        sample, _ = train_test_split(train, train_size=cfg["max_train_rows"],
                                    stratify=train.isFraud, random_state=cfg["seed"])
    # Median, scaling and category vocabulary are learned only inside training.
    def prep():
        return ColumnTransformer([
            ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")),
                                   ("scale", StandardScaler())]), NUMERIC),
            ("type", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["type"])])
    estimators = {
        "logistic_regression": LogisticRegression(class_weight="balanced", max_iter=1000, random_state=cfg["seed"]),
        "random_forest": RandomForestClassifier(n_estimators=80, max_depth=12,
            min_samples_leaf=10, class_weight="balanced_subsample", n_jobs=2, random_state=cfg["seed"])}
    models = {}
    for name, est in estimators.items():
        model = Pipeline([("prepare", prep()), ("model", est)])
        model.fit(sample[FEATURES], sample.isFraud)
        models[name] = model
    return models, len(sample)

def metrics(df, prediction, cfg):
    y = df.isFraud.to_numpy().astype(bool)
    p = np.asarray(prediction).astype(bool)
    amount = df.amount.to_numpy()
    tp, fp, fn, tn = [int(v.sum()) for v in [y&p, ~y&p, y&~p, ~y&~p]]
    div = lambda a, b: float(a/b) if b else 0.0
    captured, missed = float(amount[y&p].sum()), float(amount[y&~p].sum())
    workload = pd.Series(p.astype(int), index=df.step).groupby(level=0).sum()
    review = float(p.sum()*cfg["review_cost_units"])
    friction = float(fp*cfg["false_alert_friction_units"])
    benefit = captured*cfg["action_success_fraction"]
    return dict(rows=len(df), tp=tp, fp=fp, fn=fn, tn=tn, alerts=int(p.sum()),
        precision=div(tp, tp+fp), recall=div(tp, tp+fn), f1=div(2*tp, 2*tp+fp+fn),
        false_positive_rate=div(fp, fp+tn), alert_rate=float(p.mean()),
        fraud_value=float(amount[y].sum()), captured_fraud_value=captured,
        missed_fraud_value=missed, value_recall=div(captured, captured+missed),
        alerts_per_step=float(workload.mean()), peak_alerts_per_step=int(workload.max()),
        review_cost=review, false_alert_friction=friction, assumed_prevented_value=benefit,
        scenario_total_cost=captured+missed-benefit+review+friction,
        scenario_net_benefit=benefit-review-friction,
        capacity_feasible=bool(workload.max()<=cfg["review_capacity_per_step"]))

def select_threshold(df, scores, cfg):
    # Includes no-alert policy. Only validation labels enter threshold selection.
    thresholds = np.unique(np.r_[np.linspace(0, 1, 41), np.quantile(scores, np.linspace(0, 1, 41)), 1.000001])
    table = pd.DataFrame([dict(threshold=float(t), **metrics(df, scores>=t, cfg)) for t in thresholds])
    feasible = table[table.capacity_feasible]
    best = feasible.sort_values(["scenario_total_cost", "alerts", "threshold"], ascending=[True, True, False]).iloc[0]
    return float(best.threshold), table

def ranking_metrics(df, scores, k=100):
    y = df.isFraud.to_numpy()
    top = np.argsort(-np.asarray(scores), kind="stable")[:min(k, len(df))]
    return dict(average_precision=float(average_precision_score(y, scores)),
                roc_auc=float(roc_auc_score(y, scores)), precision_at_100=float(y[top].mean()))

def rule_flags(df, cfg):
    risky = df.type.isin(["TRANSFER", "CASH_OUT"])
    return {
        "R01_existing_flag": df.isFlaggedFraud.eq(1).to_numpy(),
        "R02_large_transfer_cashout": (risky & (df.amount>cfg["amount_rule_threshold"])).to_numpy(),
        "R03_recipient_burst": ((df.recipient_count_24h>=cfg["recipient_velocity_threshold"]) &
                                 (df.recipient_amount_ratio>=cfg["relative_amount_threshold"])).to_numpy(),
        "R04_sender_deviation": (risky & (df.sender_count_24h>=3) &
                                 (df.sender_amount_ratio>=cfg["relative_amount_threshold"])).to_numpy()}

def psi(reference, current):
    """Unlabelled population drift; quantile bins fixed on reference."""
    r, c = np.asarray(reference), np.asarray(current)
    edges = np.unique(np.quantile(r[np.isfinite(r)], np.linspace(0, 1, 11)))
    if len(edges)<2:
        edges = np.array([-np.inf, float(edges[0]), np.inf])
    else:
        edges[0], edges[-1] = -np.inf, np.inf
    a, b = np.histogram(r, edges)[0], np.histogram(c, edges)[0]
    a = np.maximum(a/max(a.sum(), 1), 1e-6)
    b = np.maximum(b/max(b.sum(), 1), 1e-6)
    return float(np.sum((b-a)*np.log(b/a)))
