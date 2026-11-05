"""Causal short, relative-value, and synthetic put research engines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from math import erf, exp, log, sqrt

import numpy as np
import pandas as pd

from .defensive import (
    DEFAULT_RISK,
    INITIAL_CAPITAL,
    SYMBOLS,
    DefensiveRisk,
    DefensiveSpec,
    defensive_features,
    prepare_daily,
    rebalance_due,
    target_weights,
)


@dataclass(frozen=True)
class ShortHedgeSpec:
    slow_days: int
    momentum_days: int
    hedge_fraction: float
    trigger: str

    @property
    def name(self) -> str:
        ratio = int(self.hedge_fraction * 100)
        return (
            f"short_hedge_trend_{self.slow_days}_momentum_{self.momentum_days}_"
            f"{self.trigger}_{ratio}"
        )

    def as_dict(self) -> dict:
        return asdict(self)


SHORT_HEDGE_SPECS = tuple(
    ShortHedgeSpec(slow, momentum, fraction, trigger)
    for slow in (100, 150, 200)
    for momentum in (30, 90, 180)
    for fraction in (0.25, 0.50, 1.00)
    for trigger in ("trend", "confirmed", "either")
)


@dataclass(frozen=True)
class RelativeValueSpec:
    lookback_days: int
    entry_z: float
    exit_z: float
    cadence: str
    volatility_target: float

    @property
    def name(self) -> str:
        return (
            f"relative_value_{self.lookback_days}_{self.entry_z:g}_"
            f"{self.exit_z:g}_{self.cadence}_vol_{self.volatility_target:g}"
        )

    def as_dict(self) -> dict:
        return asdict(self)


RELATIVE_VALUE_SPECS = tuple(
    RelativeValueSpec(lookback, entry, exit_z, cadence, volatility)
    for lookback in (30, 60, 120, 180)
    for entry in (1.0, 1.5, 2.0)
    for exit_z in (0.0, 0.5)
    for cadence in ("daily", "weekly")
    for volatility in (0.20, 0.30)
)


@dataclass(frozen=True)
class PutProtectionSpec:
    slow_days: int
    momentum_days: int
    strike_otm: float
    coverage: float
    tenor_days: int
    volatility_markup: float = 1.25

    @property
    def name(self) -> str:
        return (
            f"put_trend_{self.slow_days}_momentum_{self.momentum_days}_"
            f"otm_{int(self.strike_otm * 100)}_coverage_{int(self.coverage * 100)}_"
            f"tenor_{self.tenor_days}"
        )

    def as_dict(self) -> dict:
        return asdict(self)


PUT_PROTECTION_SPECS = tuple(
    PutProtectionSpec(slow, momentum, strike, coverage, tenor)
    for slow in (100, 150, 200)
    for momentum in (30, 90, 180)
    for strike in (0.05, 0.10, 0.15)
    for coverage in (0.50, 1.00)
    for tenor in (28, 56)
)


def _timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True)


def _drawdown(points: list[dict], initial: float) -> float:
    values = np.asarray([initial, *[float(point["equity"]) for point in points]])
    return float(np.min(values / np.maximum.accumulate(values) - 1))


def _signed_simulation(
    data: dict[str, pd.DataFrame],
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    decision: Callable[[pd.Timestamp, dict[str, float]], dict[str, float] | None],
    *,
    initial: float,
    cost_bps: float,
    short_carry_annual: float,
) -> dict:
    if initial <= 0 or cost_bps < 0 or short_carry_annual < 0:
        raise ValueError("Invalid capital, cost, or short carry")
    daily = prepare_daily(data)
    common = daily[SYMBOLS[0]].dropna().index.intersection(
        daily[SYMBOLS[1]].dropna().index
    )
    start_at = _timestamp(start)
    end_at = _timestamp(end)
    dates = common[(common >= start_at) & (common <= end_at)]
    if not len(dates):
        raise ValueError("No complete daily observations")

    cash = float(initial)
    quantities = {symbol: 0.0 for symbol in SYMBOLS}
    current_weights = {symbol: 0.0 for symbol in SYMBOLS}
    cost_rate = cost_bps / 10_000
    fills = []
    decisions = []
    points = []
    trading_costs = 0.0
    financing_costs = 0.0
    prior_timestamp = dates[0]
    for timestamp in dates:
        prices = {
            symbol: float(daily[symbol].loc[timestamp, "open"])
            for symbol in SYMBOLS
        }
        elapsed_days = max((timestamp - prior_timestamp).total_seconds() / 86_400, 0)
        short_notional = sum(
            max(-quantities[symbol] * prices[symbol], 0.0) for symbol in SYMBOLS
        )
        financing = short_notional * short_carry_annual * elapsed_days / 365
        cash -= financing
        financing_costs += financing
        equity = cash + sum(
            quantities[symbol] * prices[symbol] for symbol in SYMBOLS
        )
        targets = decision(timestamp, current_weights.copy())
        if targets is not None:
            if set(targets) != set(SYMBOLS):
                raise ValueError("Target weights must cover the complete universe")
            gross = sum(abs(weight) for weight in targets.values())
            if gross > 1 + 1e-12:
                raise ValueError("Gross exposure exceeds one")
            target_notionals = {
                symbol: equity * targets[symbol] for symbol in SYMBOLS
            }
            turnover = sum(
                abs(
                    target_notionals[symbol]
                    - quantities[symbol] * prices[symbol]
                )
                for symbol in SYMBOLS
            )
            cost = turnover * cost_rate
            trading_costs += cost
            cash = equity - sum(target_notionals.values()) - cost
            for symbol in SYMBOLS:
                current = quantities[symbol] * prices[symbol]
                change = target_notionals[symbol] - current
                if abs(change) > 0.01:
                    fills.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "symbol": symbol,
                            "notional_change": change,
                            "target_weight": targets[symbol],
                            "cost": abs(change) * cost_rate,
                        }
                    )
                quantities[symbol] = target_notionals[symbol] / prices[symbol]
            current_weights = dict(targets)
            decisions.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "weights": dict(targets),
                    "gross_exposure": gross,
                    "equity_before": equity,
                }
            )
        equity = cash + sum(
            quantities[symbol] * prices[symbol] for symbol in SYMBOLS
        )
        gross_notional = sum(
            abs(quantities[symbol] * prices[symbol]) for symbol in SYMBOLS
        )
        points.append(
            {
                "timestamp": timestamp.isoformat(),
                "equity": equity,
                "cash": cash,
                "gross_exposure": gross_notional / equity if equity else 0.0,
            }
        )
        prior_timestamp = timestamp

    final_prices = {
        symbol: float(daily[symbol].loc[dates[-1], "close"]) for symbol in SYMBOLS
    }
    ending = cash + sum(
        quantities[symbol] * final_prices[symbol] for symbol in SYMBOLS
    )
    points.append(
        {
            "timestamp": (dates[-1] + timedelta(hours=23)).isoformat(),
            "equity": ending,
            "cash": cash,
            "gross_exposure": sum(
                abs(quantities[symbol] * final_prices[symbol])
                for symbol in SYMBOLS
            )
            / ending
            if ending
            else 0.0,
        }
    )
    return {
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
        "initial": initial,
        "ending_equity": ending,
        "net_return": ending / initial - 1,
        "same_trade_gross_return": (
            ending + trading_costs + financing_costs
        )
        / initial
        - 1,
        "max_drawdown": _drawdown(points, initial),
        "fills": fills,
        "fill_count": len(fills),
        "transaction_costs": trading_costs,
        "financing_costs": financing_costs,
        "points": points,
        "decisions": decisions,
        "positions": quantities,
    }


def simulate_short_hedge(
    data: dict[str, pd.DataFrame],
    spec: ShortHedgeSpec,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    risk: DefensiveRisk = DEFAULT_RISK,
    initial: float = INITIAL_CAPITAL,
    cost_bps: float = 15.0,
    short_carry_annual: float = 0.10,
) -> dict:
    daily = prepare_daily(data)
    base = DefensiveSpec(
        spec.slow_days, spec.momentum_days, "weekly", "btc_gate"
    )
    features = {
        symbol: defensive_features(daily[symbol], base) for symbol in SYMBOLS
    }

    def decide(timestamp: pd.Timestamp, _current: dict[str, float]):
        if not rebalance_due(timestamp, "weekly"):
            return None
        btc = features["BTC-USDT"].loc[timestamp]
        positive = btc.trend > 0 and btc.momentum > 0
        if positive:
            return target_weights(timestamp, features, base, risk)
        if spec.trigger == "trend":
            hedge = btc.trend < 0
        elif spec.trigger == "confirmed":
            hedge = btc.trend < 0 and btc.momentum < 0
        elif spec.trigger == "either":
            hedge = btc.trend < 0 or btc.momentum < 0
        else:
            raise ValueError("Unsupported short trigger")
        short_weight = min(
            risk.per_asset_cap, risk.max_deployment * spec.hedge_fraction
        )
        return {
            "BTC-USDT": -short_weight if hedge else 0.0,
            "ETH-USDT": 0.0,
        }

    result = _signed_simulation(
        data,
        start,
        end,
        decide,
        initial=initial,
        cost_bps=cost_bps,
        short_carry_annual=short_carry_annual,
    )
    result.update({"spec": spec.as_dict(), "risk": risk.as_dict()})
    return result


def _relative_features(
    daily: dict[str, pd.DataFrame], spec: RelativeValueSpec
) -> pd.DataFrame:
    btc = daily["BTC-USDT"].close.shift(1)
    eth = daily["ETH-USDT"].close.shift(1)
    ratio = np.log(btc / eth)
    mean = ratio.rolling(spec.lookback_days).mean()
    deviation = ratio.rolling(spec.lookback_days).std()
    returns = ratio.diff()
    return pd.DataFrame(
        {
            "zscore": (ratio - mean) / deviation,
            "volatility": returns.rolling(30).std() * np.sqrt(365),
        }
    ).replace([np.inf, -np.inf], np.nan)


def simulate_relative_value(
    data: dict[str, pd.DataFrame],
    spec: RelativeValueSpec,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    risk: DefensiveRisk = DEFAULT_RISK,
    initial: float = INITIAL_CAPITAL,
    cost_bps: float = 15.0,
    short_carry_annual: float = 0.10,
) -> dict:
    daily = prepare_daily(data)
    features = _relative_features(daily, spec)
    state = 0

    def decide(timestamp: pd.Timestamp, _current: dict[str, float]):
        nonlocal state
        due = spec.cadence == "daily" or rebalance_due(timestamp, "weekly")
        if not due:
            return None
        zscore = features.loc[timestamp, "zscore"]
        volatility = features.loc[timestamp, "volatility"]
        if (
            not np.isfinite(zscore)
            or not np.isfinite(volatility)
            or abs(zscore) <= spec.exit_z
        ):
            state = 0
        elif zscore >= spec.entry_z:
            state = -1
        elif zscore <= -spec.entry_z:
            state = 1
        leg_cap = min(risk.per_asset_cap, risk.max_deployment / 2)
        scale = min(1.0, spec.volatility_target / volatility) if volatility > 0 else 0
        leg = leg_cap * scale
        return {
            "BTC-USDT": state * leg,
            "ETH-USDT": -state * leg,
        }

    result = _signed_simulation(
        data,
        start,
        end,
        decide,
        initial=initial,
        cost_bps=cost_bps,
        short_carry_annual=short_carry_annual,
    )
    result.update({"spec": spec.as_dict(), "risk": risk.as_dict()})
    return result


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def put_price(
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    rate: float = 0.03,
) -> float:
    if years <= 0:
        return max(strike - spot, 0.0)
    if spot <= 0 or strike <= 0 or volatility <= 0:
        raise ValueError("Invalid synthetic option input")
    root = volatility * sqrt(years)
    d1 = (log(spot / strike) + (rate + volatility**2 / 2) * years) / root
    d2 = d1 - root
    return strike * exp(-rate * years) * _normal_cdf(-d2) - spot * _normal_cdf(-d1)


@dataclass
class _PutLot:
    quantity: float
    strike: float
    expiry: pd.Timestamp
    volatility: float


def simulate_put_protection(
    data: dict[str, pd.DataFrame],
    spec: PutProtectionSpec,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    risk: DefensiveRisk = DEFAULT_RISK,
    initial: float = INITIAL_CAPITAL,
    cost_bps: float = 15.0,
    volatility_stress: float = 1.0,
) -> dict:
    if volatility_stress < 1:
        raise ValueError("Volatility stress cannot reduce option cost")
    daily = prepare_daily(data)
    base = DefensiveSpec(
        spec.slow_days, spec.momentum_days, "weekly", "btc_gate"
    )
    features = {
        symbol: defensive_features(daily[symbol], base) for symbol in SYMBOLS
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
    quantities = {symbol: 0.0 for symbol in SYMBOLS}
    puts: dict[str, _PutLot | None] = {symbol: None for symbol in SYMBOLS}
    cost_rate = cost_bps / 10_000
    trading_costs = 0.0
    premium_paid = 0.0
    option_sale_value = 0.0
    fills = []
    decisions = []
    points = []

    def option_value(symbol: str, price: float, timestamp: pd.Timestamp) -> float:
        lot = puts[symbol]
        if lot is None:
            return 0.0
        years = max((lot.expiry - timestamp).total_seconds(), 0) / (365 * 86_400)
        return lot.quantity * put_price(
            price, lot.strike, years, lot.volatility
        )

    for timestamp in dates:
        prices = {
            symbol: float(daily[symbol].loc[timestamp, "open"])
            for symbol in SYMBOLS
        }
        old_option_values = {
            symbol: option_value(symbol, prices[symbol], timestamp)
            for symbol in SYMBOLS
        }
        equity = (
            cash
            + sum(quantities[symbol] * prices[symbol] for symbol in SYMBOLS)
            + sum(old_option_values.values())
        )
        if rebalance_due(timestamp, "weekly"):
            close_value = sum(old_option_values.values())
            close_cost = close_value * cost_rate
            option_sale_value += close_value
            trading_costs += close_cost
            targets = target_weights(timestamp, features, base, risk)
            target_notionals = {
                symbol: equity * targets[symbol] for symbol in SYMBOLS
            }
            spot_turnover = sum(
                abs(
                    target_notionals[symbol]
                    - quantities[symbol] * prices[symbol]
                )
                for symbol in SYMBOLS
            )
            spot_cost = spot_turnover * cost_rate
            per_unit_premium = {}
            option_quantities = {}
            for symbol in SYMBOLS:
                volatility = features[symbol].loc[timestamp, "volatility"]
                sigma = (
                    max(float(volatility), 0.10)
                    * spec.volatility_markup
                    * volatility_stress
                    if np.isfinite(volatility)
                    else 0.50 * spec.volatility_markup * volatility_stress
                )
                strike = prices[symbol] * (1 - spec.strike_otm)
                per_unit_premium[symbol] = put_price(
                    prices[symbol],
                    strike,
                    spec.tenor_days / 365,
                    sigma,
                )
                option_quantities[symbol] = (
                    target_notionals[symbol]
                    / prices[symbol]
                    * spec.coverage
                )
            premium = sum(
                option_quantities[symbol] * per_unit_premium[symbol]
                for symbol in SYMBOLS
            )
            option_buy_cost = premium * cost_rate
            required = (
                sum(target_notionals.values())
                + premium
                + spot_cost
                + close_cost
                + option_buy_cost
            )
            scale = min(1.0, equity / required) if required > 0 else 1.0
            target_notionals = {
                symbol: value * scale for symbol, value in target_notionals.items()
            }
            spot_turnover = sum(
                abs(
                    target_notionals[symbol]
                    - quantities[symbol] * prices[symbol]
                )
                for symbol in SYMBOLS
            )
            spot_cost = spot_turnover * cost_rate
            option_quantities = {
                symbol: (
                    target_notionals[symbol]
                    / prices[symbol]
                    * spec.coverage
                )
                for symbol in SYMBOLS
            }
            premium = sum(
                option_quantities[symbol] * per_unit_premium[symbol]
                for symbol in SYMBOLS
            )
            option_buy_cost = premium * cost_rate
            trading_costs += spot_cost + option_buy_cost
            premium_paid += premium
            for symbol in SYMBOLS:
                previous = quantities[symbol] * prices[symbol]
                change = target_notionals[symbol] - previous
                if abs(change) > 0.01:
                    fills.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "instrument": symbol,
                            "kind": "SPOT",
                            "notional_change": change,
                            "cost": abs(change) * cost_rate,
                        }
                    )
                quantities[symbol] = target_notionals[symbol] / prices[symbol]
                if option_quantities[symbol] > 0:
                    volatility = features[symbol].loc[timestamp, "volatility"]
                    sigma = (
                        max(float(volatility), 0.10)
                        * spec.volatility_markup
                        * volatility_stress
                        if np.isfinite(volatility)
                        else 0.50 * spec.volatility_markup * volatility_stress
                    )
                    puts[symbol] = _PutLot(
                        option_quantities[symbol],
                        prices[symbol] * (1 - spec.strike_otm),
                        timestamp + timedelta(days=spec.tenor_days),
                        sigma,
                    )
                    fills.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "instrument": symbol,
                            "kind": "PUT",
                            "premium": option_quantities[symbol]
                            * per_unit_premium[symbol],
                            "cost": option_quantities[symbol]
                            * per_unit_premium[symbol]
                            * cost_rate,
                        }
                    )
                else:
                    puts[symbol] = None
            cash = (
                equity
                - close_cost
                - sum(target_notionals.values())
                - spot_cost
                - premium
                - option_buy_cost
            )
            decisions.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "weights": targets,
                    "scale_for_premium": scale,
                    "premium": premium,
                    "equity_before": equity,
                }
            )
        current_options = sum(
            option_value(symbol, prices[symbol], timestamp) for symbol in SYMBOLS
        )
        equity = (
            cash
            + sum(quantities[symbol] * prices[symbol] for symbol in SYMBOLS)
            + current_options
        )
        points.append(
            {
                "timestamp": timestamp.isoformat(),
                "equity": equity,
                "cash": cash,
                "option_value": current_options,
            }
        )

    final_prices = {
        symbol: float(daily[symbol].loc[dates[-1], "close"]) for symbol in SYMBOLS
    }
    final_options = sum(
        option_value(symbol, final_prices[symbol], dates[-1] + timedelta(hours=23))
        for symbol in SYMBOLS
    )
    ending = (
        cash
        + sum(quantities[symbol] * final_prices[symbol] for symbol in SYMBOLS)
        + final_options
    )
    points.append(
        {
            "timestamp": (dates[-1] + timedelta(hours=23)).isoformat(),
            "equity": ending,
            "cash": cash,
            "option_value": final_options,
        }
    )
    return {
        "spec": spec.as_dict(),
        "risk": risk.as_dict(),
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
        "initial": initial,
        "ending_equity": ending,
        "net_return": ending / initial - 1,
        "same_trade_gross_return": (ending + trading_costs) / initial - 1,
        "max_drawdown": _drawdown(points, initial),
        "fills": fills,
        "fill_count": len(fills),
        "transaction_costs": trading_costs,
        "premium_paid": premium_paid,
        "option_sale_value": option_sale_value,
        "points": points,
        "decisions": decisions,
        "positions": quantities,
    }
