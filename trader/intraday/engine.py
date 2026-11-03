"""Nautilus cash-account experiments using historical bars and modeled execution quotes.

Quotes below are cost assumptions derived from actual bar opens, not historical NBBO.
No live clients or credentials are loaded by this module.
"""

import json
import math
from decimal import Decimal
from pathlib import Path

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
from pydantic import BaseModel, Field


class Experiment(BaseModel):
    symbol: str = "BTC-USDT"
    strategy: str = Field(
        default="momentum", pattern="^(momentum|reversion|cash|hold)$"
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
    def __init__(self, instrument, targets, config):
        super().__init__()
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
        self.last_sale_day = None

    def on_start(self):
        self.subscribe_quote_ticks(self.instrument.id)

    def on_quote_tick(self, tick):
        day = str(pd.Timestamp(tick.ts_event, tz="UTC").date())
        if day != self.day:
            self.day = day
            self.count = 0
        account = self.cache.account_for_venue(self.instrument.id.venue)
        cash = float(account.balance_free(self.instrument.quote_currency).as_double())
        qty = float(self.portfolio.net_position(self.instrument.id))
        bid = float(tick.bid_price)
        ask = float(tick.ask_price)
        equity = cash + qty * bid
        self.peak = max(self.peak, equity)
        if self.c.strategy != "hold" and equity < self.peak * (1 - self.c.max_drawdown):
            self.halted = True
        self.points.append(
            {
                "timestamp": str(pd.Timestamp(tick.ts_event, tz="UTC")),
                "equity": equity,
                "cash": cash,
            }
        )
        desired = self.targets.get(tick.ts_event, False) and not self.halted
        stop = (
            self.c.strategy != "hold"
            and qty > 0
            and self.entry
            and bid < self.entry * (1 - self.c.stop_loss)
        )
        if qty > 0 and (not desired or stop):
            self.close_all_positions(self.instrument.id)
            self.last_sale_day = day
            self.entry = None
            self.count += 1
        elif qty == 0 and desired and self.count < self.c.max_trades_day:
            # Conservative settlement: no reuse of sale proceeds on the sale day.
            # Bars only occur on trading sessions; subsequent session is T+1.
            if isinstance(self.instrument, Equity) and self.last_sale_day == day:
                return
            budget = min(
                cash / (1 + self.c.fee_bps / 10000), equity * self.c.allocation
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


def backtest(config, start, end):
    c = Experiment.model_validate(config)
    df = load(c.symbol)
    target = signals(df, c)
    selected = df.loc[start:end]
    if len(selected) < 2:
        raise ValueError("Insufficient data")
    venue = Venue("RESEARCH")
    iid = InstrumentId(Symbol(c.symbol), venue)
    crypto = "-" in c.symbol
    if crypto:
        meta = json.loads(
            (Path("research/intraday/data") / f"{c.symbol}_15m.json").read_text()
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
    ts = selected.index[-1] + pd.Timedelta(minutes=15)
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
    strategy = ResearchStrategy(
        ins, {ts.value: bool(target.loc[ts]) for ts in selected.index}, c
    )
    engine.add_data(ticks)
    engine.add_strategy(strategy)
    engine.run()
    account = engine.cache.account_for_venue(venue)
    final = float(account.balance_total(ins.quote_currency).as_double())
    points = pd.DataFrame(strategy.points)
    points.loc[len(points) - 1, "equity"] = final
    values = pd.Series([c.capital, *points.equity.tolist()])
    draw = values / values.cummax() - 1
    fills = engine.trader.generate_order_fills_report()
    result = {
        "config": c.model_dump(),
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
            "Equities whole shares, conservative same-day sale cash lock",
            "Crypto USDT is assumed USD parity; conversion and depeg risk excluded",
            "Only bar-boundary stops; no intrabar protection",
        ],
    }
    engine.dispose()
    return result
