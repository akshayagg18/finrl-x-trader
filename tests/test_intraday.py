import pandas as pd
import pytest
from fastapi.testclient import TestClient

from trader.api import create_app
from trader.intraday.engine import Experiment, backtest, load, signals


def test_future_bars_cannot_change_earlier_signals():
    df = load("AAPL")
    c = Experiment()
    original = signals(df, c)
    changed = df.copy()
    changed.loc[changed.index[100] :, "close"] *= 2
    pd.testing.assert_series_equal(original.iloc[:101], signals(changed, c).iloc[:101])


def test_cash_preserved_and_whole_shares_enforced():
    r = backtest({"symbol": "QQQ", "strategy": "cash"}, "2026-10-01", "2026-10-15")
    assert r["ending_equity"] == 500 and not r["fills"]
    r = backtest(
        {"symbol": "QQQ", "strategy": "hold", "allocation": 0.5},
        "2026-10-01",
        "2026-10-15",
    )
    assert not r["fills"] and r["blocked"]


def test_fees_reduce_identical_hold():
    a = backtest(
        {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8, "fee_bps": 0},
        "2026-10-01",
        "2026-10-15",
    )
    b = backtest(
        {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8, "fee_bps": 10},
        "2026-10-01",
        "2026-10-15",
    )
    assert len(a["fills"]) == len(b["fills"]) == 2
    assert b["ending_equity"] < a["ending_equity"]


def test_config_and_results_survive_restart(tmp_path):
    path = tmp_path / "test.db"
    headers = {"X-Trader-Intent": "console"}
    with TestClient(create_app(path, with_scheduler=False)) as client:
        old = client.get("/api/settings").json()
        assert (
            client.put(
                "/api/intraday/settings",
                json={"capital": 500, "symbol": "AAPL"},
                headers=headers,
            ).status_code
            == 200
        )
        r = client.post(
            "/api/intraday/backtest",
            json={
                "settings": {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8},
                "start": "2026-10-01",
                "end": "2026-10-15",
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["fills"]) == 2
        assert client.get("/api/settings").json() == old
    with TestClient(create_app(path, with_scheduler=False)) as client:
        assert client.get("/api/intraday/settings").json()["capital"] == 500
        assert len(client.get("/api/intraday/runs").json()) == 1


def test_disallow_leverage():
    with pytest.raises(ValueError):
        Experiment(allocation=2)
