from types import SimpleNamespace as N
import pandas as pd
import pytest
from pydantic import ValidationError
from trader.config import Settings
from trader.brokers import (
    AlpacaBroker,
    MissingCredentials,
    Account,
    qty_round,
    Instrument,
    BrokerError,
)
from trader.ledger import Ledger, LocalBroker
from trader.risk import RiskEngine, RiskBlocked
from trader.data import MarketData, DataError, validate, aligned, REQUIRED
from trader.db import now
from trader.service import Service
from trader.metrics import metrics
from trader.scheduler import is_open, next_operation, Scheduler
from trader.backtest import run_backtest
from trader.strategies import StrategyEngine


def test_defaults_validation():
    s = Settings()
    assert s.capital.allocated == 500 and s.broker.mode == "simulation"
    for update in [
        {"capital": {"allocated": -1}},
        {"risk": {"max_position": 1.1}},
        {"broker": {"broker": "alpaca"}},
        {"risk": {"max_order": float("nan")}},
        {"unknown": 1},
    ]:
        with pytest.raises(ValidationError):
            Settings.model_validate(update)


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_missing_credentials(mode, monkeypatch):
    for key in [
        "ALPACA_PAPER_KEY",
        "ALPACA_PAPER_SECRET",
        "ALPACA_LIVE_KEY",
        "ALPACA_LIVE_SECRET",
    ]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(MissingCredentials):
        AlpacaBroker(mode)


def test_mode_isolation(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_KEY", "not-a-real-key")
    monkeypatch.setenv("ALPACA_PAPER_SECRET", "not-a-real-secret")
    monkeypatch.delenv("ALPACA_LIVE_KEY", raising=False)
    with pytest.raises(MissingCredentials):
        AlpacaBroker("live")


def test_fractional_rounding():
    assert qty_round(0.43219999, True) == 0.432199
    assert qty_round(0.8, False) == 0


def test_settings_persist_and_capital_flow(service):
    s = service.db.settings()
    s.capital.allocated = 600
    s.risk.max_order = 80
    service.update_settings(s.model_dump())
    restored = Service(service.db.path)
    assert restored.db.settings().risk.max_order == 80
    assert restored.overview()["account"]["cash"] == 600
    assert restored.overview()["account"]["contributions"] == 600
    assert len(restored.db.rows("SELECT * FROM settings")) == 2


def test_real_data_cycle_restart_and_idempotency(service):
    r = service.cycle(replay_date="2025-01-06")
    assert r["raw_targets"] and r["fills"]
    assert all(o["status"] == "filled" and 0 < o["qty"] < 1 for o in r["fills"])
    value = service.overview()
    assert value["account"]["cash"] >= 100
    restored = Service(service.db.path)
    assert restored.overview()["positions"] == value["positions"]
    again = restored.cycle(replay_date="2025-01-06")
    assert again["cycle"] == r["cycle"]
    assert len(restored.overview()["orders"]) == len(r["fills"])
    for o in r["fills"]:
        assert o["intended"] <= 100


def test_dry_run_no_execution(service):
    r = service.cycle(replay_date="2025-01-06", dry_run=True)
    assert r["orders"] and not service.overview()["orders"]
    assert service.overview()["equity"] == 500


def test_strategy_no_future_leak(service):
    data = service.data.load(
        service.db.settings().strategy.universe + REQUIRED, through="2025-02-28"
    )
    engine = StrategyEngine(service.db.settings().strategy)
    a, _ = engine.targets(data, "2025-01-03")
    for df in data.values():
        df.loc[df.index > "2025-01-03", "close"] *= 100
    b, _ = StrategyEngine(service.db.settings().strategy).targets(data, "2025-01-03")
    assert a == b


def test_risk_weights_sector_and_volatility(service):
    s = service.db.settings()
    data = service.data.load(s.strategy.universe + REQUIRED, through="2025-01-03")
    w, reason = RiskEngine(s).weights(
        {"AAPL": 0.5, "MSFT": 0.5}, data, pd.Timestamp("2025-01-03")
    )
    assert max(w.values()) <= 0.25 and sum(w.values()) <= 0.5 and reason
    with pytest.raises(RiskBlocked):
        RiskEngine(s).weights({"AAPL": -1}, data, pd.Timestamp("2025-01-03"))


@pytest.mark.parametrize(
    "value,peak,day,reason",
    [(480, 500, 500, "daily"), (425, 600, 425, "drawdown"), (390, 400, 390, "capital")],
)
def test_portfolio_losses(value, peak, day, reason):
    risk = RiskEngine(Settings())
    trigger = risk.loss_trigger(value, {"peak": peak, "contributions": 500}, day)
    assert reason in trigger.lower()


def test_insufficient_cash_and_unowned_positions(service):
    s = service.db.settings()
    scope = service.scope()
    b = LocalBroker(service.db, scope, s.simulation, {"AAPL": 200})
    r = RiskEngine(s)
    with pytest.raises(RiskBlocked):
        r.final(
            {"qty": 1, "symbol": "AAPL", "side": "sell", "intended": 50},
            b,
            {},
            500,
            200,
        )
    with pytest.raises(RiskBlocked):
        r.final(
            {"qty": 1, "symbol": "AAPL", "side": "buy", "intended": 50}, b, {}, 10, 200
        )
    fake = N(account=lambda: Account("acct", 2000, 2000, 2000))
    orders, _ = r.plan(
        {"AAPL": 0.25},
        {"AAPL": 200},
        {},
        dict(cash=500, contributions=500),
        500,
        N(account=fake.account, instrument=lambda s: Instrument(s, True, True)),
    )
    assert sum(o["intended"] for o in orders) <= 125


def insert_order(service, qty=1, side="buy", oid="test", price=10):
    with service.db.connect() as c:
        c.execute(
            "INSERT INTO orders(id,scope,cycle,created,symbol,side,qty,intended,status) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                oid,
                service.scope(),
                "test",
                now(),
                "AAPL",
                side,
                qty,
                qty * price,
                "prepared",
            ),
        )
    return {"id": oid, "symbol": "AAPL", "side": side, "qty": qty}


def test_partial_fill_incremental_and_recovery(service):
    s = service.db.settings()
    s.simulation.fill_fraction = 0.5
    b = LocalBroker(service.db, service.scope(), s.simulation, {"AAPL": 10})
    order = insert_order(service)
    report = b.submit(order)
    assert report["status"] == "partially_filled"
    l = Ledger(service.db, service.scope())
    cash = l.account()["cash"]
    l.apply(order["id"], report)
    assert l.account()["cash"] == cash
    l.apply(
        order["id"], {**report, "status": "filled", "filled_qty": 1, "fill_price": 11}
    )
    assert l.positions()["AAPL"]["qty"] == 1
    assert l.account()["cash"] == pytest.approx(489)
    b.cancel(order["id"])
    assert b.inspect(order["id"])["status"] == "filled"


def test_rejected_order(service):
    s = service.db.settings()
    b = LocalBroker(service.db, service.scope(), s.simulation, {"AAPL": 1000})
    order = insert_order(service, qty=1)
    report = b.submit(order)
    assert (
        report["status"] == "rejected" and not b.positions() and b.account().cash == 500
    )


def test_stale_missing_invalid_data(service, tmp_path):
    with pytest.raises(DataError):
        service.cycle()
    with pytest.raises(DataError):
        MarketData(tmp_path).load(["MISSING"])
    df = pd.DataFrame(
        {
            "open": [1, 2],
            "close": [1, float("nan")],
            "high": [1, 2],
            "low": [1, 2],
            "volume": [1, 1],
        },
        index=pd.date_range("2025-01-01", periods=2),
    )
    with pytest.raises(DataError):
        validate(df)
    with pytest.raises(DataError):
        aligned({"A": df})


def test_dedicated_account_fail_closed(service):
    fake = N(
        positions=lambda: {"AAPL": 10},
        open_orders=lambda: [],
        account=lambda: Account("external", 2000, 3000, 2000),
    )
    with pytest.raises(RiskBlocked, match="Position mismatch"):
        service.reconcile(fake, service.scope())
    s = service.db.settings()
    s.broker.broker = "alpaca"
    s.broker.mode = "paper"
    with pytest.raises(RiskBlocked, match="Dedicated"):
        service.external(s)


def test_network_timeout_does_not_resubmit(service, monkeypatch):
    def timeout(self, order):
        raise TimeoutError("Do not expose secrets")

    monkeypatch.setattr(LocalBroker, "submit", timeout)
    with pytest.raises(TimeoutError):
        service.cycle(replay_date="2025-01-06")
    assert len(service.overview()["orders"]) == 1
    with pytest.raises(RiskBlocked, match="Interrupted"):
        Service(service.db.path).cycle(replay_date="2025-01-06")
    assert len(service.overview()["orders"]) == 1


def test_unknown_external_order_halts(service):
    insert_order(service)
    fake = N(inspect=lambda oid: None)
    with pytest.raises(RiskBlocked, match="Unresolved"):
        service.reconcile(fake, service.scope())


def test_kill_and_pause(service):
    service.control("start")
    service.control("pause")
    assert service.db.state("paused")
    service.control("kill")
    with pytest.raises(RiskBlocked):
        service.cycle(replay_date="2025-01-06")
    service.control("reset")
    assert not service.db.state("kill")


def test_calendar_dst_holidays_early_close():
    assert not is_open("2025-07-04T15:00:00Z")
    assert is_open("2025-07-03T16:00:00Z")
    assert not is_open("2025-07-03T18:00:00Z")
    assert next_operation(15, "2025-03-07T22:00:00Z") == "2025-03-10T13:45:00+00:00"


def test_scheduler_persisted_resume(service, monkeypatch):
    service.control("start")
    service.db.set_state("paused", True)
    restored = Service(service.db.path)
    calls = []
    monkeypatch.setattr(restored, "cycle", lambda **kw: calls.append(kw))
    Scheduler(restored).tick("2025-01-06T15:30:00Z")
    assert calls and calls[0]["protect_only"] is True
    assert restored.db.state("next_operation")


def test_metrics_cash_flow_correctness():
    p = [
        {"equity": 110, "flow": 0},
        {"equity": 165, "flow": 55},
        {"equity": 181.5, "flow": 0},
    ]
    r = metrics(p, [], 100)
    assert r["total_return"] == pytest.approx(0.21)
    assert r["annualized_return"] is None and r["sharpe"] is None
    p = [{"equity": 90, "flow": 0}, {"equity": 99, "flow": 0}]
    assert metrics(p, [], 100)["max_drawdown"] == pytest.approx(-0.1)


def test_backtest_determinism_costs_and_oos(service, small_settings):
    s = small_settings
    s.simulation.commission_fixed = 0.05
    a = run_backtest(service, s, "2025-01-02", "2025-02-28", "2025-02-03")
    b = run_backtest(service, s, "2025-01-02", "2025-02-28", "2025-02-03")
    assert a["equity"] == b["equity"] and a["metrics"] == b["metrics"]
    assert a["metrics"]["transaction_costs"] > 0
    assert a["out_of_sample"]["start"] == "2025-02-03"
    assert a["equity"][0]["SPY"] > 0 and a["orders"]
    assert not service.overview()["orders"]


def test_broker_switch_does_not_transfer_ownership(service):
    service.cycle(replay_date="2025-01-06")
    old = service.overview()["positions"]
    s = service.db.settings()
    s.broker.account = "another-local"
    service.update_settings(s.model_dump())
    assert not service.overview()["positions"]
    s.broker.account = ""
    service.update_settings(s.model_dump())
    assert service.overview()["positions"] == old


class FakeAlpaca:
    def get_account(self):
        return N(
            id="paper1",
            cash="500",
            equity="500",
            buying_power="500",
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
        )

    def get_asset(self, s):
        return N(tradable=True, status="active", fractionable=True)

    def get_clock(self):
        return N(is_open=True)

    def submit_order(self, order_data):
        self.request = order_data
        return N(
            id="sdk-order",
            status="partially_filled",
            filled_qty=".1",
            filled_avg_price="100",
            client_order_id=order_data.client_order_id,
        )


def test_alpaca_sdk_contract():
    client = FakeAlpaca()
    b = AlpacaBroker("paper", client=client)
    assert b.account().cash == 500 and b.instrument("AAPL").fractional
    report = b.submit(
        {"id": "durable123", "symbol": "AAPL", "side": "buy", "qty": 0.25}
    )
    assert report["status"] == "partially_filled" and report["filled_qty"] == 0.1
    assert client.request.qty == 0.25 and client.request.client_order_id == "durable123"
    assert client.request.time_in_force.value == "day"


def test_alpaca_market_closed():
    c = FakeAlpaca()
    c.get_clock = lambda: N(is_open=False)
    with pytest.raises(BrokerError):
        AlpacaBroker("paper", client=c).submit(
            {"id": "x", "symbol": "AAPL", "qty": 0.1, "side": "buy"}
        )


def test_protective_stop_while_paused(service):
    service.cycle(replay_date="2025-01-06")
    s = service.db.settings()
    s.risk.max_daily_loss = 0.9
    s.risk.max_drawdown = 0.9
    s.risk.max_capital_loss = 0.9
    service.update_settings(s.model_dump())
    # Drop observed prices below entry. Central stop must operate independently of upstream weights.
    l = Ledger(service.db, service.scope())
    positions = l.positions()
    b = LocalBroker(
        service.db,
        service.scope(),
        s.simulation,
        {k: p["cost"] * 0.8 for k, p in positions.items()},
    )
    prices = b.prices
    a = l.account()
    equity = a["cash"] + sum(p["qty"] * prices[k] for k, p in positions.items())
    targets = {k: p["qty"] * prices[k] / equity for k, p in positions.items()}
    orders, reasons = RiskEngine(s).plan(targets, prices, positions, a, equity, b)
    assert orders and all(o["side"] == "sell" and o["protective"] for o in orders)
    assert any("stop" in r for r in reasons)


def test_intraday_metrics_not_annualized_as_daily():
    points = [
        {"date": "2025-01-02T10:00", "equity": 101, "flow": 0},
        {"date": "2025-01-02T11:00", "equity": 102, "flow": 0},
        {"date": "2025-01-03", "equity": 103, "flow": 0},
    ]
    assert metrics(points, [], 100)["observations"] == 2


def test_newer_schema_refused(service):
    with service.db.connect() as c:
        c.execute("INSERT INTO migrations VALUES(99,'future')")
    with pytest.raises(RuntimeError, match="newer"):
        Service(service.db.path)


def test_ibkr_mode_and_normalization(monkeypatch):
    from trader.brokers import IBKRBroker

    monkeypatch.setenv("IBKR_ACCOUNT", "U123")
    with pytest.raises(BrokerError, match="DU"):
        IBKRBroker("paper", client=N())
    monkeypatch.setenv("IBKR_ACCOUNT", "DU123")
    with pytest.raises(BrokerError, match="DU"):
        IBKRBroker("live", client=N())
    fake = N(
        order=N(orderId=42, orderRef="durable"),
        orderStatus=N(status="Filled", filled=1, avgFillPrice=19),
        fills=[N(commissionReport=N(commission=1))],
    )
    r = IBKRBroker.normalize(fake)
    assert r["status"] == "filled" and r["fees"] == 1 and r["filled_qty"] == 1


def test_alpaca_rejection_and_timeout_status():
    c = FakeAlpaca()
    c.submit_order = lambda order_data: N(
        id="r",
        status="rejected",
        filled_qty="0",
        filled_avg_price=None,
        client_order_id=order_data.client_order_id,
    )
    assert (
        AlpacaBroker("paper", client=c).submit(
            {"id": "r1", "symbol": "AAPL", "side": "buy", "qty": 0.1}
        )["status"]
        == "rejected"
    )

    def timeout(order_data):
        raise TimeoutError()

    c.submit_order = timeout
    with pytest.raises(TimeoutError):
        AlpacaBroker("paper", client=c).submit(
            {"id": "t1", "symbol": "AAPL", "side": "buy", "qty": 0.1}
        )


def test_existing_holdings_reserve_slots_and_sector_capacity(service):
    s = service.db.settings()
    s.risk.max_holdings = 1
    b = LocalBroker(service.db, service.scope(), s.simulation, {"AAPL": 10, "MSFT": 10})
    a = Ledger(service.db, service.scope()).account()
    positions = {"AAPL": {"qty": 5, "cost": 10, "peak": 10}}
    orders, reasons = RiskEngine(s).plan({"MSFT": 0.2}, b.prices, positions, a, 500, b)
    assert not any(o["side"] == "buy" for o in orders)
    assert any("slot" in reason for reason in reasons)
