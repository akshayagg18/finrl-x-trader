"""Lagged multi-day trend/momentum/volatility regime and optional ML filter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from threadpoolctl import threadpool_limits

from .models import ROOT


@dataclass(frozen=True)
class RegimeSpec:
    fast_days: int
    slow_days: int
    momentum_hours: int
    momentum_threshold: float
    volatility_quantile: float

    @property
    def name(self) -> str:
        return (
            f"trend_{self.fast_days}_{self.slow_days}_mom_{self.momentum_hours}_"
            f"q{int(self.volatility_quantile * 100)}"
        )


SPECS = tuple(
    RegimeSpec(fast, slow, momentum, 0.0, quantile)
    for fast, slow in ((20, 100), (50, 200))
    for momentum in (24, 72)
    for quantile in (0.8, 0.9)
)
FILTER_FAMILIES = ("boosted", "forest")
FILTER_THRESHOLDS = (0.55, 0.60)
LABEL_HOURS = 24 * 7


def load_long_history(symbol: str) -> pd.DataFrame:
    if symbol not in ("BTC-USDT", "ETH-USDT"):
        raise ValueError("Unsupported regime instrument")
    code = symbol.replace("-", "")
    path = Path("research/strategy_v2/data") / f"{code}_1h.csv.gz"
    manifest_path = path.with_suffix("").with_suffix(".json")
    manifest = json.loads(manifest_path.read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["csv_gzip_sha256"]:
        raise ValueError("Long-history data integrity failure")
    frame = pd.read_csv(path, index_col="timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True, format="mixed")
    if (
        frame.empty
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError("Invalid long-history timestamps")
    # Keep missing vendor hours explicit so rolling features cannot silently
    # interpret a maintenance gap as a one-hour return.
    expected = pd.date_range(frame.index[0], frame.index[-1], freq="1h", tz="UTC")
    return frame.reindex(expected).rename_axis("timestamp")


def regime_features(frame: pd.DataFrame, spec: RegimeSpec) -> pd.DataFrame:
    """Features available at each hour; daily/4h bars are shifted before use."""

    daily_count = frame.close.resample("1D").count()
    daily_close = frame.close.resample("1D").last().where(daily_count == 24).shift(1)
    fast = daily_close.rolling(
        spec.fast_days, min_periods=max(2, int(spec.fast_days * 0.9))
    ).mean()
    slow = daily_close.rolling(
        spec.slow_days, min_periods=max(2, int(spec.slow_days * 0.9))
    ).mean()
    daily_returns = daily_close.pct_change(fill_method=None)
    volatility = daily_returns.rolling(30, min_periods=27).std() * np.sqrt(365)
    volatility_limit = volatility.rolling(365, min_periods=180).quantile(
        spec.volatility_quantile
    )
    four_hour_count = frame.close.resample("4h").count()
    four_hour_close = (
        frame.close.resample("4h").last().where(four_hour_count == 4).shift(1)
    )
    momentum = four_hour_close.pct_change(spec.momentum_hours // 4, fill_method=None)
    result = pd.DataFrame(index=frame.index)
    for name, series in {
        "daily_close": daily_close,
        "trend_fast_distance": daily_close / fast - 1,
        "trend_slow_distance": daily_close / slow - 1,
        "trend_spread": fast / slow - 1,
        "momentum_4h": momentum,
        "volatility_30d": volatility,
        "volatility_limit": volatility_limit,
    }.items():
        result[name] = series.reindex(frame.index, method="ffill")
    past = frame.close.shift(1)
    returns = past.pct_change(fill_method=None)
    for hours in (1, 4, 24, 72, 168):
        result[f"return_{hours}h"] = past.pct_change(hours, fill_method=None)
    for hours in (24, 72, 168):
        result[f"realized_vol_{hours}h"] = returns.rolling(hours).std() * np.sqrt(
            24 * 365
        )
    volume = frame.volume.shift(1)
    result["relative_volume_24h"] = volume / volume.rolling(24).mean() - 1
    result["hour_sin"] = np.sin(2 * np.pi * frame.index.hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * frame.index.hour / 24)
    return result.replace([np.inf, -np.inf], np.nan)


def rule_signal(features: pd.DataFrame, spec: RegimeSpec) -> pd.Series:
    return (
        (features.daily_close > 0)
        & (features.trend_fast_distance > 0)
        & (features.trend_slow_distance > 0)
        & (features.trend_spread > 0)
        & (features.momentum_4h > spec.momentum_threshold)
        & (features.volatility_30d <= features.volatility_limit)
    ).fillna(False)


def decision_schedule(
    frame: pd.DataFrame,
    spec: RegimeSpec,
    probability: pd.Series | None = None,
    threshold: float | None = None,
) -> dict[int, dict]:
    features = regime_features(frame, spec)
    signal = rule_signal(features, spec)
    daily_vol = features.volatility_30d / np.sqrt(365)
    result: dict[int, dict] = {}
    for timestamp in frame.index:
        active = bool(signal.loc[timestamp])
        allowed = active
        if probability is not None:
            value = probability.get(timestamp, np.nan)
            allowed = active and np.isfinite(value) and value >= float(threshold)
        stop = float(np.clip(2 * daily_vol.loc[timestamp], 0.01, 0.15))
        result[timestamp.value] = {
            "enter": bool(allowed),
            "liquidate": not active,
            "horizon": 24 * 365 * 20,
            "stop": stop if np.isfinite(stop) else 0.03,
            "source": "ml_filter" if probability is not None else "rule",
        }
    return result


def decision_schedule_between(
    frame: pd.DataFrame,
    spec: RegimeSpec,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    probability: pd.Series | None = None,
    threshold: float | None = None,
) -> dict[int, dict]:
    """Build with full prior history, then select the half-open decision interval."""

    start = pd.to_datetime(start, utc=True)
    end = pd.to_datetime(end, utc=True)
    schedule = decision_schedule(frame, spec, probability, threshold)
    index = frame.index[(frame.index >= start) & (frame.index < end)]
    return {timestamp.value: schedule[timestamp.value] for timestamp in index}


def fit_filter(
    frame: pd.DataFrame,
    symbol: str,
    spec: RegimeSpec,
    cutoff: str | pd.Timestamp,
    family: str,
    round_trip_cost: float,
    years: int = 3,
    seed: int = 17,
) -> tuple[object, dict]:
    if family not in FILTER_FAMILIES:
        raise ValueError("Unsupported filter family")
    cutoff = pd.Timestamp(cutoff)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff
    features = regime_features(frame, spec)
    future_net = frame.open.shift(-LABEL_HOURS) / frame.open - 1 - round_trip_cost
    maturity = frame.index.to_series().shift(-LABEL_HOURS)
    signal = rule_signal(features, spec)
    start = cutoff - pd.DateOffset(years=years)
    valid = (
        features.notna().all(axis=1)
        & future_net.notna()
        & (maturity < cutoff)
        & (features.index >= start)
        & (features.index < cutoff)
        & signal
    )
    x = features.loc[valid]
    y = (future_net.loc[valid] > 0).astype(int)
    if len(x) < 500 or y.nunique() < 2:
        raise ValueError("Insufficient matured regime-filter examples")
    model = (
        HistGradientBoostingClassifier(
            max_iter=100,
            max_leaf_nodes=10,
            min_samples_leaf=50,
            l2_regularization=10,
            early_stopping=False,
            random_state=seed,
        )
        if family == "boosted"
        else RandomForestClassifier(
            n_estimators=64,
            max_depth=6,
            min_samples_leaf=50,
            class_weight="balanced",
            n_jobs=1,
            random_state=seed,
        )
    )
    with threadpool_limits(limits=1):
        model.fit(x, y)
    metadata = {
        "symbol": symbol,
        "cutoff": cutoff.isoformat(),
        "training_start": start.isoformat(),
        "family": family,
        "label_hours": LABEL_HOURS,
        "round_trip_cost": round_trip_cost,
        "rows": len(x),
        "positive_fraction": float(y.mean()),
        "last_feature": x.index[-1].isoformat(),
        "last_label_maturity": maturity.loc[x.index[-1]].isoformat(),
        "features": list(x.columns),
        "regime_spec": asdict(spec),
        "data_hash": hashlib.sha256(
            pd.concat([x, y.rename("label")], axis=1).to_csv().encode()
        ).hexdigest(),
        "seed": seed,
        "status": "research filter; qualification pending",
    }
    return model, metadata


def filter_probability(
    model: object, frame: pd.DataFrame, spec: RegimeSpec
) -> pd.Series:
    features = regime_features(frame, spec)
    valid = features.notna().all(axis=1)
    result = pd.Series(np.nan, index=frame.index)
    with threadpool_limits(limits=1):
        if valid.any():
            result.loc[valid] = model.predict_proba(features.loc[valid])[:, 1]
    return result


def save_filter(model: object, metadata: dict) -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    model_id = hashlib.sha256(
        json.dumps(metadata, sort_keys=True).encode()
    ).hexdigest()[:24]
    path = ROOT / f"{model_id}.joblib"
    joblib.dump(model, path, compress=3)
    manifest = {
        **metadata,
        "id": model_id,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
