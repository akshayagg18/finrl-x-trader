import math
from .db import now
from .brokers import Account, Instrument, BrokerError
from .data import ALLOWED


class Ledger:
    def __init__(self, db, scope):
        self.db, self.scope = db, scope

    def account(self):
        return self.db.rows("SELECT * FROM accounts WHERE scope=?", (self.scope,))[0]

    def positions(self):
        return {
            p["symbol"]: p
            for p in self.db.rows(
                "SELECT * FROM positions WHERE scope=? AND qty>0.00000001",
                (self.scope,),
            )
        }

    def apply(self, order_id, fill):
        """Cumulative broker fill -> incremental ownership. Atomic, restart idempotent."""
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            o = dict(
                c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            )
            qty = float(fill.get("filled_qty", 0))
            price = float(fill.get("fill_price") or 0)
            fees = float(fill.get("fees", 0))
            if (
                not all(math.isfinite(v) for v in (qty, price, fees))
                or qty < o["filled_qty"] - 1e-8
                or qty > o["qty"] + 1e-6
            ):
                raise BrokerError("Invalid cumulative fill quantity")
            delta = qty - o["filled_qty"]
            fee_delta = fees - o["fees"]
            realized = o["realized"]
            if delta > 1e-9:
                if price <= 0:
                    raise BrokerError("Fill price absent")
                # Cumulative average price may change with partial fills.
                value = qty * price - o["filled_qty"] * (o["fill_price"] or 0)
                row = c.execute(
                    "SELECT * FROM positions WHERE scope=? AND symbol=?",
                    (o["scope"], o["symbol"]),
                ).fetchone()
                p = dict(row) if row else {"qty": 0, "cost": 0, "peak": price}
                if o["side"] == "buy":
                    total = p["qty"] + delta
                    cost = (p["qty"] * p["cost"] + value + fee_delta) / total
                    cash_delta = -value - fee_delta
                else:
                    if delta > p["qty"] + 1e-6:
                        raise BrokerError("Cannot sell unowned shares")
                    total = max(0, p["qty"] - delta)
                    cost = p["cost"]
                    cash_delta = value - fee_delta
                    realized += value - delta * p["cost"] - fee_delta
                c.execute(
                    "INSERT OR REPLACE INTO positions VALUES(?,?,?,?,?)",
                    (o["scope"], o["symbol"], total, cost, max(p["peak"], price)),
                )
                c.execute(
                    "UPDATE accounts SET cash=cash+? WHERE scope=?",
                    (cash_delta, o["scope"]),
                )
            elif abs(fee_delta) > 1e-9:
                c.execute(
                    "UPDATE accounts SET cash=cash-? WHERE scope=?",
                    (fee_delta, o["scope"]),
                )
                if o["side"] == "sell":
                    realized -= fee_delta
            c.execute(
                "UPDATE orders SET status=?,broker_id=?,filled_qty=?,fill_price=?,fees=?,realized=? WHERE id=?",
                (
                    fill["status"],
                    fill.get("broker_id"),
                    qty,
                    price or None,
                    fees,
                    realized,
                    order_id,
                ),
            )

    def mark(self, prices, date, flow=0):
        positions = self.positions()
        if any(
            s not in prices or not math.isfinite(prices[s]) or prices[s] <= 0
            for s in positions
        ):
            raise ValueError("Missing price for owned position")
        a = self.account()
        value = a["cash"] + sum(p["qty"] * prices[s] for s, p in positions.items())
        with self.db.connect() as c:
            c.execute(
                "UPDATE accounts SET peak=MAX(peak,?) WHERE scope=?",
                (value, self.scope),
            )
            for s, p in positions.items():
                c.execute(
                    "UPDATE positions SET peak=MAX(peak,?) WHERE scope=? AND symbol=?",
                    (prices[s], self.scope, s),
                )
            c.execute(
                "INSERT INTO equity(scope,date,equity,cash,flow) VALUES(?,?,?,?,?) ON CONFLICT(scope,date) DO UPDATE SET equity=excluded.equity,cash=excluded.cash,flow=equity.flow+excluded.flow",
                (self.scope, date, value, a["cash"], flow),
            )
        return value


class LocalBroker:
    def __init__(self, db, scope, settings, prices):
        self.db, self.scope, self.settings, self.prices = db, scope, settings, prices
        self.ledger = Ledger(db, scope)

    def account(self):
        a = self.ledger.account()
        equity = a["cash"] + sum(
            p["qty"] * self.prices[s] for s, p in self.ledger.positions().items()
        )
        return Account(self.scope, a["cash"], equity, a["cash"])

    def positions(self):
        return {s: p["qty"] for s, p in self.ledger.positions().items()}

    def open_orders(self):
        return self.db.rows(
            "SELECT * FROM orders WHERE scope=? AND status NOT IN ('filled','rejected','canceled','expired','done_for_day')",
            (self.scope,),
        )

    def instrument(self, symbol):
        return Instrument(symbol, symbol in ALLOWED, True)

    def market_open(self):
        return True

    def quote(self, symbol):
        return self.prices[symbol], now()

    def inspect(self, client_id):
        r = self.db.rows(
            "SELECT * FROM orders WHERE id=? AND scope=?", (client_id, self.scope)
        )
        return r[0] if r else None

    def submit(self, order):
        # Durable local row already exists. Replay never fills it twice.
        old = self.inspect(order["id"])
        if old and old["status"] != "prepared":
            return old
        price = self.prices[order["symbol"]] * (
            1
            + (1 if order["side"] == "buy" else -1)
            * (self.settings.slippage_bps + self.settings.spread_bps / 2)
            / 10000
        )
        qty = order["qty"] * self.settings.fill_fraction
        fee = (
            self.settings.commission_fixed
            + qty * price * self.settings.commission_bps / 10000
        )
        positions = self.positions()
        a = self.account()
        rejected = (order["side"] == "buy" and qty * price + fee > a.cash + 1e-7) or (
            order["side"] == "sell" and qty > positions.get(order["symbol"], 0) + 1e-7
        )
        fill = {
            "broker_id": order["id"],
            "status": "rejected"
            if rejected
            else ("filled" if self.settings.fill_fraction == 1 else "partially_filled"),
            "filled_qty": 0 if rejected else qty,
            "fill_price": 0 if rejected else price,
            "fees": 0 if rejected else fee,
        }
        self.ledger.apply(order["id"], fill)
        return fill

    def cancel(self, broker_id):
        with self.db.connect() as c:
            c.execute(
                "UPDATE orders SET status='canceled' WHERE id=? AND scope=? AND status NOT IN ('filled','rejected')",
                (broker_id, self.scope),
            )
