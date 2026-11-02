"""Walk-forward signals from t-1 close, fills at t open, valuation at t close."""

import tempfile
from pathlib import Path
import hashlib
import pandas as pd
from .db import DB, dumps, now
from .data import REQUIRED, aligned
from .ledger import Ledger, LocalBroker
from .risk import RiskEngine
from .strategies import StrategyEngine
from .metrics import metrics


def run_backtest(service, settings, start, end, oos_start=None):
    if pd.Timestamp(start) >= pd.Timestamp(end):
        raise ValueError("Start must precede end")
    data = service.data.load(settings.strategy.universe + REQUIRED, through=end)
    dates = aligned(data)
    sessions = [d for d in dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    if not sessions or dates.get_loc(sessions[0]) < 130:
        raise ValueError("Require 130 warmup sessions before test start")
    if oos_start and not pd.Timestamp(start) < pd.Timestamp(oos_start) <= pd.Timestamp(
        end
    ):
        raise ValueError("OOS boundary must be inside test interval")
    with tempfile.TemporaryDirectory() as tmp:
        db = DB(Path(tmp) / "test.db")
        scope = "backtest"
        db.ensure_account(scope, settings.capital.allocated)
        ledger = Ledger(db, scope)
        strategy = StrategyEngine(settings.strategy)
        risk = RiskEngine(settings)
        previous_period = None
        decisions = []
        halt = False
        for date in sessions:
            signal_date = dates[dates.get_loc(date) - 1]
            prices = {s: float(df.loc[date, "open"]) for s, df in data.items()}
            closes = {s: float(df.loc[date, "close"]) for s, df in data.items()}
            b = LocalBroker(db, scope, settings.simulation, prices)
            a = ledger.account()
            pos = ledger.positions()
            value = a["cash"] + sum(p["qty"] * prices[s] for s, p in pos.items())
            points = db.rows("SELECT * FROM equity ORDER BY date")
            day_start = points[-1]["equity"] if points else a["initial"]
            trigger = risk.loss_trigger(value, a, day_start)
            if trigger:
                halt = True
            period = (
                str(signal_date.date())
                if settings.strategy.rebalance == "daily"
                else (
                    signal_date.strftime("%Y-%m")
                    if settings.strategy.rebalance == "monthly"
                    else str(signal_date.to_period("W"))
                )
            )
            if not halt and period != previous_period:
                raw, audit = strategy.targets(data, signal_date)
                weights, reasons = risk.weights(raw, data, signal_date)
                previous_period = period
                decisions.append(
                    {
                        "signal_date": str(signal_date.date()),
                        "raw": raw,
                        "permitted": weights,
                        "risk": reasons,
                    }
                )
            else:
                weights = {s: p["qty"] * prices[s] / value for s, p in pos.items()}
                reasons = []
            liquidate = halt and settings.risk.loss_action == "liquidate"
            orders, blocked = risk.plan(
                weights, prices, pos, a, value, b, protect=liquidate
            )
            if halt and not liquidate:
                orders = []
            # Before a scheduled rebalance, only protective stops can change holdings.
            if not decisions or decisions[-1]["signal_date"] != str(signal_date.date()):
                orders = [o for o in orders if o["protective"]]
            for i, o in enumerate(orders):
                oid = hashlib.sha256(f"{date}|{i}".encode()).hexdigest()
                risk.final(
                    o,
                    b,
                    ledger.positions(),
                    ledger.account()["cash"],
                    prices[o["symbol"]],
                    equity=value,
                    price_map=prices,
                )
                with db.connect() as c:
                    c.execute(
                        "INSERT INTO orders(id,scope,cycle,created,symbol,side,qty,intended,status,strategy,reason,risk) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            oid,
                            scope,
                            str(date),
                            str(date.date()),
                            o["symbol"],
                            o["side"],
                            o["qty"],
                            o["intended"],
                            "prepared",
                            settings.strategy.name,
                            "protective stop" if o["protective"] else "rebalance",
                            dumps(reasons + blocked),
                        ),
                    )
                b.submit({**o, "id": oid})
                # Partial simulated fills remain pending until next day's cancellation.
                if settings.simulation.fill_fraction < 1:
                    b.cancel(oid)
            ledger.mark(closes, str(date.date()))
        points = db.rows("SELECT * FROM equity ORDER BY date")
        orders = db.rows("SELECT * FROM orders ORDER BY created,id")
        for point in points:
            date = pd.Timestamp(point["date"])
            for sym in ["SPY", "QQQ"]:
                # Consistent adjusted basis and starting capital; benchmark entry costs included.
                entry = float(data[sym].loc[sessions[0], "open"])
                commission = settings.simulation.commission_fixed
                cost = (
                    1
                    + (
                        settings.simulation.slippage_bps
                        + settings.simulation.spread_bps / 2
                        + settings.simulation.commission_bps
                    )
                    / 10000
                )
                qty = (settings.capital.allocated - commission) / entry / cost
                point[sym] = qty * float(data[sym].loc[date, "close"])
        result = {
            "mode": "historical backtest",
            "start": start,
            "end": end,
            "initial": settings.capital.allocated,
            "equity": points,
            "orders": orders,
            "decisions": decisions,
            "metrics": metrics(points, orders, settings.capital.allocated),
            "halted": halt,
            "assumptions": [
                "Historical adjusted OHLC basis (vendor split/dividend factors); fractional research units. Not executable real-time prices.",
                "Signals use only prior completed bars; next-session open + configured spread/slippage.",
                "Fixed present-day universe: selection/survivorship bias; vendor history is not certified as vintage point-in-time.",
                "Daily close/open monitoring; intraday gaps, market impact and actual broker fees can differ.",
                "Cash constraints, stops, sizing and commissions use the same operational modules.",
                "SPY/QQQ are fully invested buy-and-hold with entry costs; strategy may retain cash.",
                "No parameter search on out-of-sample interval; deterministic strategy is evaluated sequentially.",
            ],
            "data_hash": hashlib.sha256(
                "".join(df.to_csv() for _, df in sorted(data.items())).encode()
            ).hexdigest(),
        }
        if oos_start:
            selected = [p for p in points if p["date"] >= oos_start]
            prior = [p for p in points if p["date"] < oos_start]
            result["out_of_sample"] = {
                "start": oos_start,
                "metrics": metrics(
                    selected,
                    [o for o in orders if o["created"] >= oos_start],
                    prior[-1]["equity"] if prior else settings.capital.allocated,
                ),
            }
        with service.db.connect() as c:
            row = c.execute(
                "INSERT INTO research(created,kind,config,result) VALUES(?,?,?,?)",
                (now(), "backtest", dumps(settings.model_dump()), dumps(result)),
            )
            result["id"] = row.lastrowid
        return result
