import pandas as pd
import pytest

from trader.db import DB
from trader.growth.config import GrowthConfig
from trader.growth.forward import configure, control, tick
from trader.growth.models import fit, hourly, predict
from trader.growth.portfolio import execute
from trader.growth.weekly import weekly_report


def test_hourly_aggregation_and_mature_labels():
    df = hourly("BTC-USDT")
    assert len(df) == 17520
    model, meta = fit(
        df, "BTC-USDT", pd.Timestamp("2025-08-01", tz="UTC"), "boosted", 72, 0.003
    )
    assert pd.Timestamp(meta["last_maturity"]) < pd.Timestamp(meta["cutoff"])
    before = predict(model, df)
    changed = df.copy()
    changed.loc["2025-09-01":, ["close", "volume"]] *= 2
    pd.testing.assert_series_equal(
        before.loc[:"2025-08-31"], predict(model, changed).loc[:"2025-08-31"]
    )


def test_continuous_portfolio_limits_and_same_trade_costs():
    d = {s: hourly(s).loc["2026-01-31":"2026-02-01"] for s in ("BTC-USDT", "ETH-USDT")}
    dec = {
        t.value: {s: {"enter": True, "horizon": 72, "stop": 0.03} for s in d}
        for t in d["BTC-USDT"].index
    }
    r = execute(d, dec, benchmark=True)
    assert len(r["fills"]) == 2  # no artificial liquidation at the month boundary
    assert all(p["cash"] >= 0 for p in r["equity"])
    assert r["same_trade_gross_return"] > r["net_return"]
    assert r["fees"] > 0
    for f in r["fills"]:
        assert float(f["filled_qty"]) * f["avg_px"] <= 150.01
    assert r["cash"] >= 199


def test_weekly_singapore_boundaries_and_sample_gate():
    dates = pd.date_range("2025-01-05T16:00:00Z", periods=24 * 56, freq="h")
    points = [
        {"timestamp": str(t), "equity": 500 + i * 0.001} for i, t in enumerate(dates)
    ]
    r = weekly_report(points, 500, exits=2, stress_positive=True)
    assert next(iter(r["weeks"])) == "2025-01-06"
    assert r["complete_weeks"] == 8
    assert not r["qualified"]
    assert "Insufficient completed trades" in r["reasons"]
    assert r["losing_weeks"] == 0


def test_forward_restart_and_duplicate_observation(tmp_path):
    db = DB(tmp_path / "test.db")
    configure(db, {})
    control(db, "start")
    q = {
        "BTC-USDT": {"bid": 70000, "ask": 70010, "provider_timestamp": 1},
        "ETH-USDT": {"bid": 2000, "ask": 2001, "provider_timestamp": 1},
    }
    at = pd.Timestamp("2026-11-04T00:00:00Z")
    r = tick(db, (at, q))
    assert r["observations"] == 1 and r["result"]["ending_equity"] == 500
    r = tick(DB(tmp_path / "test.db"), (at, q))
    assert r["observations"] == 1
    assert r["result"]["fills"] == []
    assert not r["qualification"]["qualified"]
    with pytest.raises(ValueError):
        configure(db, {"capital": 600})
    db.set_state("kill", True)
    assert not tick(db, (at + pd.Timedelta(minutes=1), q))["active"]


def test_forward_outage_fails_closed(tmp_path, monkeypatch):
    from trader.growth import forward

    db = DB(tmp_path / "test.db")
    configure(db, {})
    control(db, "start")

    def broken():
        raise TimeoutError("no response")

    monkeypatch.setattr(forward, "observe", broken)
    r = forward.tick(db)
    assert not r["active"] and r["error"] == "TimeoutError"
    assert not db.rows("SELECT * FROM growth_fills")


def test_risk_limits_validated():
    for bad in [
        {"deployment": 0.9},
        {"per_asset": 0.5},
        {"reserve": 0.1},
        {"drawdown_halt": 0.2},
        {"trade_risk": 0.02},
    ]:
        with pytest.raises(ValueError):
            GrowthConfig(**bad)


def test_unqualified_models_cannot_enter_forward_simulation(tmp_path):
    db = DB(tmp_path / "test.db")
    with pytest.raises(ValueError, match="qualified"):
        configure(db, {}, {"BTC-USDT": "a" * 24})


def test_stale_public_quotes_fail_closed(monkeypatch):
    from unittest.mock import Mock

    from trader.growth import forward

    response = Mock()
    response.json.return_value = {
        "code": "0",
        "data": [{"bidPx": "70000", "askPx": "70001", "ts": "1"}],
    }
    monkeypatch.setattr(forward.requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError, match="stale"):
        forward.observe(pd.Timestamp("2026-11-04T00:00:00Z"))


def test_forward_start_requires_configuration(tmp_path):
    db = DB(tmp_path / "test.db")
    with pytest.raises(ValueError, match="Configure"):
        control(db, "start")


def test_model_promotion_does_not_reset_forward_observations(tmp_path):
    from trader.growth.forward import promote

    db = DB(tmp_path / "test.db")
    configure(db, {})
    control(db, "start")
    q = {
        "BTC-USDT": {"bid": 70000, "ask": 70010},
        "ETH-USDT": {"bid": 2000, "ask": 2001},
    }
    tick(db, (pd.Timestamp("2026-11-04T00:00:00Z"), q))
    with pytest.raises(ValueError, match="qualified"):
        promote(db, {"BTC-USDT": "a" * 24})
    r = promote(db, {})
    assert r["observations"] == 1 and r["result"]["ending_equity"] == 500
