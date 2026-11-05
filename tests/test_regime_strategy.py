import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.db import dumps
from trader.growth.portfolio import execute
from trader.growth.regime import (
    SPECS,
    decision_schedule,
    decision_schedule_between,
    fit_filter,
    load_long_history,
    regime_features,
    rule_signal,
)


def test_long_history_integrity_and_missing_hours_are_explicit():
    for symbol in ("BTC-USDT", "ETH-USDT"):
        data = load_long_history(symbol)
        manifest = json.loads(
            (
                Path("research/strategy_v2/data")
                / (symbol.replace("-", "") + "_1h.json")
            ).read_text()
        )
        assert len(data) > 80_000
        assert int(data.isna().any(axis=1).sum()) == manifest["missing_hours"]
        assert data.index.freq == pd.tseries.frequencies.to_offset("1h")


def test_regime_features_do_not_change_from_future_prices():
    data = load_long_history("BTC-USDT")
    spec = SPECS[-1]
    expected = regime_features(data, spec)
    changed = data.copy()
    changed.loc["2024-01-01":, ["open", "high", "low", "close", "volume"]] *= 3
    actual = regime_features(changed, spec)
    pd.testing.assert_frame_equal(
        expected.loc[:"2023-12-31 23:00:00+00:00"],
        actual.loc[:"2023-12-31 23:00:00+00:00"],
    )


def test_incomplete_day_does_not_become_completed_daily_feature():
    data = load_long_history("BTC-USDT")
    gap = data.index[data.close.isna()][0]
    spec = SPECS[0]
    features = regime_features(data, spec)
    next_day = gap.normalize() + timedelta(days=1)
    # The incomplete day's close is shifted into the next day as NaN.
    assert (
        features.loc[next_day, "daily_close"] != features.loc[next_day, "daily_close"]
    )
    assert not rule_signal(features, spec).loc[next_day]


def test_filter_labels_mature_before_cutoff():
    data = load_long_history("BTC-USDT")
    _, metadata = fit_filter(
        data,
        "BTC-USDT",
        SPECS[0],
        "2022-01-01",
        "boosted",
        0.003,
    )
    assert pd.Timestamp(metadata["last_label_maturity"]) < pd.Timestamp(
        metadata["cutoff"]
    )
    assert metadata["rows"] >= 500


def test_ml_filter_controls_entries_but_base_regime_controls_exit():
    data = load_long_history("BTC-USDT").loc["2023-01-01":"2023-01-10"]
    spec = SPECS[0]
    features = regime_features(load_long_history("BTC-USDT"), spec).loc[data.index]
    base = rule_signal(features, spec)
    probability = pd.Series(0.0, index=data.index)
    decisions = decision_schedule(
        load_long_history("BTC-USDT"),
        spec,
        probability.reindex(load_long_history("BTC-USDT").index),
        0.55,
    )
    for timestamp, active in base.items():
        item = decisions[timestamp.value]
        if active:
            assert not item["enter"]
            assert not item["liquidate"]
        else:
            assert item["liquidate"]


def test_annual_model_interval_keeps_prior_feature_history():
    data = load_long_history("BTC-USDT")
    spec = SPECS[0]
    probability = pd.Series(1.0, index=data.index)
    complete = decision_schedule(data, spec, probability, 0.55)
    interval = decision_schedule_between(
        data, spec, "2024-01-01", "2025-01-01", probability, 0.55
    )
    expected_index = data.index[
        (data.index >= pd.Timestamp("2024-01-01", tz="UTC"))
        & (data.index < pd.Timestamp("2025-01-01", tz="UTC"))
    ]
    assert interval
    assert interval == {timestamp.value: complete[timestamp.value] for timestamp in expected_index}
    # A sliced year has no 100-day/365-day history at the boundary. The helper
    # must retain prior years before selecting this interval.
    sliced = decision_schedule(data.loc[expected_index], spec, probability, 0.55)
    assert interval[expected_index[0].value] != sliced[expected_index[0].value]


def test_protective_stop_requires_regime_reset_before_reentry():
    dates = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    data = {
        "BTC-USDT": pd.DataFrame({"open": [100, 90, 95, 98, 99, 100]}, index=dates),
        "ETH-USDT": pd.DataFrame({"open": [100, 90, 95, 98, 99, 100]}, index=dates),
    }
    decisions = {
        timestamp.value: {
            symbol: {
                "enter": True,
                "liquidate": False,
                "horizon": 100,
                "stop": 0.01,
            }
            for symbol in data
        }
        for timestamp in dates
    }
    result = execute(
        data,
        decisions,
        {"fee_bps": 0, "friction_bps": 0, "reserve": 0.4},
    )
    # Two entry fills and two stop exits. Continued enter=True does not churn
    # back into the same regime after the protective stop.
    assert [fill["side"] for fill in result["fills"]] == [
        "BUY",
        "BUY",
        "SELL",
        "SELL",
    ]
    assert result["positions"] == {"BTC-USDT": 0.0, "ETH-USDT": 0.0}


def test_rule_signal_is_boolean_and_nonleveraged_decisions():
    data = load_long_history("ETH-USDT")
    spec = SPECS[0]
    signal = rule_signal(regime_features(data, spec), spec)
    assert signal.dtype == bool
    assert np.isfinite(signal.astype(float)).all()
    assert set(decision_schedule(data.iloc[-100:], spec)[data.index[-1].value]) >= {
        "enter",
        "liquidate",
        "stop",
    }


def test_locked_protocol_and_failed_qualification_are_explicit():
    root = Path("research/strategy_v2")
    protocol = json.loads((root / "protocol.json").read_text())
    lock = json.loads((root / "selection_locked.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    serialized = dumps(protocol)
    assert hashlib.sha256(serialized.encode()).hexdigest() == lock["protocol_sha256"]
    assert pd.to_datetime(protocol["validation"][1], utc=True) < pd.to_datetime(
        protocol["evaluation"][0], utc=True
    )
    assert not lock["rule_passed_selection"]
    assert not lock["filter_passed_selection"]
    for name in ("rule_base", "ml_filter_base"):
        assert not summary[name]["qualified"]
        assert not summary[name]["live_qualified"]
