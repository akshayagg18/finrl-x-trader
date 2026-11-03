"""Nautilus cash-account experiments using historical bars and modeled execution quotes.

Quotes below are cost assumptions derived from actual bar opens, not historical NBBO.
No live clients or credentials are loaded by this module.
"""

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import BTC, ETH, USD, USDT
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy
from pydantic import BaseModel, ConfigDict, Field

from trader.risk import portfolio_loss


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    interval: Literal[5, 15] = 15
    model_id: str | None = None
    ml_buffer: float = Field(default=0.001, ge=0, le=0.1)
    max_daily_loss: float = Field(default=0.05, gt=0, lt=1)
    max_capital_loss: float = Field(default=0.2, gt=0, lt=1)
    symbol: str = "BTC-USDT"
    strategy: str = Field(
        default="momentum", pattern="^(momentum|reversion|cash|hold|ml)$"
    )
    capital: float = Field(default=500, gt=0)
    allocation: float = Field(default=0.5, gt=0, le=0.8)
    lookback: int = Field(default=32, ge=4, le=256)
    threshold: float = Field(default=0.003, gt=0)
    stop_loss: float = Field(default=0.03, gt=0, lt=1)
    max_drawdown: float = Field(default=0.15, gt=0, lt=1)
    fee_bps: float = Field(default=10, ge=0, le=100)
    friction_bps: float = Field(default=5, ge=0, le=100)
    max_trades_day: int = Field(default=4, ge=1, le=30)


def load(symbol, interval=15):
    if interval not in (5, 15):
        raise ValueError("Only 5/15-minute candles supported")
    if symbol not in ("BTC-USDT", "ETH-USDT", "SPY", "QQQ", "AAPL"):
        raise ValueError("Unsupported research instrument")
    path = Path("research/intraday/data") / f"{symbol}_{interval}m.csv"
    df = pd.read_csv(path, index_col="timestamp", parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    if df.empty or df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError("Invalid timestamps")
    if (
        not np.isfinite(df[["open", "high", "low", "close", "volume"]]).all().all()
        or (df[["open", "high", "low", "close"]] <= 0).any().any()
    ):
        raise ValueError("Invalid market data")
    if (df.high < df[["open", "close", "low"]].max(axis=1)).any() or (
        df.low > df[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("Invalid OHLC bounds")
    if "-" not in symbol:
        from trader.scheduler import schedule

        sessions = schedule(df.index[0].date(), df.index[-1].date())
        allowed = pd.Series(False, index=df.index)
        for row in sessions.itertuples():
            allowed |= (df.index >= row.market_open) & (
                df.index + pd.Timedelta(minutes=interval) <= row.market_close
            )
        df = df.loc[allowed]
    return df


def signals(df, c):
    # All features lag one bar; orders are filled using the subsequent open.
    if c.strategy == "ml":
        from .ml import targets

        return targets(df, c)
    past = df.close.shift(1)
    if c.strategy == "cash":
        return pd.Series(False, index=df.index)
    if c.strategy == "hold":
        return pd.Series(True, index=df.index)
    if c.strategy == "momentum":
        return past.pct_change(c.lookback) > c.threshold
    mean = past.rolling(c.lookback).mean()
    return (past / mean - 1) < -c.threshold


class ResearchStrategy(Strategy):
    def __init__(self, instrument, targets, config, policies=None):
        super().__init__()
        self.policies = policies or []
        self.instrument = instrument
        self.targets = targets
        self.c = config
        self.points = []
        self.blocks = []
        self.peak = config.capital
        self.halted = False
        self.day = None
        self.count = 0
        self.entry = None
        self.unsettled = []
        self.day_start = config.capital
        self.new_day = True

    def on_start(self):
        self.subscribe_quote_ticks(self.instrument.id)

    def on_quote_tick(self, tick):
        day = str(pd.Timestamp(tick.ts_event, tz="UTC").date())
        if day != self.day:
            self.day = day
            self.count = 0
            self.new_day = True
        account = self.cache.account_for_venue(self.instrument.id.venue)
        cash = float(account.balance_free(self.instrument.quote_currency).as_double())
        qty = float(self.portfolio.net_position(self.instrument.id))
        bid = float(tick.bid_price)
        ask = float(tick.ask_price)
        equity = cash + qty * bid
        self.peak = max(self.peak, equity)
        if self.new_day:
            self.day_start = (
                self.points[-1]["equity"] if self.points else self.c.capital
            )
            self.new_day = False
        reason = portfolio_loss(
            equity,
            self.day_start,
            self.peak,
            self.c.capital,
            self.c.max_daily_loss,
            self.c.max_drawdown,
            self.c.max_capital_loss,
        )
        if self.c.strategy != "hold" and reason:
            self.halted = True
            self.blocks.append({"timestamp": tick.ts_event, "reason": reason})
        self.points.append(
            {
                "timestamp": str(pd.Timestamp(tick.ts_event, tz="UTC")),
                "equity": equity,
                "cash": cash,
            }
        )
        mode = "trade"
        for policy in self.policies:
            if pd.Timestamp(policy["at"]).value <= tick.ts_event:
                mode = policy["mode"]
        desired = (
            self.targets.get(tick.ts_event, False)
            and not self.halted
            and mode != "flatten"
        )
        stop = (
            self.c.strategy != "hold"
            and qty > 0
            and self.entry
            and bid < self.entry * (1 - self.c.stop_loss)
        )
        if qty > 0 and (not desired or stop):
            self.close_all_positions(self.instrument.id)
            self.entry = None
            self.count += 1
        elif (
            qty == 0
            and desired
            and mode == "trade"
            and self.count < self.c.max_trades_day
        ):
            self.unsettled = [
                (due, amount) for due, amount in self.unsettled if due > day
            ]
            settled = max(0, cash - sum(amount for _, amount in self.unsettled))
            budget = min(
                settled / (1 + self.c.fee_bps / 10000), equity * self.c.allocation
            )
            step = float(self.instrument.size_increment)
            units = math.floor(budget / ask / step) * step
            if (
                units <= 0
                or units * ask < 1
                or (
                    self.instrument.min_quantity is not None
                    and units < float(self.instrument.min_quantity)
                )
            ):
                self.blocks.append(
                    {
                        "timestamp": tick.ts_event,
                        "reason": "minimum size or whole-share affordability",
                    }
                )
                return
            order = self.order_factory.market(
                self.instrument.id, OrderSide.BUY, self.instrument.make_qty(units)
            )
            self.submit_order(order)
            self.entry = ask
            self.count += 1

    def on_order_filled(self, event):
        if event.order_side == OrderSide.BUY:
            self.entry = float(event.last_px)
        elif isinstance(self.instrument, Equity):
            from trader.scheduler import schedule

            day = pd.Timestamp(event.ts_event, tz="UTC").date()
            sessions = schedule(day, pd.Timestamp(day) + pd.Timedelta(days=14))
            next_day = next(d.date() for d in sessions.index if d.date() > day)
            proceeds = float(event.last_qty) * float(event.last_px) - float(
                event.commission.as_double()
            )
            self.unsettled.append((str(next_day), proceeds))


def _backtest(config, start, end, *, liquidate=True, policies=None):
    c = Experiment.model_validate(config)
    df = load(c.symbol, c.interval)
    target = signals(df, c)
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(end)
    lo = lo.tz_localize("UTC") if lo.tzinfo is None else lo.tz_convert("UTC")
    hi = hi.tz_localize("UTC") if hi.tzinfo is None else hi.tz_convert("UTC")
    if len(str(end)) == 10:
        hi += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    selected = df.loc[lo:hi]
    if len(selected) < (2 if liquidate else 1):
        raise ValueError("Insufficient data")
    if c.strategy == "ml":
        from .ml import prediction

        _, meta = prediction(df, c.model_id, c.symbol, c.interval)
        if selected.index[0] < pd.Timestamp(meta["cutoff"]):
            raise ValueError("Evaluation starts before model training cutoff")
    venue = Venue("RESEARCH")
    iid = InstrumentId(Symbol(c.symbol), venue)
    crypto = "-" in c.symbol
    if crypto:
        meta = json.loads(
            (
                Path("research/intraday/data") / f"{c.symbol}_{c.interval}m.json"
            ).read_text()
        )
        details = meta["metadata"]["instrument"]["data"][0]
        tick = details["tickSz"]
        lot = details["lotSz"]
        minimum = details["minSz"]
        precision = lambda v: max(0, -Decimal(v).normalize().as_tuple().exponent)
        ins = CurrencyPair(
            iid,
            Symbol(c.symbol),
            BTC if c.symbol.startswith("BTC") else ETH,
            USDT,
            precision(tick),
            precision(lot),
            Price.from_str(tick),
            Quantity.from_str(lot),
            0,
            0,
            min_quantity=Quantity.from_str(minimum),
            maker_fee=Decimal(str(c.fee_bps / 10000)),
            taker_fee=Decimal(str(c.fee_bps / 10000)),
        )
    else:
        ins = Equity(
            iid,
            Symbol(c.symbol),
            USD,
            2,
            Price.from_str("0.01"),
            Quantity.from_int(1),
            0,
            0,
            maker_fee=Decimal(str(c.fee_bps / 10000)),
            taker_fee=Decimal(str(c.fee_bps / 10000)),
        )
    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True))
    )
    engine.add_venue(
        venue,
        OmsType.NETTING,
        AccountType.CASH,
        [Money(c.capital, ins.quote_currency)],
        allow_cash_borrowing=False,
    )
    engine.add_instrument(ins)
    ticks = []
    for ts, row in selected.iterrows():
        mid = row.open
        ticks.append(
            QuoteTick(
                iid,
                ins.make_price(mid * (1 - c.friction_bps / 10000)),
                ins.make_price(mid * (1 + c.friction_bps / 10000)),
                ins.make_qty(10000),
                ins.make_qty(10000),
                ts.value,
                ts.value,
            )
        )
    # A final mark also liquidates through the engine, charging exit fees/friction.
    ts = selected.index[-1] + pd.Timedelta(minutes=c.interval)
    mid = selected.iloc[-1].close
    ticks.append(
        QuoteTick(
            iid,
            ins.make_price(mid * (1 - c.friction_bps / 10000)),
            ins.make_price(mid * (1 + c.friction_bps / 10000)),
            ins.make_qty(10000),
            ins.make_qty(10000),
            ts.value,
            ts.value,
        )
    )
    targets = {ts.value: bool(target.loc[ts]) for ts in selected.index}
    if not liquidate:
        # Final mark values the existing position without creating an entry or terminal exit.
        ticks = ticks[:-1]
    strategy = ResearchStrategy(ins, targets, c, policies)
    engine.add_data(ticks)
    engine.add_strategy(strategy)
    engine.run()
    account = engine.cache.account_for_venue(venue)
    final = float(account.balance_total(ins.quote_currency).as_double())
    quantity = float(engine.portfolio.net_position(ins.id))
    cash = final
    final = cash + quantity * float(ticks[-1].bid_price)
    points = pd.DataFrame(strategy.points)
    points.loc[len(points) - 1, "equity"] = final
    values = pd.Series([c.capital, *points.equity.tolist()])
    draw = values / values.cummax() - 1
    fills = engine.trader.generate_order_fills_report()
    result = {
        "config": c.model_dump(),
        "cash": cash,
        "quantity": quantity,
        "liquidated": liquidate,
        "unsettled": strategy.unsettled,
        "start": start,
        "end": end,
        "engine": "NautilusTrader 1.231.0",
        "net_return": final / c.capital - 1,
        "ending_equity": final,
        "max_drawdown": float(draw.min()),
        "fills": json.loads(fills.to_json(orient="records", date_format="iso")),
        "equity": points.to_dict("records"),
        "blocked": strategy.blocks,
        "halted": strategy.halted,
        "assumptions": [
            "Historical opens with modeled bid/ask, not observed quotes",
            "Immediate full market fills; no depth or queue simulation",
            "Equities whole shares; sell proceeds settle next exchange session; original settled cash remains usable",
            "Crypto USDT is assumed USD parity; conversion and depeg risk excluded",
            "Only bar-boundary stops; no intrabar protection",
        ],
    }
    engine.dispose()
    from .analytics import analyze

    result["metrics"] = analyze(result)
    return result


def backtest(config, start, end, *, liquidate=True, policies=None):
    from filelock import FileLock

    Path("runtime").mkdir(exist_ok=True)
    with FileLock("runtime/intraday-engine.lock", timeout=120):
        return _backtest(config, start, end, liquidate=liquidate, policies=policies)
