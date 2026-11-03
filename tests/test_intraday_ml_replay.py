
import pandas as pd
import pytest

from trader.db import DB
from trader.intraday.engine import Experiment, backtest, load
from trader.intraday.ml import features, prediction, train
from trader.intraday.replay import control, create, inspect, step
from trader.scheduler import Scheduler
from trader.service import Service


def test_features_have_no_future_dependency():
    df = load("BTC-USDT")
    x = features(df)
    changed = df.copy()
    changed.loc[changed.index[200] :, ["open", "high", "low", "close", "volume"]] *= 3
    pd.testing.assert_frame_equal(x.iloc[:201], features(changed).iloc[:201])


def test_training_maturity_and_artifact_integrity(tmp_path):
    m = train("BTC-USDT", 15, "2025-01-01", root=tmp_path)
    assert pd.Timestamp(m["last_label_maturity"]) < pd.Timestamp(m["cutoff"])
    df = load("BTC-USDT")
    y, _ = prediction(df, m["id"], "BTC-USDT", 15, root=tmp_path)
    assert y.loc[:"2024-12-31"].isna().all()
    assert y.loc["2025-01-01":].notna().any()
    with pytest.raises(ValueError):
        prediction(df, m["id"], "ETH-USDT", 15, root=tmp_path)
    p = tmp_path / (m["id"] + ".joblib")
    p.write_bytes(p.read_bytes() + b"bad")
    with pytest.raises(ValueError, match="integrity"):
        prediction(df, m["id"], "BTC-USDT", 15, root=tmp_path)


def test_replay_restart_matches_uninterrupted_and_preserves_ownership(tmp_path):
    db = DB(tmp_path / "state.db")
    old = db.settings().model_dump()
    c = {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8}
    sid = create(db, c, "2026-10-01", "2026-10-05")
    control(db, sid, "start")
    first = step(db, sid, 2)
    assert first["result"]["quantity"] == 1
    resumed = step(DB(tmp_path / "state.db"), sid, 2)
    expected = backtest(c, "2026-10-01", resumed["result"]["end"], liquidate=False)
    assert resumed["result"]["ending_equity"] == expected["ending_equity"]
    assert resumed["result"]["quantity"] == 1
    assert len(db.rows("SELECT * FROM intraday_fills")) == 1
    assert db.settings().model_dump() == old
    assert not db.rows("SELECT * FROM orders")
    control(db, sid, "stop")
    cursor = resumed["cursor"]
    step(db, sid)
    assert inspect(db, sid)["cursor"] == cursor


def test_pause_liquidation_and_global_kill(tmp_path):
    db = DB(tmp_path / "state.db")
    sid = create(
        db,
        {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8},
        "2026-10-01",
        "2026-10-05",
    )
    control(db, sid, "pause")
    assert step(db, sid, 2)["result"]["quantity"] == 0
    control(db, sid, "resume")
    assert step(db, sid, 2)["result"]["quantity"] == 1
    control(db, sid, "pause")
    assert step(db, sid, 2)["result"]["quantity"] == 1
    control(db, sid, "liquidate")
    assert step(db, sid, 2)["result"]["quantity"] == 0
    assert len(db.rows("SELECT * FROM intraday_fills")) == 2
    db.set_state("kill", True)
    assert not step(db, sid)["active"]
    with pytest.raises(ValueError, match="kill"):
        control(db, sid, "start")


def test_scheduler_restores_persistent_session(tmp_path):
    service = Service(tmp_path / "state.db")
    sid = create(
        service.db,
        {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8},
        "2026-10-01",
        "2026-10-05",
    )
    control(service.db, sid, "start")
    service.db.set_state("intraday_enabled", True)
    Scheduler(service).tick()
    cursor = inspect(service.db, sid)["cursor"]
    Scheduler(Service(tmp_path / "state.db")).tick()
    assert inspect(service.db, sid)["cursor"] > cursor


def test_equity_proceeds_remain_unsettled_until_next_session():
    r = backtest(
        {"symbol": "AAPL", "strategy": "hold", "allocation": 0.8},
        "2026-10-02",
        "2026-10-02",
    )
    assert r["unsettled"]
    assert r["unsettled"][0][0] == "2026-10-05"
    assert r["quantity"] == 0


def test_one_active_session_and_invalid_settings(tmp_path):
    db = DB(tmp_path / "state.db")
    sid = create(db, {"symbol": "AAPL"}, "2026-10-01", "2026-10-05")
    control(db, sid, "start")
    with pytest.raises(ValueError):
        create(db, {"symbol": "AAPL"}, "2026-10-01", "2026-10-05")
    for c in [{"capital": float("nan")}, {"interval": 1}, {"allocation": 2}]:
        with pytest.raises(ValueError):
            Experiment(**c)


def test_exchange_modes_missing_credentials_and_ambiguous_submission(monkeypatch):
    from unittest.mock import Mock

    from trader.brokers import AmbiguousOrder, BrokerError, MissingCredentials
    from trader.intraday.exchange import OKXSpot

    for prefix in ("OKX_DEMO", "OKX_LIVE"):
        for key in ("KEY", "SECRET", "PASSPHRASE"):
            monkeypatch.delenv(prefix + "_" + key, raising=False)
    for mode in ("paper", "live"):
        with pytest.raises(MissingCredentials):
            OKXSpot(mode)
    client = Mock()
    client.market.return_value = {
        "spot": True,
        "active": True,
        "limits": {"amount": {"min": 0.00001}},
    }
    client.amount_to_precision.return_value = "0.001"
    adapter = OKXSpot(client=client)
    with pytest.raises(BrokerError):
        adapter.submit(symbol="BTC/USDT", side="buy", quantity=0.001, client_id="abc")
    client.create_order.side_effect = TimeoutError("secret must not leak")
    with pytest.raises(AmbiguousOrder, match="uncertain"):
        adapter.submit(
            symbol="BTC/USDT",
            side="buy",
            quantity=0.001,
            client_id="abc",
            authorized=True,
        )
    assert client.create_order.call_count == 1
