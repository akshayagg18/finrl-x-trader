"""Independent portfolio and final-order constraints; shared by all modes."""

import math
import numpy as np
from .data import SECTORS, ALLOWED
from .brokers import qty_round


class RiskBlocked(ValueError):
    pass


class RiskEngine:
    def __init__(self, settings):
        self.s = settings

    def weights(self, raw, data, asof):
        if (
            any(not math.isfinite(float(w)) or w < 0 for w in raw.values())
            or sum(raw.values()) > 1.000001
        ):
            raise RiskBlocked("Invalid strategy weights / short or leveraged portfolio")
        s = self.s
        result = {}
        sector = {}
        reasons = []
        for sym, w in sorted(raw.items(), key=lambda x: (-x[1], x[0])):
            if w <= 0:
                continue
            if sym not in s.strategy.universe or sym not in ALLOWED:
                reasons.append(f"{sym}: instrument ineligible")
                continue
            if len(result) >= s.risk.max_holdings:
                reasons.append(f"{sym}: maximum holdings")
                continue
            if sym not in data:
                raise RiskBlocked(f"{sym}: price history missing")
            returns = data[sym].loc[:asof, "close"].pct_change().dropna().tail(20)
            if len(returns) < 20:
                raise RiskBlocked(f"{sym}: insufficient volatility history")
            vol = float(returns.std(ddof=1) * np.sqrt(252))
            if not math.isfinite(vol) or vol > s.risk.max_volatility:
                reasons.append(f"{sym}: excessive volatility")
                continue
            scaled = w * min(1, s.risk.volatility_target / max(vol, 1e-9))
            sec = SECTORS.get(sym, "Unknown")
            allowed = min(
                scaled,
                s.risk.max_position,
                max(0, s.risk.max_sector - sector.get(sec, 0)),
            )
            if allowed < w:
                reasons.append(f"{sym}: position/sector/volatility cap")
            if allowed > 0:
                result[sym] = allowed
                sector[sec] = sector.get(sec, 0) + allowed
        cap = min(s.capital.deployment, 1 - s.capital.cash_reserve)
        scale = min(1, cap / max(sum(result.values()), 1e-12))
        return {k: v * scale for k, v in result.items()}, reasons

    def loss_trigger(self, value, account, day_start):
        r = self.s.risk
        if value <= day_start * (1 - r.max_daily_loss):
            return "Maximum daily loss"
        if value <= account["peak"] * (1 - r.max_drawdown):
            return "Maximum drawdown"
        if value <= account["contributions"] * (1 - r.max_capital_loss):
            return "Maximum capital loss"
        return None

    def plan(
        self,
        weights,
        prices,
        positions,
        account,
        equity,
        broker,
        orders_today=0,
        protect=False,
        forced=None,
    ):
        s = self.s
        cash = min(account["cash"], broker.account().cash)
        reserve = equity * s.capital.cash_reserve
        # Profits can grow the allocation, account cash outside this ledger cannot.
        base = (
            min(equity, account["contributions"])
            if not s.capital.reinvest_profits
            else equity
        )
        targets = {sym: w * base for sym, w in weights.items()}
        forced = set(forced or [])
        changes = []
        reasons = []
        for sym in sorted(set(targets) | set(positions)):
            if sym not in prices or not math.isfinite(prices[sym]) or prices[sym] <= 0:
                raise RiskBlocked(f"{sym}: missing/invalid price")
            p = positions.get(sym, {"qty": 0, "cost": 0, "peak": 0})
            price = prices[sym]
            stop = p["qty"] > 0 and (
                price <= p["cost"] * (1 - s.risk.stop_loss)
                or (
                    s.risk.trailing_stop is not None
                    and price <= p["peak"] * (1 - s.risk.trailing_stop)
                )
            )
            if stop:
                forced.add(sym)
                reasons.append(f"{sym}: protective stop triggered")
            target = 0 if sym in forced or protect else targets.get(sym, 0)
            diff = target - p["qty"] * price
            if abs(diff) < s.capital.min_order:
                continue
            instrument = broker.instrument(sym)
            if not instrument.tradable:
                raise RiskBlocked(f"{sym}: broker instrument restricted")
            value = min(abs(diff), s.risk.max_order)
            qty = qty_round(
                value / price, s.capital.fractional and instrument.fractional
            )
            if qty < instrument.min_qty or qty * price < s.capital.min_order:
                reasons.append(f"{sym}: below minimum quantity/notional")
                continue
            changes.append(
                {
                    "symbol": sym,
                    "side": "buy" if diff > 0 else "sell",
                    "qty": qty,
                    "intended": qty * price,
                    "protective": sym in forced or protect,
                }
            )
        changes.sort(key=lambda x: (x["side"] == "buy", x["symbol"]))
        turnover_left = equity * s.risk.max_turnover
        orders = []
        # Reserve exposure conservatively: planned sales do not release room until filled.
        exposure = {sym: p["qty"] * prices[sym] for sym, p in positions.items()}
        for o in changes:
            if len(orders) + orders_today >= s.risk.max_orders_day:
                reasons.append("Maximum orders per day")
                break
            # Protective reductions bypass turnover, but never order-notional or ownership limits.
            price = prices[o["symbol"]]
            value = (
                o["intended"]
                if o["protective"]
                else min(o["intended"], max(0, turnover_left))
            )
            if o["side"] == "buy":
                if o["symbol"] not in exposure and len(exposure) >= s.risk.max_holdings:
                    reasons.append(
                        f"{o['symbol']}: existing holdings leave no new position slot"
                    )
                    continue
                sector = SECTORS.get(o["symbol"], "Unknown")
                sector_used = sum(
                    v
                    for sym, v in exposure.items()
                    if SECTORS.get(sym, "Unknown") == sector
                )
                position_room = max(
                    0, s.risk.max_position * equity - exposure.get(o["symbol"], 0)
                )
                sector_room = max(0, s.risk.max_sector * equity - sector_used)
                deployment_room = max(
                    0,
                    min(s.capital.deployment, 1 - s.capital.cash_reserve) * equity
                    - sum(exposure.values()),
                )
                value = min(value, position_room, sector_room, deployment_room)
                fee = s.simulation.commission_fixed
                buffer = (
                    1
                    + (
                        s.simulation.slippage_bps
                        + s.simulation.spread_bps / 2
                        + s.simulation.commission_bps
                    )
                    / 10000
                    + 0.002
                )
                value = min(
                    value,
                    s.risk.max_order / buffer,
                    max(0, (cash - reserve - fee) / buffer),
                )
            instrument = broker.instrument(o["symbol"])
            qty = qty_round(
                value / price, s.capital.fractional and instrument.fractional
            )
            if o["side"] == "sell":
                qty = min(qty, positions[o["symbol"]]["qty"])
            if qty * price < s.capital.min_order:
                reasons.append(f"{o['symbol']}: cash/turnover/minimum limit")
                continue
            o.update(qty=qty, intended=qty * price)
            if o["side"] == "buy":
                cash -= qty * price * buffer + fee
                exposure[o["symbol"]] = exposure.get(o["symbol"], 0) + qty * price
            # Never budget anticipated sell proceeds before confirmed fills.
            if not o["protective"]:
                turnover_left -= qty * price
            orders.append(o)
        return orders, reasons

    def final(
        self, order, broker, owned, ledger_cash, price, equity=None, price_map=None
    ):
        if (
            order["qty"] <= 0
            or order["intended"] > self.s.risk.max_order + 1e-6
            or order["qty"] * price > self.s.risk.max_order + 1e-6
        ):
            raise RiskBlocked("Order size invalid")
        if not broker.market_open():
            raise RiskBlocked("Market closed")
        account = broker.account()
        if account.blocked:
            raise RiskBlocked("Broker account restricted")
        if (
            order["side"] == "sell"
            and order["qty"] > owned.get(order["symbol"], {}).get("qty", 0) + 1e-7
        ):
            raise RiskBlocked("Sell exceeds bot-owned quantity")
        if order["side"] == "buy" and order["qty"] * price > min(
            ledger_cash, account.cash, account.buying_power
        ):
            raise RiskBlocked("Insufficient bot cash")

        if (
            order["side"] == "buy"
            and order["symbol"] not in owned
            and len(owned) >= self.s.risk.max_holdings
        ):
            raise RiskBlocked("Final maximum holdings check failed")
        if order["side"] == "buy" and equity is not None:
            cost = order["qty"] * price
            if ledger_cash - cost < equity * self.s.capital.cash_reserve:
                raise RiskBlocked("Final cash reserve check failed")
            held = owned.get(order["symbol"], {}).get("qty", 0) * price
            if held + cost > equity * self.s.risk.max_position + 1e-6:
                raise RiskBlocked("Final position cap check failed")

            if price_map is not None:
                sector = SECTORS.get(order["symbol"], "Unknown")
                sector_value = sum(
                    p["qty"] * price_map[sym]
                    for sym, p in owned.items()
                    if SECTORS.get(sym, "Unknown") == sector
                )
                if sector_value + cost > equity * self.s.risk.max_sector + 1e-6:
                    raise RiskBlocked("Final sector cap check failed")
