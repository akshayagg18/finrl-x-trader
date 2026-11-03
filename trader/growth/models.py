"""Hourly, net-return labels with chronological residual calibration."""

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from threadpoolctl import threadpool_limits

from trader.intraday.engine import load
from trader.intraday.ml import features

ROOT = Path("runtime/growth_models")
SYMBOLS = ("BTC-USDT", "ETH-USDT")


def hourly(symbol):
    d = load(symbol, 15)
    counts = d.close.resample("1h").count()
    h = d.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    if (counts != 4).any():
        raise ValueError("Incomplete hourly source data")
    return h


def fit(df, symbol, cutoff, family, horizon, cost, seed=17):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    before = df[df.index < cutoff]
    x = features(before)
    y = before.open.shift(-horizon) / before.open - 1 - cost
    maturity = before.index.to_series().shift(-horizon)
    start = cutoff - pd.DateOffset(months=9)
    valid = x.notna().all(axis=1) & y.notna() & (maturity < cutoff) & (x.index >= start)
    x, y = x.loc[valid], y.loc[valid]
    if len(x) < 1000:
        raise ValueError("Insufficient matured nine-month training data")
    model = (
        HistGradientBoostingRegressor(
            max_iter=80,
            max_leaf_nodes=10,
            min_samples_leaf=80,
            l2_regularization=10,
            early_stopping=False,
            random_state=seed,
        )
        if family == "boosted"
        else RandomForestRegressor(
            n_estimators=40,
            max_depth=5,
            min_samples_leaf=80,
            n_jobs=1,
            random_state=seed,
        )
    )
    with threadpool_limits(limits=1):
        model.fit(x, y)
    return model, {
        "symbol": symbol,
        "cutoff": str(cutoff),
        "training_start": str(start),
        "family": family,
        "horizon": horizon,
        "rows": len(x),
        "last_maturity": str(maturity.loc[x.index[-1]]),
        "net_label_cost": cost,
        "data_hash": hashlib.sha256(before.to_csv().encode()).hexdigest(),
    }


def predict(model, df):
    x = features(df)
    valid = x.notna().all(axis=1)
    p = pd.Series(np.nan, index=df.index)
    with threadpool_limits(limits=1):
        if valid.any():
            p.loc[valid] = model.predict(x.loc[valid])
    return p


def save(model, meta):
    ROOT.mkdir(parents=True, exist_ok=True)
    mid = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:24]
    p = ROOT / (mid + ".joblib")
    joblib.dump(model, p, compress=3)
    meta = {
        **meta,
        "id": mid,
        "artifact_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    p.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    return meta


def restore(mid):
    import re

    if not re.fullmatch("[0-9a-f]{24}", mid):
        raise ValueError("Invalid model id")
    p = ROOT / (mid + ".joblib")
    m = json.loads(p.with_suffix(".json").read_text())
    if hashlib.sha256(p.read_bytes()).hexdigest() != m["artifact_sha256"]:
        raise ValueError("Artifact mismatch")
    return joblib.load(p), m
