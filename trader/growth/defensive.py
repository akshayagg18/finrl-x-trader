"""Causal, low-exposure BTC/ETH trend allocation research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

SYMBOLS = ("BTC-USDT", "ETH-USDT")
INITIAL_CAPITAL = 500.0
PER_ASSET_CAP = 0.10
MAX_DEPLOYMENT = 0.20
VOLATILITY_TARGET = 0.30


@dataclass(frozen=True)
class DefensiveRisk:
    per_asset_cap: float = PER_ASSET_CAP
    max_deployment: float = MAX_DEPLOYMENT
    volatility_target: float = VOLATILITY_TARGET

    def __post_init__(self) -> None:
        if not 0 < self.per_asset_cap <= 1:
            raise ValueError("Per-asset cap must be in (0, 1]")
        if not 0 < self.max_deployment <= 1:
            raise ValueError("Maximum deployment must be in (0, 1]")
        if self.per_asset_cap > self.max_deployment:
            raise ValueError("Per-asset cap cannot exceed maximum deployment")
        if not 0 < self.volatility_target <= 2:
            raise ValueError("Volatility target must be in (0, 2]")

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_RISK = DefensiveRisk()


@dataclass(frozen=True)
class DefensiveSpec:
    slow_days: int
    momentum_days: int
    cadence: str
    mode: str

    @property
    def name(self) -> str:
        return (
            f"trend_{self.slow_days}_momentum_{self.momentum_days}_"
            f"{self.cadence}_{self.mode}"
        )

    def as_dict(self) -> dict:
        return asdict(self)


SPECS = tuple(
    DefensiveSpec(slow, momentum, cadence, mode)
    for slow in (100, 150, 200)
    for momentum in (30, 90, 180)
    for cadence in ("weekly", "biweekly", "monthly")
    for mode in ("both", "best", "btc_gate")
)


def prepare_daily(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    result = {}
    for symbol in SYMBOLS:
        frame = data[symbol]
        count = frame.close.resample("1D").count()
        result[symbol] = pd.DataFrame(
            {
                "open": frame.open.resample("1D").first().where(count == 24),
                "close": frame.close.resample("1D").last().where(count == 24),
            }
        )
    return result


def defensive_features(frame: pd.DataFrame, spec: DefensiveSpec) -> pd.DataFrame:
    """Features available at the next UTC daily open."""

    prior_close = frame.close.shift(1)
    returns = prior_close.pct_change(fill_method=None)
    return pd.DataFrame(
        {
            "trend": prior_close / prior_close.rolling(spec.slow_days).mean() - 1,
            "momentum": prior_close / prior_close.shift(spec.momentum_days) - 1,
            "volatility": returns.rolling(30).std() * np.sqrt(365),
        },
        index=frame.index,
    ).replace([np.inf, -np.inf], np.nan)


def rebalance_due(timestamp: pd.Timestamp, cadence: str) -> bool:
    if cadence == "weekly":
        return timestamp.weekday() == 0
    if cadence == "biweekly":
        return timestamp.weekday() == 0 and int(timestamp.isocalendar().week) % 2 == 0
    if cadence == "monthly":
        return timestamp.weekday() == 0 and timestamp.day <= 7
    raise ValueError("Unsupported cadence")


def target_weights(
    timestamp: pd.Timestamp,
    features: dict[str, pd.DataFrame],
    spec: DefensiveSpec,
    risk: DefensiveRisk = DEFAULT_RISK,
) -> dict[str, float]:
    eligible = [
        symbol
        for symbol in SYMBOLS
        if features[symbol].loc[timestamp, "trend"] > 0
        and features[symbol].loc[timestamp, "momentum"] > 0
    ]
    if spec.mode == "both":
        chosen = eligible
    elif spec.mode == "best":
        chosen = (
            [
                max(
                    eligible,
                    key=lambda symbol: features[symbol].loc[timestamp, "momentum"],
                )
            ]
            if eligible
            else []
        )
    elif spec.mode == "btc_gate":
        chosen = list(SYMBOLS) if "BTC-USDT" in eligible else []
    else:
        raise ValueError("Unsupported allocation mode")

    result = {}
    for symbol in SYMBOLS:
        volatility = features[symbol].loc[timestamp, "volatility"]
        if symbol not in chosen or not np.isfinite(volatility) or volatility <= 0:
            result[symbol] = 0.0
        else:
            result[symbol] = float(
                min(
                    risk.per_asset_cap,
                    risk.per_asset_cap * risk.volatility_target / volatility,
                )
            )
    total = sum(result.values())
    if total > risk.max_deployment:
        scale = risk.max_deployment / total
        result = {symbol: weight * scale for symbol, weight in result.items()}
    return result


def _timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True)


def _drawdown(points: list[dict], initial: float) -> float:
    equity = np.array([initial, *[float(point["equity"]) for point in points]])
    return float(np.min(equity / np.maximum.accumulate(equity) - 1))


def simulate(
    data: dict[str, pd.DataFrame],
    spec: DefensiveSpec,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    initial: float = INITIAL_CAPITAL,
    cost_bps: float = 15.0,
    risk: DefensiveRisk = DEFAULT_RISK,
) -> dict:
    """Execute lagged targets at daily opens with adverse proportional costs."""

    if initial <= 0 or cost_bps < 0:
        raise ValueError("Invalid capital or cost")
    daily = prepare_daily(data)
    features = {
        symbol: defensive_features(daily[symbol], spec) for symbol in SYMBOLS
    }
    common = daily[SYMBOLS[0]].dropna().index.intersection(
        daily[SYMBOLS[1]].dropna().index
    )
    start_at = _timestamp(start)
    end_at = _timestamp(end)
    dates = common[(common >= start_at) & (common <= end_at)]
    if not len(dates):
        raise ValueError("No complete daily observations")

    cash = float(initial)
    quantity = {symbol: 0.0 for symbol in SYMBOLS}
    cost_rate = cost_bps / 10000
    points = []
    fills = []
    decisions = []
    for timestamp in dates:
        prices = {
            symbol: float(daily[symbol].loc[timestamp, "open"])
            for symbol in SYMBOLS
        }
        equity = cash + sum(quantity[s] * prices[s] for s in SYMBOLS)
        if rebalance_due(timestamp, spec.cadence):
            weights = target_weights(timestamp, features, spec, risk)
            decisions.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "weights": weights,
                    "equity_before": equity,
                }
            )
            target = {symbol: equity * weights[symbol] for symbol in SYMBOLS}
            for symbol in SYMBOLS:
                current = quantity[symbol] * prices[symbol]
                if current > target[symbol] + 0.01:
                    notional = current - target[symbol]
                    fee = notional * cost_rate
                    quantity[symbol] -= notional / prices[symbol]
                    cash += notional - fee
                    fills.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "symbol": symbol,
                            "side": "SELL",
                            "notional": notional,
                            "cost": fee,
                        }
                    )
            for symbol in SYMBOLS:
                current = quantity[symbol] * prices[symbol]
                if target[symbol] > current + 0.01:
                    notional = min(
                        target[symbol] - current,
                        cash / (1 + cost_rate),
                    )
                    fee = notional * cost_rate
                    quantity[symbol] += notional / prices[symbol]
                    cash -= notional + fee
                    fills.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "symbol": symbol,
                            "side": "BUY",
                            "notional": notional,
                            "cost": fee,
                        }
                    )
        equity = cash + sum(quantity[s] * prices[s] for s in SYMBOLS)
        points.append(
            {
                "timestamp": timestamp.isoformat(),
                "equity": equity,
                "cash": cash,
                "exposure": 1 - cash / equity if equity else 0.0,
            }
        )

    final_prices = {
        symbol: float(daily[symbol].loc[dates[-1], "close"]) for symbol in SYMBOLS
    }
    ending = cash + sum(quantity[s] * final_prices[s] for s in SYMBOLS)
    points.append(
        {
            "timestamp": (dates[-1] + timedelta(hours=23)).isoformat(),
            "equity": ending,
            "cash": cash,
            "exposure": 1 - cash / ending if ending else 0.0,
        }
    )
    total_cost = float(sum(fill["cost"] for fill in fills))
    exits = sum(
        1
        for fill in fills
        if fill["side"] == "SELL" and fill["notional"] > 0
    )
    return {
        "spec": spec.as_dict(),
        "risk": risk.as_dict(),
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
        "initial": initial,
        "ending_equity": ending,
        "net_return": ending / initial - 1,
        "same_trade_gross_return": (ending + total_cost) / initial - 1,
        "max_drawdown": _drawdown(points, initial),
        "fills": fills,
        "fill_count": len(fills),
        "sell_count": exits,
        "transaction_costs": total_cost,
        "positions": quantity,
        "points": points,
        "decisions": decisions,
    }
