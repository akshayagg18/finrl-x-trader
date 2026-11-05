import numpy as np
import pandas as pd
import pytest

from trader.db import DB
from trader.growth.defensive_forward import (
    configure,
    control,
    decision_from_closes,
    status,
    tick,
)


def _observation(at: str, *, rising: bool = True, bid_scale: float = 1.0):
    timestamp = pd.Timestamp(at)
    dates = pd.date_range(
        end=timestamp.normalize() - pd.Timedelta(days=1),
        periods=130,
        freq="1D",
        tz="UTC",
    )
    btc = np.linspace(50_000, 70_000, len(dates))
    eth = np.linspace(2_000, 3_000, len(dates))
    if not rising:
        btc = btc[::-1]
        eth = eth[::-1]
    histories = {
        "BTC-USDT": pd.Series(btc, index=dates),
        "ETH-USDT": pd.Series(eth, index=dates),
    }
    quotes = {
        "BTC-USDT": {
            "bid": 70_000 * bid_scale,
            "ask": 70_010 * bid_scale,
        },
        "ETH-USDT": {"bid": 3_000 * bid_scale, "ask": 3_001 * bid_scale},
    }
    return timestamp, quotes, histories


def test_selected_forward_weights_are_causal_and_bounded():
    _, _, histories = _observation("2026-11-06T00:05:00Z")
    weights, features = decision_from_closes(histories)
    assert 0 < weights["BTC-USDT"] <= 0.20
    assert 0 < weights["ETH-USDT"] <= 0.20
    assert sum(weights.values()) <= 0.40
    assert features["BTC-USDT"]["trend"] > 0
    down = _observation("2026-11-06T00:05:00Z", rising=False)[2]
    assert decision_from_closes(down)[0] == {
        "BTC-USDT": 0.0,
        "ETH-USDT": 0.0,
    }


def test_forward_persists_deduplicates_and_rebalances_once_per_week(tmp_path):
    path = tmp_path / "forward.db"
    db = DB(path)
    configure(db, {"capital": 500})
    control(db, "start")
    first = tick(db, _observation("2026-11-06T00:05:00Z"))
    assert first["observations"] == 1
    assert first["decision_weeks"] == 1
    assert len(first["result"]["fills"]) == 2
    assert first["result"]["cash"] >= 299
    assert not first["live_orders_possible"]

    duplicate = tick(DB(path), _observation("2026-11-06T12:00:00Z"))
    assert duplicate["observations"] == 1
    assert len(duplicate["result"]["fills"]) == 2

    next_day = tick(DB(path), _observation("2026-11-07T00:05:00Z"))
    assert next_day["observations"] == 2
    assert next_day["decision_weeks"] == 1
    assert len(next_day["result"]["fills"]) == 2

    next_week = tick(
        DB(path), _observation("2026-11-09T00:05:00Z", bid_scale=1.01)
    )
    assert next_week["observations"] == 3
    assert next_week["decision_weeks"] == 2
    assert len(next_week["result"]["fills"]) >= 2
    assert len(db.rows("SELECT * FROM defensive_forward_fills")) == len(
        next_week["result"]["fills"]
    )


def test_forward_config_freezes_and_kill_stops_collection(tmp_path):
    db = DB(tmp_path / "forward.db")
    configure(db, {})
    control(db, "start")
    tick(db, _observation("2026-11-06T00:05:00Z"))
    with pytest.raises(ValueError, match="frozen"):
        configure(db, {"capital": 600})
    db.set_state("kill", True)
    stopped = tick(db, _observation("2026-11-07T00:05:00Z"))
    assert not stopped["active"]
    assert stopped["error"] == "Global kill"
    assert stopped["observations"] == 1


def test_start_requires_configuration(tmp_path):
    db = DB(tmp_path / "forward.db")
    assert not status(db)["configured"]
    with pytest.raises(ValueError, match="Configure"):
        control(db, "start")
