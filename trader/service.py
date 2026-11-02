import hashlib
import json
import threading
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import pandas as pd
from .config import Settings
from .db import DB, now, dumps
from .data import MarketData, REQUIRED, aligned, DataError
from .strategies import StrategyEngine
from .risk import RiskEngine, RiskBlocked
from .ledger import Ledger, LocalBroker
from .brokers import create_broker
from .metrics import metrics

ACTIVE_SQL = "status NOT IN ('filled','canceled','rejected','expired','done_for_day')"


class Service:
    def __init__(self, path):
        self.db = DB(path)
        self.data = MarketData(Path(path).parent / "market")
        self.lock = threading.RLock()
        self.db.ensure_account(self.scope(), self.db.settings().capital.allocated)

    @contextmanager
    def exclusive(self):
        # One process owns all mutations, including UI vs scheduler. OS releases on crash.
        from filelock import FileLock, Timeout

        with self.lock:
            try:
                with FileLock(self.db.path + ".lock", timeout=1):
                    yield
            except Timeout:
                raise RiskBlocked("Another operation holds the trading lock") from None

    def scope(self, s=None):
        s = s or self.db.settings()
        return f"{s.broker.broker}:{s.broker.mode}:{s.broker.account or 'default'}"

    def update_settings(self, settings):
        s = Settings.model_validate(settings)
        if s.broker.broker != "local" and s.capital.include_deposits:
            raise RiskBlocked(
                "Automatic external deposits require verified broker cash-flow feed; use explicit allocation changes"
            )
        if s.strategy.name == "rolling_ml":
            raise RiskBlocked(
                "Rolling ML is research-only until data provenance is verified"
            )
        with self.exclusive():
            old = self.db.settings()
            old_scope = self.scope(old)
            new_scope = self.scope(s)
            active = self.db.rows(
                f"SELECT id FROM orders WHERE scope=? AND {ACTIVE_SQL}", (old_scope,)
            )
            critical = (
                old.broker != s.broker
                or old.strategy != s.strategy
                or old.capital != s.capital
            )
            if critical and active:
                raise RiskBlocked(
                    "Reconcile/cancel pending orders before changing broker, capital or strategy"
                )
            if critical:
                self.db.set_state("automation", False)
                self.db.set_state("live_activation", None)
            self.db.ensure_account(new_scope, s.capital.allocated)
            if old_scope == new_scope and old.capital.allocated != s.capital.allocated:
                delta = s.capital.allocated - old.capital.allocated
                ledger = Ledger(self.db, new_scope)
                a = ledger.account()
                if a["cash"] + delta < 0:
                    raise RiskBlocked(
                        "Reduce positions before withdrawing allocated cash"
                    )
                if s.broker.broker != "local":
                    b = self.external(s)
                    self.reconcile(b, new_scope)
                    if a["cash"] + delta > b.account().cash:
                        raise RiskBlocked(
                            "Insufficient account cash for new allocation"
                        )
                with self.db.connect() as c:
                    c.execute(
                        "UPDATE accounts SET cash=cash+?,contributions=contributions+?,peak=peak+? WHERE scope=?",
                        (delta, delta, delta, new_scope),
                    )

                self.db.event(
                    new_scope,
                    "capital_flow",
                    {
                        "amount": delta,
                        "note": "Allocation change, excluded from time-weighted returns",
                    },
                )
                self.db.set_state(
                    "pending_flow:" + new_scope,
                    self.db.state("pending_flow:" + new_scope, 0) + delta,
                )
            with self.db.connect() as c:
                c.execute(
                    "INSERT INTO settings(created,body) VALUES(?,?)",
                    (now(), dumps(s.model_dump())),
                )
            self.db.event(
                new_scope,
                "settings_version",
                {"settings": s.model_dump(), "automation_stopped": critical},
            )
        return s

    def external(self, s):
        if not s.broker.dedicated_account:
            raise RiskBlocked(
                "Dedicated account required: shared ownership isolation is not guaranteed"
            )
        if not s.broker.account:
            raise RiskBlocked("Explicit account identifier required")
        b = create_broker(s.broker)
        a = b.account()
        if a.id != s.broker.account:
            raise RiskBlocked("Broker account identity does not match selected account")
        if a.blocked:
            raise RiskBlocked("Account trading restricted")
        if s.broker.mode == "live" and self.db.state(
            "live_activation"
        ) != self.activation_fingerprint(s):
            raise RiskBlocked("Live disabled: explicit activation required")
        return b

    def activation_fingerprint(self, s):
        return hashlib.sha256(dumps(s.broker.model_dump()).encode()).hexdigest()

    def activate_live(self, phrase):
        s = self.db.settings()
        if phrase != "ENABLE LIVE TRADING" or s.broker.mode != "live":
            raise RiskBlocked("Select live and type ENABLE LIVE TRADING")
        if not s.broker.dedicated_account:
            raise RiskBlocked("Dedicated account required")
        # Read-only credential/account check before activating; no orders here.
        b = create_broker(s.broker)
        a = b.account()
        if a.id != s.broker.account or a.blocked:
            raise RiskBlocked("Broker identity/restrictions validation failed")
        with self.exclusive():
            self.reconcile(b, self.scope(s))
            self.db.set_state("live_activation", self.activation_fingerprint(s))
            self.db.event(self.scope(s), "live_activated", {"account": a.id})

    def reconcile(self, b, scope):
        ledger = Ledger(self.db, scope)
        a = ledger.account()
        # Reconcile uncertain/partial orders before checking holdings. Never auto-resubmit.
        pending = self.db.rows(
            f"SELECT * FROM orders WHERE scope=? AND {ACTIVE_SQL}", (scope,)
        )
        for o in pending:
            report = b.inspect(o["id"])
            if report is None:
                self.db.event(
                    scope,
                    "ambiguous_order",
                    {"id": o["id"], "action": "Fail closed; never resubmit"},
                )
                raise RiskBlocked("Unresolved order: inspect broker before recovery")
            ledger.apply(o["id"], report)
        actual = b.positions()
        owned = {s: p["qty"] for s, p in ledger.positions().items()}
        if any(
            abs(actual.get(s, 0) - owned.get(s, 0)) > 1e-5
            for s in set(actual) | set(owned)
        ):
            raise RiskBlocked(
                "Position mismatch: dedicated account contains unowned or missing holdings"
            )
        broker_ids = {o.get("client_id") or o.get("id") for o in b.open_orders()}
        local_ids = {
            o["id"]
            for o in self.db.rows(
                f"SELECT * FROM orders WHERE scope=? AND {ACTIVE_SQL}", (scope,)
            )
        }
        if broker_ids - local_ids:
            raise RiskBlocked("Unowned open orders in dedicated account")
        ba = b.account()
        if ba.cash < ledger.account()["cash"] - 0.05:
            raise RiskBlocked(
                "Cash mismatch: bot ledger exceeds available broker cash (fees/withdrawal?)"
            )
        if a["broker_id"] and a["broker_id"] != ba.id:
            raise RiskBlocked("Account binding mismatch")
        if not a["broker_id"]:
            budget = self.db.settings().capital
            allocated = (
                budget.allocated
                if budget.method == "fixed"
                else min(budget.allocated, ba.equity * budget.equity_percent)
            )
            if allocated > ba.cash:
                raise RiskBlocked("Allocated budget exceeds available cash")
            with self.db.connect() as c:
                c.execute(
                    "UPDATE accounts SET cash=?,initial=?,contributions=?,peak=?,baseline_equity=?,broker_id=? WHERE scope=?",
                    (
                        allocated,
                        allocated,
                        allocated,
                        allocated,
                        ba.equity,
                        ba.id,
                        scope,
                    ),
                )
        return not bool(local_ids)

    def cycle(
        self,
        dry_run=False,
        replay_date=None,
        scheduled=False,
        protect_only=False,
        monitor_bucket=None,
        liquidate=False,
    ):
        with self.exclusive():
            s = self.db.settings()
            scope = self.scope(s)
            if self.db.state("kill", False):
                raise RiskBlocked("Kill switch enabled")
            if self.db.state("failures", 0) >= s.risk.failure_limit:
                raise RiskBlocked(
                    "API failure circuit breaker: reset after investigation"
                )
            if s.broker.broker != "local" and replay_date:
                raise RiskBlocked("Historical replay can only execute locally")
            if scheduled and s.broker.broker == "local":
                if s.data.provider == "cache":
                    raise RiskBlocked(
                        "Local automation requires current data; use historical replay manually or switch data provider to yahoo"
                    )
            if s.data.provider == "yahoo" and not replay_date:
                self.data.refresh(
                    s.strategy.universe + REQUIRED, s.data.timeout_seconds
                )
            data = self.data.load(s.strategy.universe + REQUIRED, through=replay_date)
            dates = aligned(data)
            if replay_date:
                execution = pd.Timestamp(replay_date)
                if execution not in dates:
                    raise DataError("Replay date must be a common trading session")
                idx = dates.get_loc(execution)
                if idx < 130:
                    raise DataError("Insufficient warmup history")
                signal_date = dates[idx - 1]
                prices = {
                    sym: float(df.loc[execution, "open"]) for sym, df in data.items()
                }
                valuation_date = execution.strftime("%Y-%m-%d")
            else:
                signal_date = dates[-1]
                age = (
                    pd.Timestamp.now(tz="UTC") - signal_date.tz_localize("UTC")
                ).total_seconds() / 3600
                if age > s.data.max_age_hours:
                    raise DataError(
                        "Market data stale; refresh real bars or specify a historical local replay date"
                    )
                prices = {sym: float(df.close.iloc[-1]) for sym, df in data.items()}
                valuation_date = now()
            previous = self.db.rows(
                "SELECT date FROM equity WHERE scope=? ORDER BY date DESC LIMIT 1",
                (scope,),
            )
            if (
                replay_date
                and previous
                and pd.Timestamp(previous[0]["date"]) >= pd.Timestamp(replay_date)
                and not liquidate
            ):
                key = hashlib.sha256(
                    f"{scope}|{replay_date}|rebalance".encode()
                ).hexdigest()[:32]
                old = self.db.rows("SELECT result FROM cycles WHERE id=?", (key,))
                if old:
                    return json.loads(old[0]["result"])
                raise RiskBlocked("Replay must advance chronologically")
            key = hashlib.sha256(
                f"{scope}|{replay_date or datetime.now(timezone.utc).date()}|{'liquidate' if liquidate else (monitor_bucket if scheduled else 'rebalance')}".encode()
            ).hexdigest()[:32]
            if not dry_run:
                old = self.db.rows("SELECT * FROM cycles WHERE id=?", (key,))
                if old:
                    if old[0]["status"] == "complete":
                        return json.loads(old[0]["result"])
                    if s.broker.broker != "local":
                        self.reconcile(self.external(s), scope)
                    raise RiskBlocked(
                        "Interrupted cycle reconciled; no automatic resubmission"
                    )
            try:
                return self._cycle(
                    s,
                    scope,
                    data,
                    signal_date,
                    prices,
                    valuation_date,
                    key,
                    dry_run,
                    protect_only,
                    liquidate,
                    replay_date,
                    scheduled,
                )
            except Exception as exc:
                self.db.event(
                    scope,
                    "blocked",
                    {
                        "cycle": key,
                        "reason": str(exc)
                        if isinstance(exc, (RiskBlocked, DataError))
                        else type(exc).__name__,
                    },
                )
                if not isinstance(exc, (RiskBlocked, DataError, ValueError)):
                    self.db.set_state("failures", self.db.state("failures", 0) + 1)
                raise

    def _cycle(
        self,
        s,
        scope,
        data,
        signal_date,
        prices,
        date,
        key,
        dry,
        protect,
        liquidate,
        replay,
        scheduled,
    ):
        self.db.ensure_account(scope, s.capital.allocated)
        ledger = Ledger(self.db, scope)
        b = (
            LocalBroker(self.db, scope, s.simulation, prices)
            if s.broker.broker == "local"
            else self.external(s)
        )
        if not self.reconcile(b, scope):
            raise RiskBlocked(
                "Pending orders: wait for fills/cancellation before planning"
            )
        if s.broker.broker != "local":
            for sym in set(s.strategy.universe) | set(ledger.positions()):
                price, stamp = b.quote(sym)
                if (
                    pd.Timestamp.now(tz="UTC") - pd.Timestamp(stamp)
                ).total_seconds() > 90:
                    raise RiskBlocked("Broker quote stale")
                prices[sym] = price
        a = ledger.account()
        positions = ledger.positions()
        value = a["cash"] + sum(p["qty"] * prices[sym] for sym, p in positions.items())
        points = self.db.rows(
            "SELECT * FROM equity WHERE scope=? ORDER BY date", (scope,)
        )
        day = str(date)[:10]
        prior = [p for p in points if p["date"][:10] < day]
        day_start = prior[-1]["equity"] if prior else a["initial"]
        risk = RiskEngine(s)
        trigger = risk.loss_trigger(value, a, day_start)
        halt = self.db.state("loss_halt:" + scope)
        if halt and not liquidate:
            raise RiskBlocked(f"Loss halt latched: {halt}")
        if trigger:
            self.db.set_state("loss_halt:" + scope, trigger)
            self.db.event(
                scope,
                "portfolio_loss",
                {"reason": trigger, "action": s.risk.loss_action},
            )
            if s.risk.loss_action == "halt" and not liquidate:
                raise RiskBlocked(trigger)
            protect = True
            liquidate = True
        # Rebalance only once per intended strategy period. Stops run daily/each monitor.
        period = (
            str(signal_date.date())
            if s.strategy.rebalance == "daily"
            else (
                signal_date.strftime("%Y-%m")
                if s.strategy.rebalance == "monthly"
                else str(signal_date.to_period("W"))
            )
        )
        last_period = self.db.state("rebalance:" + scope)
        protective_only = protect or (scheduled and last_period == period)
        if liquidate:
            raw = {}
            audit = {"reason": "Emergency/protective liquidation"}
        elif protective_only:
            raw = {sym: p["qty"] * prices[sym] / value for sym, p in positions.items()}
            audit = {"reason": "Monitor stops; no new allocation"}
        else:
            raw, audit = StrategyEngine(s.strategy).targets(data, signal_date)
        weights, notes = risk.weights(raw, data, signal_date)
        if protective_only and not liquidate:
            weights = raw
        count = self.db.rows(
            "SELECT count(*) n FROM orders WHERE scope=? AND substr(created,1,10)=?",
            (scope, day),
        )[0]["n"]
        orders, blocked = risk.plan(
            weights, prices, positions, a, value, b, count, protect=liquidate
        )
        if protective_only and not liquidate:
            orders = [o for o in orders if o["protective"] and o["side"] == "sell"]
        result = {
            "cycle": key,
            "scope": scope,
            "signal_date": str(signal_date.date()),
            "date": date,
            "raw_targets": raw,
            "permitted_targets": weights,
            "orders": orders,
            "blocked_reasons": notes + blocked,
            "dry_run": dry,
            "strategy_audit": audit,
        }
        self.db.event(scope, "decision", result)
        if dry:
            return result
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO cycles VALUES(?,?,?,?,?)",
                (key, scope, now(), "running", dumps(result)),
            )
        for i, o in enumerate(orders):
            if self.db.state("kill", False):
                raise RiskBlocked("Kill switch activated")
            price = prices[o["symbol"]]
            if s.broker.broker != "local":
                price, stamp = b.quote(o["symbol"])
                if (
                    pd.Timestamp.now(tz="UTC") - pd.Timestamp(stamp)
                ).total_seconds() > 90:
                    raise RiskBlocked("Final quote stale")
            risk.final(
                o,
                b,
                ledger.positions(),
                ledger.account()["cash"],
                price,
                equity=value,
                price_map=prices,
            )
            oid = (
                "fx"
                + hashlib.sha256(
                    f"{key}|{i}|{o['symbol']}|{o['side']}".encode()
                ).hexdigest()[:42]
            )
            o.update(id=oid, scope=scope, cycle=key, strategy=s.strategy.name)
            with self.db.connect() as c:
                c.execute(
                    "INSERT INTO orders(id,scope,cycle,created,symbol,side,qty,intended,status,strategy,reason,risk) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        oid,
                        scope,
                        key,
                        date,
                        o["symbol"],
                        o["side"],
                        o["qty"],
                        o["intended"],
                        "prepared",
                        s.strategy.name,
                        "protective reduction"
                        if o["protective"]
                        else "FinRL-X rebalance",
                        dumps({"passed": True, "notes": notes + blocked}),
                    ),
                )
            # Persist intent before outbound call; an exception leaves an ambiguous row, never a blind retry.
            report = b.submit(o)
            if s.broker.broker != "local":
                ledger.apply(oid, report)
            self.db.event(scope, "broker_report", {"order": oid, "report": report})
        flow = self.db.state("pending_flow:" + scope, 0)
        result["equity"] = ledger.mark(prices, date, flow)
        self.db.set_state("pending_flow:" + scope, 0)
        self.db.set_state("marks:" + scope, prices)
        result["fills"] = self.db.rows("SELECT * FROM orders WHERE cycle=?", (key,))
        with self.db.connect() as c:
            c.execute(
                "UPDATE cycles SET status='complete',result=? WHERE id=?",
                (dumps(result), key),
            )
        if not protective_only:
            self.db.set_state("rebalance:" + scope, period)
        self.db.set_state("last_success", now())
        self.db.set_state("failures", 0)
        return result

    def control(self, action):
        # Kill flag is visible between individual submissions, even if cycle lock is held.
        scope = self.scope()
        if action == "kill":
            self.db.set_state("kill", True)
            self.db.set_state("automation", False)
            return {
                "kill": True,
                "note": "New submissions stopped; cancel open orders separately. Fills already in flight may still occur.",
            }
        with self.exclusive():
            if action in ("start", "resume"):
                if self.db.state("kill", False):
                    raise RiskBlocked("Reset kill switch before starting")
                self.db.set_state("automation", True)
                self.db.set_state("paused", False)
            elif action == "pause":
                self.db.set_state("paused", True)
            elif action == "stop":
                self.db.set_state("automation", False)
            elif action == "reset":
                self.db.set_state("kill", False)
                self.db.set_state("failures", 0)
            elif action == "acknowledge_loss":
                self.db.set_state("loss_halt:" + scope, None)
            elif action == "cancel":
                s = self.db.settings()
                b = (
                    LocalBroker(self.db, scope, s.simulation, {})
                    if s.broker.broker == "local"
                    else self.external(s)
                )
                for o in self.db.rows(
                    f"SELECT * FROM orders WHERE scope=? AND {ACTIVE_SQL}", (scope,)
                ):
                    report = b.inspect(o["id"])
                    if report and s.broker.broker != "local":
                        Ledger(self.db, scope).apply(o["id"], report)
                    bid = (report or {}).get("broker_id") or o["broker_id"]
                    if bid:
                        b.cancel(bid)
            else:
                raise ValueError("Unknown control")
            self.db.event(scope, "control", {"action": action})
        return {
            "action": action,
            "automation": self.db.state("automation", False),
            "paused": self.db.state("paused", False),
        }

    def overview(self):
        s = self.db.settings()
        scope = self.scope()
        self.db.ensure_account(scope, s.capital.allocated)
        ledger = Ledger(self.db, scope)
        a = ledger.account()
        points = self.db.rows(
            "SELECT * FROM equity WHERE scope=? ORDER BY date", (scope,)
        )
        orders = self.db.rows(
            "SELECT * FROM orders WHERE scope=? ORDER BY created DESC", (scope,)
        )
        pos = ledger.positions()
        marks = self.db.state("marks:" + scope, {})
        value = a["cash"] + sum(
            p["qty"] * marks.get(sym, p["cost"]) for sym, p in pos.items()
        )
        # Benchmarks are comparison series, never merged into the bot's returns.
        if points:
            for symbol in ["SPY", "QQQ"]:
                try:
                    bars = self.data.load([symbol])[symbol]
                    entry = bars.loc[points[0]["date"][:10], "open"]
                    for point in points:
                        eligible = bars.loc[: point["date"][:10]]
                        point[symbol] = (
                            a["initial"] * float(eligible.close.iloc[-1] / entry)
                            if len(eligible)
                            else None
                        )
                except (DataError, KeyError, IndexError):
                    pass
        realized = sum(o["realized"] for o in orders)
        enriched = []
        for sym, p in pos.items():
            try:
                price = self.db.state("marks:" + scope, {}).get(sym)
            except (ValueError, IndexError):
                price = None
            enriched.append(
                {
                    **p,
                    "price": price,
                    "market_value": p["qty"] * price if price else None,
                    "unrealized": p["qty"] * (price - p["cost"]) if price else None,
                }
            )
        return {
            "scope": scope,
            "mode": s.broker.mode,
            "broker": s.broker.broker,
            "account": a,
            "equity": value,
            "pnl": value - a["contributions"],
            "pnl_percent": (value / a["contributions"] - 1)
            if a["contributions"]
            else 0,
            "realized": realized,
            "unrealized": value - a["contributions"] - realized,
            "positions": enriched,
            "orders": orders,
            "equity_history": points,
            "metrics": metrics(points, orders, a["initial"]),
            "automation": self.db.state("automation", False),
            "paused": self.db.state("paused", False),
            "kill": self.db.state("kill", False),
            "loss_halt": self.db.state("loss_halt:" + scope),
            "last_success": self.db.state("last_success"),
            "next_operation": self.db.state("next_operation"),
            "live_activated": s.broker.mode == "live"
            and self.db.state("live_activation") == self.activation_fingerprint(s),
            "connection": self.db.state(
                "connection:" + scope,
                {
                    "status": "local ready"
                    if s.broker.broker == "local"
                    else "not tested"
                },
            ),
        }
