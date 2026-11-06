import numpy as np
import pandas as pd

from scripts.evaluate_etf_rotation import RotationSpec, simulate, target_weights


def _data(change_current_close=False):
    dates = pd.bdate_range("2022-01-03", periods=380)
    result = {}
    slopes = {"SPY": 0.25, "QQQ": 0.35, "IWM": 0.12, "GLD": 0.08, "TLT": -0.1, "SHY": 0.02}
    for symbol, slope in slopes.items():
        close = 100 * np.exp(np.linspace(0, slope, len(dates)))
        frame = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 1_000_000,
            },
            index=dates,
        )
        result[symbol] = frame
    if change_current_close:
        result["QQQ"].iloc[-1, result["QQQ"].columns.get_loc("close")] *= 10
    return result


def test_rotation_uses_prior_data_and_caps_exposure():
    spec = RotationSpec(126, 150, 2, 0.25)
    data = _data()
    date = data["SPY"].index[-1]
    weights, features = target_weights(data, date, spec)
    changed, _ = target_weights(_data(change_current_close=True), date, spec)
    assert weights == changed
    assert features["selected"][0] == "QQQ"
    assert max(weights.values()) <= 0.20
    assert sum(weights.values()) <= 0.40


def test_rotation_simulation_models_costs_and_fractional_positions():
    spec = RotationSpec(126, 150, 2, 0.25)
    data = _data()
    base = simulate(data, spec, "2023-01-03", "2023-06-16", cost_bps=15)
    stress = simulate(data, spec, "2023-01-03", "2023-06-16", cost_bps=30)
    assert base["fill_count"] > 0
    assert base["transaction_costs"] > 0
    assert stress["ending_equity"] < base["ending_equity"]
    assert base["cash"] >= 0
    assert any(quantity % 1 for quantity in base["positions"].values() if quantity)
    assert all(
        sum(decision["weights"].values()) <= 0.40
        for decision in base["decisions"]
    )


def test_rotation_holds_cash_until_declared_warmup_exists():
    spec = RotationSpec(252, 200, 2, 0.25)
    data = _data()
    result = simulate(data, spec, "2022-01-03", "2022-02-28")
    assert result["ending_equity"] == 500
    assert result["fill_count"] == 0
    assert result["decisions"][0]["features"]["reason"].startswith("Full declared")
