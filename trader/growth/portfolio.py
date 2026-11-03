"""One Nautilus cash account, shared risk and continuous BTC/ETH positions."""

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from filelock import FileLock
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import BTC, ETH, USDT
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.risk import portfolio_loss

from .config import GrowthConfig


def instrument(symbol, fee):
    m = json.loads(
        (Path("research/intraday/data") / (symbol + "_15m.json")).read_text()
    )["metadata"]["instrument"]["data"][0]
    precision = lambda x: max(0, -Decimal(x).normalize().as_tuple().exponent)
    return CurrencyPair(
        InstrumentId(Symbol(symbol), Venue("GROWTH")),
        Symbol(symbol),
        BTC if symbol.startswith("BTC") else ETH,
        USDT,
        precision(m["tickSz"]),
        precision(m["lotSz"]),
        Price.from_str(m["tickSz"]),
        Quantity.from_str(m["lotSz"]),
        0,
        0,
        min_quantity=Quantity.from_str(m["minSz"]),
        maker_fee=Decimal(str(fee / 10000)),
        taker_fee=Decimal(str(fee / 10000)),
    )


class Portfolio(Strategy):
    def __init__(self, instruments, decisions, c, benchmark=False):
        super().__init__()
        self.ins = instruments
        self.decisions = decisions
        self.c = c
        self.benchmark = benchmark
        self.quotes = {}
        self.entries = {}
        self.expiry = {}
        self.stops = {}
        self.peak = c.capital
        self.day = None
        self.day_start = c.capital
        self.halt = False
        self.points = []
        self.blocked = []
        self.seen = {}
        self.clock_step = 0

    def on_start(self):
        for i in self.ins.values():
            self.subscribe_quote_ticks(i.id)

    def on_quote_tick(self, t):
        sym = t.instrument_id.symbol.value
        self.quotes[sym] = t
        if len(self.quotes) != len(self.ins) or any(
            q.ts_event != t.ts_event for q in self.quotes.values()
        ):
            return
        self.clock_step += 1
        cash = float(
            self.cache.account_for_venue(Venue("GROWTH")).balance_free(USDT).as_double()
        )
        quantities = {
            s: float(self.portfolio.net_position(i.id)) for s, i in self.ins.items()
        }
        equity = cash + sum(
            quantities[s] * float(q.bid_price) for s, q in self.quotes.items()
        )
        day = str(
            pd.Timestamp(t.ts_event, tz="UTC").tz_convert("Asia/Singapore").date()
        )
        if day != self.day:
            self.day = day
            self.day_start = (
                self.points[-1]["equity"] if self.points else self.c.capital
            )
        self.peak = max(self.peak, equity)
        trigger = portfolio_loss(
            equity,
            self.day_start,
            self.peak,
            self.c.capital,
            self.c.daily_loss,
            self.c.drawdown_halt,
            0.1,
        )
        if not self.benchmark and trigger in (
            "Maximum drawdown",
            "Maximum capital loss",
            "Invalid portfolio valuation",
        ):
            self.halt = True
        self.points.append(
            {
                "timestamp": str(pd.Timestamp(t.ts_event, tz="UTC")),
                "equity": equity,
                "cash": cash,
                "exposure": 1 - cash / equity if equity else 0,
            }
        )
        for s, i in self.ins.items():
            q = self.quotes[s]
            qty = quantities[s]
            decision = self.decisions.get(t.ts_event, {}).get(s, {})
            if qty > 0:
                stop = float(q.bid_price) <= self.entries.get(s, float(q.ask_price)) * (
                    1 - self.stops.get(s, 0.03)
                )
                expired = t.ts_event >= self.expiry.get(s, 0)
                if not self.benchmark and (
                    self.halt or stop or expired or decision.get("liquidate", False)
                ):
                    self.close_all_positions(i.id)
                continue
            if (
                self.halt
                or (trigger and not self.benchmark)
                or not decision.get("enter", False)
            ):
                continue
            stop = float(decision.get("stop", 0.03))
            cash = float(
                self.cache.account_for_venue(Venue("GROWTH"))
                .balance_free(USDT)
                .as_double()
            )
            deployed = sum(
                float(self.portfolio.net_position(j.id))
                * float(self.quotes[k].ask_price)
                for k, j in self.ins.items()
            )
            budget = min(
                equity * self.c.per_asset,
                max(0, equity * self.c.deployment - deployed),
                max(0, cash - equity * self.c.reserve) / (1 + self.c.fee_bps / 10000),
            )
            if not self.benchmark:
                budget = min(budget, equity * self.c.trade_risk / stop)
            step = float(i.size_increment)
            units = np.floor(budget / float(q.ask_price) / step) * step
            if units < float(i.min_quantity) or units * float(q.ask_price) < 1:
                self.blocked.append(
                    {
                        "timestamp": t.ts_event,
                        "symbol": s,
                        "reason": "Cash, risk budget or minimum quantity",
                    }
                )
                continue
            self.entries[s] = float(q.ask_price)
            self.stops[s] = stop
            self.expiry[s] = (
                t.ts_event + int(decision.get("horizon", 24)) * 3600 * 10**9
            )
            self.submit_order(
                self.order_factory.market(i.id, OrderSide.BUY, i.make_qty(units))
            )


def execute(data, decisions, config=None, benchmark=False, observed_quotes=None):
    c = GrowthConfig.model_validate(config or {})
    dates = data["BTC-USDT"].index.intersection(data["ETH-USDT"].index)
    if not len(dates):
        raise ValueError("No synchronized data")
    instruments = {s: instrument(s, c.fee_bps) for s in data}
    Path("runtime").mkdir(exist_ok=True)
    with FileLock("runtime/intraday-engine.lock", timeout=120):
        engine = BacktestEngine(
            BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True))
        )
        try:
            engine.add_venue(
                Venue("GROWTH"),
                OmsType.NETTING,
                AccountType.CASH,
                [Money(c.capital, USDT)],
                allow_cash_borrowing=False,
            )
            ticks = []
            for s, i in instruments.items():
                engine.add_instrument(i)
                for ts in dates:
                    mid = float(data[s].loc[ts, "open"])
                    bid = mid * (1 - c.friction_bps / 10000)
                    ask = mid * (1 + c.friction_bps / 10000)
                    if observed_quotes is not None:
                        bid, ask = observed_quotes[ts.value][s]
                    ticks.append(
                        QuoteTick(
                            i.id,
                            i.make_price(bid),
                            i.make_price(ask),
                            i.make_qty(10000),
                            i.make_qty(10000),
                            ts.value,
                            ts.value,
                        )
                    )
            ticks.sort(key=lambda t: t.ts_event)
            engine.add_data(ticks)
            strategy = Portfolio(instruments, decisions, c, benchmark)
            engine.add_strategy(strategy)
            engine.run()
            fills = json.loads(
                engine.trader.generate_order_fills_report().to_json(
                    orient="records", date_format="iso"
                )
            )
            cash = float(
                engine.cache.account_for_venue(Venue("GROWTH"))
                .balance_total(USDT)
                .as_double()
            )
            positions = {
                s: float(engine.portfolio.net_position(i.id))
                for s, i in instruments.items()
            }
            equity = cash + sum(
                positions[s] * float(strategy.quotes[s].bid_price) for s in positions
            )
            strategy.points[-1].update(equity=equity, cash=cash)
            fees = sum(float(x.split()[0]) for f in fills for x in f["commissions"])
            execution_friction = 0
            for f in fills:
                s = f["instrument_id"].split(".")[0]
                ts = pd.Timestamp(f["ts_last"])
                mid = float(data[s].loc[ts, "open"])
                execution_friction += (
                    float(f["filled_qty"])
                    * (float(f["avg_px"]) - mid)
                    * (1 if f["side"] == "BUY" else -1)
                )
            mark_friction = sum(
                positions[s]
                * (
                    float(data[s].loc[dates[-1], "open"])
                    - float(strategy.quotes[s].bid_price)
                )
                for s in positions
            )
            return {
                "mode": "forward local simulation"
                if observed_quotes is not None
                else "continuous historical research",
                "initial": c.capital,
                "config": c.model_dump(),
                "equity": strategy.points,
                "fills": fills,
                "positions": positions,
                "cash": cash,
                "ending_equity": equity,
                "net_return": equity / c.capital - 1,
                "same_trade_gross_return": (
                    equity + fees + execution_friction + mark_friction
                )
                / c.capital
                - 1,
                "fees": fees,
                "execution_friction": execution_friction,
                "mark_friction": mark_friction,
                "halted": strategy.halt,
                "blocked": strategy.blocked,
                "completed_trades": sum(f["side"] == "SELL" for f in fills),
                "assumptions": [
                    "Full market fills; no historical depth or queue reconstruction",
                    "USDT/USD parity assumed",
                    "Marked at last observed bid; no final forced liquidation",
                    "Same-trade gross holds actual quantities fixed; it is attribution, not an executable alternative strategy",
                ],
            }
        finally:
            engine.dispose()
