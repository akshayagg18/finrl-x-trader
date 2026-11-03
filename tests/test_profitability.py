import numpy as np
import pandas as pd
from pathlib import Path

from trader.opening_range import opening_range_backtest
from trader.profitability import (
    ExecutionConfig,
    aligned_target,
    feature_frame,
    fit_xgboost,
    passive_buy_and_hold,
    regime_frame,
    simulate,
)


def synthetic_crypto(periods=1800, freq="15min"):
    index = pd.date_range("2024-01-01", periods=periods, freq=freq, tz="UTC")
    change = 0.0001 + 0.002 * np.sin(np.arange(periods) / 17)
    close = 100 * np.cumprod(1 + change)
    return pd.DataFrame(
        {
            "open": close / (1 + change),
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": 1_000 + 100 * np.cos(np.arange(periods) / 9),
        },
        index=index,
    )


def test_cost_aware_features_and_labels_do_not_look_forward():
    df = synthetic_crypto(500)
    before = feature_frame(df)
    changed = df.copy()
    changed.loc[changed.index[300]:, ["open", "high", "low", "close", "volume"]] *= 5
    pd.testing.assert_frame_equal(before.iloc[:300], feature_frame(changed).iloc[:300])
    target, maturity = aligned_target(df, 4)
    assert target.iloc[0] == df.open.iloc[5] / df.open.iloc[1] - 1
    assert maturity.iloc[0] == df.index[5]


def test_xgboost_training_uses_only_matured_labels():
    df = synthetic_crypto()
    cutoff = df.index[1500]
    _, meta = fit_xgboost(df, 4, df.index[0], cutoff)
    assert meta["rows"] >= 1000
    assert pd.Timestamp(meta["last_label_maturity"]) < cutoff


def test_cost_thresholds_small_orders_and_risk_accounting():
    df = synthetic_crypto(600)
    forecasts = pd.Series(0.02, index=df.index)
    regimes = regime_frame(df, df.index[:300])
    result = simulate(
        df,
        forecasts,
        df.index[300],
        df.index[-2],
        execution=ExecutionConfig(capital=500, max_exposure=0.6),
        threshold_multiplier=2,
        uncertainty=0.001,
        regimes=regimes,
    )
    assert result["signal_counts"]["net_candidate_signals"] >= 1
    assert result["signal_counts"]["submitted_orders"] == 2
    assert result["metrics"]["completed_trades"] == 1
    assert result["total_costs"] > 0
    assert max(t["notional"] for t in result["trades"] if t["side"] == "BUY") <= 300.01
    blocked = simulate(
        df,
        pd.Series(0.0001, index=df.index),
        df.index[300],
        df.index[-2],
        regimes=regimes,
    )
    assert blocked["signal_counts"]["gross_candidate_signals"] > 0
    assert blocked["signal_counts"]["submitted_orders"] == 0


def test_long_only_orb_uses_relative_volume_and_fractional_cash_sizing():
    rows = []
    for day in pd.date_range("2026-01-02", periods=20, freq="B"):
        local = pd.date_range(
            pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta("9h30min"),
            periods=26,
            freq="15min",
        ).tz_convert("UTC")
        first_volume = 250_000 if day == pd.date_range("2026-01-02", periods=20, freq="B")[-1] else 100_000
        for i, timestamp in enumerate(local):
            price = 100 + 0.02 * i
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": price,
                    "high": price + (0.15 if i else 0.10),
                    "low": price - 0.05,
                    "close": price + 0.05,
                    "volume": first_volume if i == 0 else 50_000,
                }
            )
    frame = pd.DataFrame(rows).set_index("timestamp")
    result = opening_range_backtest({"AAPL": frame})
    assert any(x["eligible"] for x in result["diagnostics"])
    assert result["metrics"]["completed_trades"] >= 1
    assert all(t["units"] % 1 != 0 for t in result["trades"])
    assert max(t["units"] * t["entry"] for t in result["trades"]) <= 250.01


def test_profitability_results_are_connected_to_read_only_dashboard():
    app = Path("trader/static/app.js").read_text()
    api = Path("trader/growth/api.py").read_text()
    assert "growth/profitability" in app
    assert "profitability-summary" in app
    assert '@routes.get("/profitability")' in api
    route = api[api.index('@routes.get("/profitability")'):api.index('@routes.get("/forward")')]
    assert "@routes.post" not in route


def test_passive_benchmark_is_fractional_costed_and_not_risk_halted():
    df = synthetic_crypto(600)
    result = passive_buy_and_hold(
        df,
        df.index[100],
        df.index[500],
        execution=ExecutionConfig(capital=500, max_exposure=0.6),
    )
    assert result["signal_counts"] == {"submitted_orders": 2, "simulated_fills": 2}
    assert result["total_costs"] > 0
    assert result["time_invested"] == 1.0
    assert not result["halted"]
    assert result["trades"][0]["notional"] == 300
