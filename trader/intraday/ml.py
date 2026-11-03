"""Local, versioned supervised models. Features lag; labels must mature before cutoff."""

import hashlib
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from threadpoolctl import threadpool_limits

ROOT = Path("runtime/intraday_models")


def features(df):
    p = df.close.shift(1)
    r = p.pct_change()
    x = pd.DataFrame(index=df.index)
    for n in (1, 4, 16, 48, 96):
        x[f"return_{n}"] = p.pct_change(n)
    for n in (16, 48, 96):
        x[f"volatility_{n}"] = r.rolling(n).std()
        x[f"deviation_{n}"] = p / p.rolling(n).mean() - 1
    x["range"] = (df.high.shift(1) - df.low.shift(1)) / p
    volume = df.volume.shift(1)
    x["relative_volume"] = volume / volume.rolling(48).mean() - 1
    x["hour_sin"] = np.sin(2 * np.pi * df.index.hour / 24)
    x["hour_cos"] = np.cos(2 * np.pi * df.index.hour / 24)
    return x.replace([np.inf, -np.inf], np.nan)


def train(symbol, interval, cutoff, family="boosted", horizon=16, root=ROOT):
    from .engine import load

    if family not in ("boosted", "forest") or horizon not in (8, 16):
        raise ValueError("Unsupported model family or horizon")
    df = load(symbol, interval)
    cutoff = pd.Timestamp(cutoff)
    cutoff = (
        cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    )
    # Exclude all later observations before generating any features/labels.
    df = df[df.index < cutoff]
    x = features(df)
    y = df.open.shift(-horizon) / df.open - 1
    maturity = df.index.to_series().shift(-horizon)
    valid = x.notna().all(axis=1) & y.notna() & (maturity < cutoff)
    x, y = x.loc[valid], y.loc[valid]
    if len(x) < 1000:
        raise ValueError("Need at least 1000 matured training examples")
    signature = hashlib.sha256(
        pd.concat([x, y.rename("label")], axis=1).to_csv().encode()
    ).hexdigest()
    metadata = {
        "symbol": symbol,
        "interval": interval,
        "cutoff": cutoff.isoformat(),
        "family": family,
        "horizon": horizon,
        "rows": len(x),
        "first": str(x.index[0]),
        "last_feature": str(x.index[-1]),
        "last_label_maturity": str(maturity.loc[x.index[-1]]),
        "data_hash": signature,
        "features": list(x.columns),
        "seed": 17,
        "status": "research only; no live qualification",
    }
    model_id = hashlib.sha256(
        json.dumps(metadata, sort_keys=True).encode()
    ).hexdigest()[:24]
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (model_id + ".joblib")
    if not path.exists():
        model = (
            HistGradientBoostingRegressor(
                max_iter=120,
                max_leaf_nodes=15,
                learning_rate=0.05,
                l2_regularization=10,
                min_samples_leaf=100,
                early_stopping=False,
                random_state=17,
            )
            if family == "boosted"
            else RandomForestRegressor(
                n_estimators=64,
                max_depth=6,
                min_samples_leaf=100,
                max_features=0.8,
                n_jobs=1,
                random_state=17,
            )
        )
        with threadpool_limits(limits=1):
            model.fit(x, y)
        temporary = path.with_suffix(".tmp")
        joblib.dump(model, temporary, compress=3)
        temporary.replace(path)
        metadata["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    return {"id": model_id, **json.loads(path.with_suffix(".json").read_text())}


def prediction(df, model_id, symbol, interval, root=ROOT):
    if not re.fullmatch("[0-9a-f]{24}", model_id or ""):
        raise ValueError("Invalid model version")
    path = Path(root) / (model_id + ".joblib")
    meta = json.loads(path.with_suffix(".json").read_text())
    if meta["symbol"] != symbol or meta["interval"] != interval:
        raise ValueError("Model instrument/interval mismatch")
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta["artifact_sha256"]:
        raise ValueError("Model artifact integrity failure")
    # Only locally generated, hash-verified artifacts are accepted. No upload endpoint.
    model = joblib.load(path)
    x = features(df)
    valid = x.notna().all(axis=1) & (x.index >= pd.Timestamp(meta["cutoff"]))
    result = pd.Series(np.nan, index=df.index)
    if valid.any():
        with threadpool_limits(limits=1):
            result.loc[valid] = model.predict(x.loc[valid])
    return result, meta


def targets(df, c):
    predicted, meta = prediction(df, c.model_id, c.symbol, c.interval)
    cost = 2 * (c.fee_bps + c.friction_bps) / 10000 + c.ml_buffer
    active = False
    remaining = 0
    cooldown = 0
    out = []
    for value in predicted:
        if cooldown:
            cooldown -= 1
        if active:
            remaining -= 1
            if remaining <= 0 or not np.isfinite(value) or value < 0:
                active = False
                cooldown = meta["horizon"] // 2
        elif cooldown == 0 and np.isfinite(value) and value > cost:
            active = True
            remaining = meta["horizon"]
        out.append(active)
    return pd.Series(out, index=df.index)
