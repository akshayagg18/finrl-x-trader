import numpy as np
import pandas as pd

from scripts.deepen_long_cash import (
    CryptoEnsembleSpec,
    EtfExposureSpec,
    crypto_target_weights,
    etf_target_weights,
    simulate_etf,
)


def _crypto_features(votes=5, volatility=0.3):
    date = pd.Timestamp("2026-01-05", tz="UTC")
    return {
        symbol: pd.DataFrame(
            {"votes": [votes], "momentum_average": [0.1], "volatility": [volatility]},
            index=[date],
        )
        for symbol in ("BTC-USDT", "ETH-USDT")
    }, date


def _etf_data():
    dates = pd.bdate_range("2020-01-02", periods=1600)
    slopes = {"SPY": 0.45, "QQQ": 0.6, "IWM": 0.2, "GLD": 0.25, "TLT": -0.1, "SHY": 0.03}
    result = {}
    for symbol, slope in slopes.items():
        close = 100 * np.exp(np.linspace(0, slope, len(dates)))
        result[symbol] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 1_000_000,
            },
            index=dates,
        )
    return result


def test_crypto_ensemble_caps_and_drawdown_brake():
    features, date = _crypto_features()
    plain = CryptoEnsembleSpec("majority_each", "weekly", 0.3)
    weights = crypto_target_weights(date, features, plain)
    assert max(weights.values()) <= 0.20
    assert sum(weights.values()) <= 0.40
    brake = CryptoEnsembleSpec("majority_each_brake", "weekly", 0.3)
    assert crypto_target_weights(date, features, brake, drawdown=-0.11) == {
        "BTC-USDT": 0.0,
        "ETH-USDT": 0.0,
    }


def test_etf_exposure_caps_and_removal_reranks():
    data = _etf_data()
    date = data["SPY"].index[-1]
    spec = EtfExposureSpec(0.30, 0.60, 0.20)
    weights, detail = etf_target_weights(data, date, spec)
    assert detail["selected"][0] == "QQQ"
    assert max(weights.values()) <= 0.30
    assert sum(weights.values()) <= 0.60
    removed, detail_removed = etf_target_weights(data, date, spec, excluded="QQQ")
    assert "QQQ" not in detail_removed["selected"]
    assert removed["QQQ"] == 0


def test_etf_cost_delay_and_minimum_order_stresses_are_real():
    data = _etf_data()
    spec = EtfExposureSpec(0.30, 0.60, 0.20)
    base = simulate_etf(data, spec, "2023-01-03", "2025-12-31")
    cost = simulate_etf(data, spec, "2023-01-03", "2025-12-31", cost_bps=60)
    delayed = simulate_etf(data, spec, "2023-01-03", "2025-12-31", delay_sessions=3)
    minimum = simulate_etf(data, spec, "2023-01-03", "2025-12-31", minimum_order=10)
    assert base["fill_count"] > 0
    assert cost["transaction_costs"] > base["transaction_costs"]
    assert delayed["fills"][0]["timestamp"] != base["fills"][0]["timestamp"]
    assert minimum["fill_count"] <= base["fill_count"]
