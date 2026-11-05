import hashlib
import json
from pathlib import Path

import pandas as pd

from trader.db import dumps
from trader.growth.defensive import (
    DefensiveRisk,
    DefensiveSpec,
    defensive_features,
    rebalance_due,
    simulate,
    target_weights,
)
from trader.growth.regime import load_long_history

SELECTED = DefensiveSpec(100, 90, "weekly", "btc_gate")


def test_defensive_features_do_not_change_from_future_prices():
    data = load_long_history("BTC-USDT")
    daily = pd.DataFrame(
        {
            "open": data.open.resample("1D").first(),
            "close": data.close.resample("1D").last(),
        }
    )
    expected = defensive_features(daily, SELECTED)
    changed = daily.copy()
    changed.loc["2024-01-01":, ["open", "close"]] *= 3
    actual = defensive_features(changed, SELECTED)
    pd.testing.assert_frame_equal(
        expected.loc[:"2023-12-31"], actual.loc[:"2023-12-31"]
    )


def test_rebalance_calendar_is_stable_and_not_split_anchored():
    monday = pd.Timestamp("2026-11-02", tz="UTC")
    assert rebalance_due(monday, "weekly")
    assert not rebalance_due(monday + pd.Timedelta(days=1), "weekly")
    assert not rebalance_due(pd.Timestamp("2026-11-02", tz="UTC"), "biweekly")
    assert rebalance_due(pd.Timestamp("2026-11-09", tz="UTC"), "biweekly")
    assert rebalance_due(pd.Timestamp("2026-06-01", tz="UTC"), "monthly")


def test_weights_respect_caps_and_btc_gate():
    timestamp = pd.Timestamp("2026-11-02", tz="UTC")
    features = {
        "BTC-USDT": pd.DataFrame(
            {"trend": [0.1], "momentum": [0.1], "volatility": [0.15]},
            index=[timestamp],
        ),
        "ETH-USDT": pd.DataFrame(
            {"trend": [-0.1], "momentum": [-0.1], "volatility": [0.60]},
            index=[timestamp],
        ),
    }
    weights = target_weights(timestamp, features, SELECTED)
    assert weights == {"BTC-USDT": 0.1, "ETH-USDT": 0.05}
    assert sum(weights.values()) <= 0.2
    features["BTC-USDT"].loc[timestamp, "momentum"] = -0.1
    assert target_weights(timestamp, features, SELECTED) == {
        "BTC-USDT": 0.0,
        "ETH-USDT": 0.0,
    }


def test_higher_risk_profile_scales_weights_without_leverage():
    timestamp = pd.Timestamp("2026-11-02", tz="UTC")
    features = {
        symbol: pd.DataFrame(
            {"trend": [0.1], "momentum": [0.1], "volatility": [0.15]},
            index=[timestamp],
        )
        for symbol in ("BTC-USDT", "ETH-USDT")
    }
    moderate = DefensiveRisk(per_asset_cap=0.2, max_deployment=0.4)
    aggressive = DefensiveRisk(per_asset_cap=0.5, max_deployment=1.0)
    assert target_weights(timestamp, features, SELECTED, moderate) == {
        "BTC-USDT": 0.2,
        "ETH-USDT": 0.2,
    }
    assert target_weights(timestamp, features, SELECTED, aggressive) == {
        "BTC-USDT": 0.5,
        "ETH-USDT": 0.5,
    }


def test_cost_stress_reduces_selected_evaluation_result():
    data = {
        symbol: load_long_history(symbol)
        for symbol in ("BTC-USDT", "ETH-USDT")
    }
    base = simulate(data, SELECTED, "2024-01-01", "2024-12-31", cost_bps=15)
    stress = simulate(data, SELECTED, "2024-01-01", "2024-12-31", cost_bps=30)
    assert base["fill_count"] > 0
    assert stress["ending_equity"] < base["ending_equity"]


def test_locked_selection_and_historical_claim_are_reproducible():
    root = Path("research/defensive_trend")
    protocol = json.loads((root / "protocol.json").read_text())
    lock = json.loads((root / "selection_locked.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    assert hashlib.sha256(dumps(protocol).encode()).hexdigest() == lock[
        "protocol_sha256"
    ]
    assert lock["selected"] == SELECTED.as_dict()
    assert summary["selection"] == {
        "tested": 81,
        "eligible": 14,
        "protocol_sha256": lock["protocol_sha256"],
    }
    assert summary["qualification"]["historically_profitable"]
    assert not summary["qualification"]["deployment_qualified"]
    for result in summary["periods"].values():
        assert result["net_return"] > 0
        assert result["max_drawdown"] > -0.10
