"""Staged diagnostic deepening of the crypto and ETF long/cash tracks."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate_etf_rotation import ALL_SYMBOLS, CAPITAL, RISK_SYMBOLS, load_data
from trader.db import dumps
from trader.growth import defensive as defensive_module
from trader.growth.defensive import (
    DefensiveRisk,
    DefensiveSpec,
    prepare_daily,
    rebalance_due,
)
from trader.growth.regime import load_long_history
from trader.growth.weekly import weekly_report

OUT = Path("research/long_cash_deepening")
PROTOCOL_PATH = OUT / "protocol.json"
CRYPTO_SYMBOLS = ("BTC-USDT", "ETH-USDT")
TREND_WINDOWS = (100, 150, 200)
MOMENTUM_WINDOWS = (30, 90, 180)
CRYPTO_MECHANISMS = (
    "majority_btc_gate",
    "majority_each",
    "unanimous_btc_gate",
    "best_majority",
    "score_each",
    "majority_btc_gate_brake",
    "majority_each_brake",
)


@dataclass(frozen=True)
class CryptoEnsembleSpec:
    mechanism: str
    cadence: str
    volatility_target: float

    @property
    def name(self) -> str:
        return (
            f"{self.mechanism}_{self.cadence}_"
            f"vol{int(self.volatility_target * 100)}"
        )


@dataclass(frozen=True)
class EtfExposureSpec:
    per_asset_cap: float
    max_deployment: float
    volatility_target: float

    @property
    def name(self) -> str:
        return (
            f"asset{int(self.per_asset_cap * 100)}_"
            f"deploy{int(self.max_deployment * 100)}_"
            f"vol{int(self.volatility_target * 100)}"
        )


def crypto_specs() -> tuple[CryptoEnsembleSpec, ...]:
    return tuple(
        CryptoEnsembleSpec(*values)
        for values in itertools.product(
            CRYPTO_MECHANISMS,
            ("weekly", "biweekly", "monthly"),
            (0.20, 0.30, 0.40),
        )
    )


def etf_specs() -> tuple[EtfExposureSpec, ...]:
    profiles = ((0.20, 0.40), (0.25, 0.50), (0.30, 0.60), (0.40, 0.80))
    return tuple(
        EtfExposureSpec(per_asset, deployment, volatility)
        for (per_asset, deployment), volatility in itertools.product(
            profiles, (0.10, 0.15, 0.20, 0.25)
        )
    )


def _protocol() -> tuple[dict, str]:
    raw = PROTOCOL_PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _crypto_data_hashes() -> dict[str, str]:
    result = {}
    for symbol in CRYPTO_SYMBOLS:
        code = symbol.replace("-", "")
        path = Path("research/strategy_v2/data") / f"{code}_1h.csv.gz"
        result[symbol] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _etf_data_hashes() -> dict[str, str]:
    root = Path("research/etf_rotation_challenger/data")
    return {
        symbol: hashlib.sha256((root / f"{symbol}.csv").read_bytes()).hexdigest()
        for symbol in ALL_SYMBOLS
    }


def _drawdown(values: list[float]) -> float:
    array = np.asarray(values, dtype=float)
    return float(np.min(array / np.maximum.accumulate(array) - 1))


def _crypto_features(daily: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    result = {}
    for symbol in CRYPTO_SYMBOLS:
        prior = daily[symbol].close.shift(1)
        frame = pd.DataFrame(index=prior.index)
        votes = pd.Series(0, index=prior.index, dtype=float)
        momentum_sum = pd.Series(0.0, index=prior.index)
        for days in TREND_WINDOWS:
            signal = prior / prior.rolling(days).mean() - 1
            frame[f"trend_{days}"] = signal
            votes += (signal > 0).astype(float)
        for days in MOMENTUM_WINDOWS:
            signal = prior / prior.shift(days) - 1
            frame[f"momentum_{days}"] = signal
            momentum_sum += signal
            votes += (signal > 0).astype(float)
        frame["votes"] = votes
        frame["momentum_average"] = momentum_sum / len(MOMENTUM_WINDOWS)
        frame["volatility"] = prior.pct_change(fill_method=None).rolling(30).std() * np.sqrt(365)
        result[symbol] = frame.replace([np.inf, -np.inf], np.nan)
    return result


def crypto_target_weights(
    timestamp: pd.Timestamp,
    features: dict[str, pd.DataFrame],
    spec: CryptoEnsembleSpec,
    *,
    drawdown: float = 0.0,
) -> dict[str, float]:
    base = spec.mechanism.removesuffix("_brake")
    votes = {
        symbol: float(features[symbol].loc[timestamp, "votes"])
        for symbol in CRYPTO_SYMBOLS
    }
    majority = [symbol for symbol in CRYPTO_SYMBOLS if votes[symbol] >= 4]
    if base == "majority_btc_gate":
        chosen = list(CRYPTO_SYMBOLS) if votes["BTC-USDT"] >= 4 else []
    elif base == "majority_each" or base == "score_each":
        chosen = majority
    elif base == "unanimous_btc_gate":
        chosen = list(CRYPTO_SYMBOLS) if votes["BTC-USDT"] == 6 else []
    elif base == "best_majority":
        chosen = (
            [
                max(
                    majority,
                    key=lambda symbol: features[symbol].loc[
                        timestamp, "momentum_average"
                    ],
                )
            ]
            if majority
            else []
        )
    else:
        raise ValueError("Unknown crypto ensemble mechanism")
    multiplier = 1.0
    if spec.mechanism.endswith("_brake"):
        if drawdown <= -0.10:
            multiplier = 0.0
        elif drawdown <= -0.05:
            multiplier = 0.5
    weights = {}
    for symbol in CRYPTO_SYMBOLS:
        volatility = float(features[symbol].loc[timestamp, "volatility"])
        if symbol not in chosen or not np.isfinite(volatility) or volatility <= 0:
            weights[symbol] = 0.0
            continue
        weight = min(0.20, 0.20 * spec.volatility_target / volatility)
        if base == "score_each":
            weight *= votes[symbol] / 6
        weights[symbol] = float(weight * multiplier)
    total = sum(weights.values())
    if total > 0.40:
        weights = {symbol: weight * 0.40 / total for symbol, weight in weights.items()}
    return weights


def _trade_targets(
    *,
    prices: dict[str, float],
    weights: dict[str, float],
    symbols: tuple[str, ...],
    quantities: dict[str, float],
    cash: float,
    cost_rate: float,
    timestamp: str,
    minimum_order: float,
) -> tuple[float, list[dict]]:
    equity = cash + sum(quantities[symbol] * prices[symbol] for symbol in symbols)
    targets = {symbol: equity * weights.get(symbol, 0.0) for symbol in symbols}
    fills = []
    for symbol in symbols:
        current = quantities[symbol] * prices[symbol]
        difference = current - targets[symbol]
        if difference < minimum_order:
            continue
        notional = min(current, difference)
        fee = notional * cost_rate
        quantities[symbol] -= notional / prices[symbol]
        cash += notional - fee
        fills.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "side": "SELL",
                "notional": notional,
                "cost": fee,
            }
        )
    for symbol in symbols:
        current = quantities[symbol] * prices[symbol]
        difference = targets[symbol] - current
        if difference < minimum_order:
            continue
        notional = min(difference, cash / (1 + cost_rate))
        if notional < minimum_order:
            continue
        fee = notional * cost_rate
        quantities[symbol] += notional / prices[symbol]
        cash -= notional + fee
        fills.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "side": "BUY",
                "notional": notional,
                "cost": fee,
            }
        )
    return cash, fills


def simulate_crypto(
    data: dict[str, pd.DataFrame],
    spec: CryptoEnsembleSpec,
    start: str,
    end: str,
    *,
    cost_bps: float = 15.0,
    execution_delay_days: int = 0,
) -> dict:
    daily = prepare_daily(data)
    features = _crypto_features(daily)
    dates = daily[CRYPTO_SYMBOLS[0]].dropna().index.intersection(
        daily[CRYPTO_SYMBOLS[1]].dropna().index
    )
    dates = dates[
        (dates >= pd.to_datetime(start, utc=True))
        & (dates <= pd.to_datetime(end, utc=True))
    ]
    if not len(dates):
        raise ValueError("No crypto observations")
    cash = CAPITAL
    quantities = {symbol: 0.0 for symbol in CRYPTO_SYMBOLS}
    fills = []
    decisions = []
    points = []
    pending: list[tuple[int, dict[str, float]]] = []
    peak = CAPITAL
    for index, timestamp in enumerate(dates):
        prices = {
            symbol: float(daily[symbol].loc[timestamp, "open"])
            for symbol in CRYPTO_SYMBOLS
        }
        due = [item for item in pending if item[0] == index]
        pending = [item for item in pending if item[0] != index]
        for _, weights in due:
            cash, new_fills = _trade_targets(
                prices=prices,
                weights=weights,
                symbols=CRYPTO_SYMBOLS,
                quantities=quantities,
                cash=cash,
                cost_rate=cost_bps / 10_000,
                timestamp=timestamp.isoformat(),
                minimum_order=0.01,
            )
            fills.extend(new_fills)
        equity_open = cash + sum(
            quantities[symbol] * prices[symbol] for symbol in CRYPTO_SYMBOLS
        )
        peak = max(peak, equity_open)
        if rebalance_due(timestamp, spec.cadence):
            weights = crypto_target_weights(
                timestamp, features, spec, drawdown=equity_open / peak - 1
            )
            decisions.append(
                {"timestamp": timestamp.isoformat(), "weights": weights}
            )
            if execution_delay_days:
                if index + execution_delay_days < len(dates):
                    pending.append((index + execution_delay_days, weights))
            else:
                cash, new_fills = _trade_targets(
                    prices=prices,
                    weights=weights,
                    symbols=CRYPTO_SYMBOLS,
                    quantities=quantities,
                    cash=cash,
                    cost_rate=cost_bps / 10_000,
                    timestamp=timestamp.isoformat(),
                    minimum_order=0.01,
                )
                fills.extend(new_fills)
        closes = {
            symbol: float(daily[symbol].loc[timestamp, "close"])
            for symbol in CRYPTO_SYMBOLS
        }
        equity = cash + sum(
            quantities[symbol] * closes[symbol] for symbol in CRYPTO_SYMBOLS
        )
        peak = max(peak, equity)
        points.append(
            {"timestamp": timestamp.isoformat(), "equity": equity, "cash": cash}
        )
    ending = float(points[-1]["equity"])
    return {
        "name": spec.name,
        "spec": asdict(spec),
        "initial": CAPITAL,
        "ending_equity": ending,
        "net_return": ending / CAPITAL - 1,
        "max_drawdown": _drawdown([CAPITAL, *[point["equity"] for point in points]]),
        "fill_count": len(fills),
        "sell_count": sum(fill["side"] == "SELL" for fill in fills),
        "transaction_costs": float(sum(fill["cost"] for fill in fills)),
        "fills": fills,
        "decisions": decisions,
        "points": points,
    }


def etf_target_weights(
    data: dict[str, pd.DataFrame],
    decision_date: pd.Timestamp,
    spec: EtfExposureSpec,
    *,
    excluded: str | None = None,
) -> tuple[dict[str, float], dict]:
    shy = data["SHY"].loc[data["SHY"].index < decision_date, "close"]
    if len(shy) < 252:
        raise ValueError("Insufficient lagged ETF history")
    shy_momentum = float(shy.iloc[-1] / shy.iloc[-252] - 1)
    features = {}
    eligible = []
    for symbol in RISK_SYMBOLS:
        closes = data[symbol].loc[data[symbol].index < decision_date, "close"]
        if len(closes) < 252:
            raise ValueError("Insufficient lagged ETF history")
        momentum = float(closes.iloc[-1] / closes.iloc[-252] - 1)
        trend = float(closes.iloc[-1] / closes.iloc[-200:].mean() - 1)
        volatility = float(closes.pct_change().iloc[-30:].std() * np.sqrt(252))
        valid = (
            symbol != excluded
            and momentum > 0
            and trend > 0
            and momentum > shy_momentum
        )
        features[symbol] = {
            "momentum": momentum,
            "trend": trend,
            "volatility": volatility,
            "eligible": bool(valid),
        }
        if valid:
            eligible.append(symbol)
    selected = sorted(
        eligible, key=lambda symbol: features[symbol]["momentum"], reverse=True
    )[:2]
    weights = {symbol: 0.0 for symbol in RISK_SYMBOLS}
    for symbol in selected:
        volatility = features[symbol]["volatility"]
        weights[symbol] = min(
            spec.per_asset_cap,
            spec.per_asset_cap * spec.volatility_target / volatility,
        )
    total = sum(weights.values())
    if total > spec.max_deployment:
        weights = {
            symbol: weight * spec.max_deployment / total
            for symbol, weight in weights.items()
        }
    return weights, {"selected": selected, "assets": features}


def simulate_etf(
    data: dict[str, pd.DataFrame],
    spec: EtfExposureSpec,
    start: str,
    end: str,
    *,
    cost_bps: float = 15.0,
    delay_sessions: int = 0,
    minimum_order: float = 1.0,
    excluded: str | None = None,
) -> dict:
    dates = data["SPY"].index
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    if not len(dates):
        raise ValueError("No ETF sessions")
    cash = CAPITAL
    quantities = {symbol: 0.0 for symbol in RISK_SYMBOLS}
    fills = []
    decisions = []
    points = []
    pending: list[tuple[int, dict[str, float]]] = []
    previous_month = None
    for index, date in enumerate(dates):
        prices = {
            symbol: float(data[symbol].loc[date, "open"])
            for symbol in RISK_SYMBOLS
        }
        due = [item for item in pending if item[0] == index]
        pending = [item for item in pending if item[0] != index]
        for _, weights in due:
            cash, new_fills = _trade_targets(
                prices=prices,
                weights=weights,
                symbols=RISK_SYMBOLS,
                quantities=quantities,
                cash=cash,
                cost_rate=cost_bps / 10_000,
                timestamp=date.date().isoformat(),
                minimum_order=minimum_order,
            )
            fills.extend(new_fills)
        month = (date.year, date.month)
        if month != previous_month:
            previous_month = month
            try:
                weights, features = etf_target_weights(
                    data, date, spec, excluded=excluded
                )
            except ValueError as exc:
                if not str(exc).startswith("Insufficient lagged ETF history"):
                    raise
                weights = {symbol: 0.0 for symbol in RISK_SYMBOLS}
                features = {"selected": [], "reason": "warmup"}
            decisions.append(
                {
                    "timestamp": date.date().isoformat(),
                    "weights": weights,
                    "features": features,
                }
            )
            if delay_sessions:
                if index + delay_sessions < len(dates):
                    pending.append((index + delay_sessions, weights))
            else:
                cash, new_fills = _trade_targets(
                    prices=prices,
                    weights=weights,
                    symbols=RISK_SYMBOLS,
                    quantities=quantities,
                    cash=cash,
                    cost_rate=cost_bps / 10_000,
                    timestamp=date.date().isoformat(),
                    minimum_order=minimum_order,
                )
                fills.extend(new_fills)
        closes = {
            symbol: float(data[symbol].loc[date, "close"])
            for symbol in RISK_SYMBOLS
        }
        equity = cash + sum(
            quantities[symbol] * closes[symbol] for symbol in RISK_SYMBOLS
        )
        points.append(
            {
                "timestamp": pd.Timestamp(date).tz_localize("UTC").isoformat(),
                "equity": equity,
                "cash": cash,
            }
        )
    ending = float(points[-1]["equity"])
    return {
        "name": spec.name,
        "spec": asdict(spec),
        "initial": CAPITAL,
        "ending_equity": ending,
        "net_return": ending / CAPITAL - 1,
        "max_drawdown": _drawdown([CAPITAL, *[point["equity"] for point in points]]),
        "fill_count": len(fills),
        "sell_count": sum(fill["side"] == "SELL" for fill in fills),
        "transaction_costs": float(sum(fill["cost"] for fill in fills)),
        "fills": fills,
        "decisions": decisions,
        "points": points,
    }


def _brief(result: dict) -> dict:
    brief = {
        key: result[key]
        for key in (
            "initial",
            "ending_equity",
            "net_return",
            "max_drawdown",
            "fill_count",
            "sell_count",
            "transaction_costs",
        )
    }
    brief["name"] = result.get("name") or result.get("spec")
    return brief


def _calendar_years(simulator, data, spec, start: str, end: str) -> dict[str, float]:
    result = {}
    start_at = pd.Timestamp(start)
    end_at = pd.Timestamp(end)
    if start_at.tz is not None or end_at.tz is not None:
        start_at = pd.to_datetime(start, utc=True)
        end_at = pd.to_datetime(end, utc=True)
    timezone = start_at.tz
    for year in range(start_at.year, end_at.year + 1):
        year_start = pd.Timestamp(f"{year}-01-01", tz=timezone)
        year_end = pd.Timestamp(f"{year}-12-31 23:59:59", tz=timezone)
        lower = max(start_at, year_start)
        upper = min(end_at, year_end)
        result[str(year)] = simulator(
            data, spec, str(lower.date()), str(upper.date())
        )["net_return"]
    return result


def _select_crypto(protocol: dict, protocol_hash: str) -> dict:
    partitions = protocol["crypto_long_cash"]["partitions"]
    data = {symbol: load_long_history(symbol) for symbol in CRYPTO_SYMBOLS}
    trials = []
    eligible = []
    for spec in crypto_specs():
        dev = simulate_crypto(data, spec, *partitions["development"])
        val = simulate_crypto(data, spec, *partitions["validation"])
        dev_stress = simulate_crypto(
            data, spec, *partitions["development"], cost_bps=30
        )
        val_stress = simulate_crypto(
            data, spec, *partitions["validation"], cost_bps=30
        )
        years = _calendar_years(
            simulate_crypto, data, spec, *partitions["validation"]
        )
        passed = (
            min(
                dev["net_return"],
                val["net_return"],
                dev_stress["net_return"],
                val_stress["net_return"],
            )
            > 0
            and min(dev["max_drawdown"], val["max_drawdown"]) >= -0.20
            and min(dev["fill_count"], val["fill_count"]) >= 8
        )
        row = {
            "name": spec.name,
            "spec": asdict(spec),
            "development": _brief(dev),
            "development_cost_2x": _brief(dev_stress),
            "validation": _brief(val),
            "validation_cost_2x": _brief(val_stress),
            "validation_calendar_year_returns": years,
            "minimum_validation_year": min(years.values()),
            "eligible": bool(passed),
        }
        trials.append(row)
        if passed:
            eligible.append(row)
    (OUT / "crypto_trials.json").write_text(dumps(trials) + "\n")
    if not eligible:
        lock = {
            "selected": None,
            "eligible_count": 0,
            "reason": "No crypto extension passed",
        }
    else:
        winner = max(
            eligible,
            key=lambda row: (
                row["minimum_validation_year"],
                row["validation"]["net_return"],
                row["validation"]["max_drawdown"],
            ),
        )
        lock = {
            "selected": winner["name"],
            "selected_spec": winner["spec"],
            "eligible_count": len(eligible),
            "selection_evidence": winner,
        }
    lock.update(
        {
            "protocol_sha256": protocol_hash,
            "data_sha256": _crypto_data_hashes(),
            "evaluation_opened": False,
        }
    )
    (OUT / "crypto_selection_locked.json").write_text(dumps(lock) + "\n")
    return lock


def _select_etf(protocol: dict, protocol_hash: str) -> dict:
    partitions = protocol["etf_long_cash"]["partitions"]
    data = load_data()
    trials = []
    eligible = []
    for spec in etf_specs():
        dev = simulate_etf(data, spec, *partitions["development"])
        val = simulate_etf(data, spec, *partitions["validation"])
        dev_stress = simulate_etf(
            data, spec, *partitions["development"], cost_bps=30
        )
        val_stress = simulate_etf(
            data, spec, *partitions["validation"], cost_bps=30
        )
        years = _calendar_years(simulate_etf, data, spec, *partitions["validation"])
        passed = (
            min(
                dev["net_return"],
                val["net_return"],
                dev_stress["net_return"],
                val_stress["net_return"],
            )
            > 0
            and min(dev["max_drawdown"], val["max_drawdown"]) >= -0.20
            and min(years.values()) > -0.10
            and min(dev["fill_count"], val["fill_count"]) >= 8
        )
        ratio = val["net_return"] / max(abs(val["max_drawdown"]), 1e-9)
        row = {
            "name": spec.name,
            "spec": asdict(spec),
            "development": _brief(dev),
            "development_cost_2x": _brief(dev_stress),
            "validation": _brief(val),
            "validation_cost_2x": _brief(val_stress),
            "validation_calendar_year_returns": years,
            "minimum_validation_year": min(years.values()),
            "validation_return_drawdown_ratio": ratio,
            "eligible": bool(passed),
        }
        trials.append(row)
        if passed:
            eligible.append(row)
    (OUT / "etf_trials.json").write_text(dumps(trials) + "\n")
    if not eligible:
        lock = {
            "selected": None,
            "eligible_count": 0,
            "reason": "No ETF extension passed",
        }
    else:
        winner = max(
            eligible,
            key=lambda row: (
                row["validation_return_drawdown_ratio"],
                row["minimum_validation_year"],
                row["validation"]["net_return"],
            ),
        )
        lock = {
            "selected": winner["name"],
            "selected_spec": winner["spec"],
            "eligible_count": len(eligible),
            "selection_evidence": winner,
        }
    lock.update(
        {
            "protocol_sha256": protocol_hash,
            "data_sha256": _etf_data_hashes(),
            "evaluation_opened": False,
        }
    )
    (OUT / "etf_selection_locked.json").write_text(dumps(lock) + "\n")
    return lock


def select() -> dict:
    protocol, protocol_hash = _protocol()
    return {
        "crypto": _select_crypto(protocol, protocol_hash),
        "etf": _select_etf(protocol, protocol_hash),
    }


def _verify_lock(lock: dict, protocol_hash: str, hashes: dict[str, str]) -> None:
    if lock["protocol_sha256"] != protocol_hash:
        raise ValueError("Deepening protocol changed after selection")
    if lock["data_sha256"] != hashes:
        raise ValueError("Deepening data changed after selection")
    if not lock.get("selected"):
        raise ValueError("No selected extension")


def _window_rows(simulator, data, spec, start: str, end: str) -> list[dict]:
    rows = []
    lower = pd.Timestamp(start)
    final = pd.Timestamp(end)
    while lower + pd.DateOffset(months=2) <= final + pd.Timedelta(days=1):
        upper = lower + pd.DateOffset(months=2) - pd.Timedelta(days=1)
        result = simulator(data, spec, str(lower.date()), str(upper.date()))
        rows.append(
            {
                "window": f"{lower.date()} to {upper.date()}",
                "net_return": result["net_return"],
                "profit_usd": result["ending_equity"] - CAPITAL,
                "max_drawdown": result["max_drawdown"],
                "fills": result["fill_count"],
            }
        )
        lower += pd.DateOffset(months=2)
    return rows


def _window_summary(rows: list[dict]) -> dict:
    returns = np.asarray([row["net_return"] for row in rows])
    drawdowns = np.asarray([row["max_drawdown"] for row in rows])
    return {
        "windows": len(rows),
        "profitable": int((returns > 0).sum()),
        "losing": int((returns < 0).sum()),
        "flat": int((returns == 0).sum()),
        "average_return": float(returns.mean()),
        "average_profit_usd": float(returns.mean() * CAPITAL),
        "average_drawdown": float(drawdowns.mean()),
        "worst_drawdown": float(drawdowns.min()),
        "best_return": float(returns.max()),
        "worst_return": float(returns.min()),
    }


def _passive_etf(data: dict[str, pd.DataFrame], deployment: float, start: str, end: str) -> dict:
    dates = data["SPY"].index
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    notional = CAPITAL * deployment
    cost = notional * 15 / 10_000
    quantity = notional / float(data["SPY"].loc[dates[0], "open"])
    cash = CAPITAL - notional - cost
    values = [
        cash + quantity * float(data["SPY"].loc[date, "close"]) for date in dates
    ]
    return {
        "deployment": deployment,
        "ending_equity": values[-1],
        "net_return": values[-1] / CAPITAL - 1,
        "max_drawdown": _drawdown([CAPITAL, *values]),
        "transaction_costs": cost,
    }


def _evaluate_crypto(protocol: dict, protocol_hash: str) -> dict:
    lock_path = OUT / "crypto_selection_locked.json"
    lock = json.loads(lock_path.read_text())
    _verify_lock(lock, protocol_hash, _crypto_data_hashes())
    partitions = protocol["crypto_long_cash"]["partitions"]
    data = {symbol: load_long_history(symbol) for symbol in CRYPTO_SYMBOLS}
    spec = CryptoEnsembleSpec(**lock["selected_spec"])
    evaluation = simulate_crypto(data, spec, *partitions["diagnostic_evaluation"])
    cost_2x = simulate_crypto(
        data, spec, *partitions["diagnostic_evaluation"], cost_bps=30
    )
    cost_4x = simulate_crypto(
        data, spec, *partitions["diagnostic_evaluation"], cost_bps=60
    )
    delay = simulate_crypto(
        data,
        spec,
        *partitions["diagnostic_evaluation"],
        execution_delay_days=1,
    )
    frozen = defensive_module.simulate(
        data,
        DefensiveSpec(100, 90, "weekly", "btc_gate"),
        *partitions["diagnostic_evaluation"],
        risk=DefensiveRisk(0.20, 0.40, 0.30),
    )
    windows = _window_rows(
        simulate_crypto, data, spec, "2022-01-01", "2026-10-31"
    )
    pd.DataFrame(windows).to_csv(OUT / "crypto_two_month_windows.csv", index=False)
    weekly = weekly_report(
        evaluation["points"], CAPITAL, evaluation["sell_count"], cost_4x["net_return"] > 0
    )
    (OUT / "crypto_evaluation_detail.json").write_text(
        dumps(
            {
                "selected": spec.name,
                "evaluation": {
                    key: evaluation[key]
                    for key in ("points", "fills", "decisions")
                },
                "cost_4x": {
                    key: cost_4x[key] for key in ("points", "fills", "decisions")
                },
                "delay_1_day": {
                    key: delay[key] for key in ("points", "fills", "decisions")
                },
            }
        )
        + "\n"
    )
    stronger = (
        evaluation["net_return"] > frozen["net_return"]
        and evaluation["max_drawdown"] >= -0.20
        and cost_4x["net_return"] > 0
        and delay["net_return"] > 0
    )
    result = {
        "selected": spec.name,
        "selected_spec": asdict(spec),
        "eligible_count": lock["eligible_count"],
        "evaluation": _brief(evaluation),
        "cost_2x": _brief(cost_2x),
        "cost_4x": _brief(cost_4x),
        "delay_1_day": _brief(delay),
        "frozen_comparison": _brief(frozen),
        "calendar_years": _calendar_years(
            simulate_crypto, data, spec, *partitions["diagnostic_evaluation"]
        ),
        "two_month_windows": _window_summary(windows),
        "weekly": weekly,
        "historically_stronger": stronger,
        "decision": (
            "separate prospective challenger warranted"
            if stronger
            else "retain frozen crypto candidate; extension rejected"
        ),
    }
    lock["evaluation_opened"] = True
    lock_path.write_text(dumps(lock) + "\n")
    return result


def _evaluate_etf(protocol: dict, protocol_hash: str) -> dict:
    lock_path = OUT / "etf_selection_locked.json"
    lock = json.loads(lock_path.read_text())
    _verify_lock(lock, protocol_hash, _etf_data_hashes())
    partitions = protocol["etf_long_cash"]["partitions"]
    dates = partitions["diagnostic_evaluation"]
    data = load_data()
    spec = EtfExposureSpec(**lock["selected_spec"])
    evaluation = simulate_etf(data, spec, *dates)
    cost_2x = simulate_etf(data, spec, *dates, cost_bps=30)
    cost_4x = simulate_etf(data, spec, *dates, cost_bps=60)
    delay_1 = simulate_etf(data, spec, *dates, delay_sessions=1)
    delay_3 = simulate_etf(data, spec, *dates, delay_sessions=3)
    minimum_10 = simulate_etf(data, spec, *dates, minimum_order=10)
    removals = {
        symbol: _brief(simulate_etf(data, spec, *dates, excluded=symbol))
        for symbol in RISK_SYMBOLS
    }
    frozen_spec = EtfExposureSpec(0.20, 0.40, 0.15)
    frozen = simulate_etf(data, frozen_spec, *dates)
    windows = _window_rows(simulate_etf, data, spec, "2022-01-01", "2026-10-30")
    pd.DataFrame(windows).to_csv(OUT / "etf_two_month_windows.csv", index=False)
    weekly = weekly_report(
        evaluation["points"], CAPITAL, evaluation["sell_count"], cost_4x["net_return"] > 0
    )
    (OUT / "etf_evaluation_detail.json").write_text(
        dumps(
            {
                "selected": spec.name,
                "evaluation": {
                    key: evaluation[key]
                    for key in ("points", "fills", "decisions")
                },
                "cost_4x": {
                    key: cost_4x[key] for key in ("points", "fills", "decisions")
                },
                "delay_3_sessions": {
                    key: delay_3[key] for key in ("points", "fills", "decisions")
                },
            }
        )
        + "\n"
    )
    removal_positive = all(row["net_return"] > 0 for row in removals.values())
    stronger = (
        evaluation["net_return"] > frozen["net_return"]
        and evaluation["max_drawdown"] >= -0.20
        and cost_4x["net_return"] > 0
        and delay_3["net_return"] > 0
        and removal_positive
    )
    result = {
        "selected": spec.name,
        "selected_spec": asdict(spec),
        "eligible_count": lock["eligible_count"],
        "evaluation": _brief(evaluation),
        "cost_2x": _brief(cost_2x),
        "cost_4x": _brief(cost_4x),
        "delay_1_session": _brief(delay_1),
        "delay_3_sessions": _brief(delay_3),
        "minimum_order_10": _brief(minimum_10),
        "asset_removals": removals,
        "all_asset_removals_positive": removal_positive,
        "frozen_comparison": _brief(frozen),
        "spy_40": _passive_etf(data, 0.40, *dates),
        "spy_selected_exposure": _passive_etf(data, spec.max_deployment, *dates),
        "calendar_years": _calendar_years(simulate_etf, data, spec, *dates),
        "two_month_windows": _window_summary(windows),
        "weekly": weekly,
        "historically_stronger": stronger,
        "decision": (
            "separate prospective challenger warranted"
            if stronger
            else "retain frozen ETF candidate; extension rejected"
        ),
    }
    lock["evaluation_opened"] = True
    lock_path.write_text(dumps(lock) + "\n")
    return result


def _write_report(summary: dict) -> None:
    crypto = summary["crypto"]
    etf = summary["etf"]
    lines = [
        "# Long/cash deepening — results",
        "",
        "Both tracks remain long-only with a cash fallback. Historical partitions",
        "were already inspected, so these are diagnostic improvements rather than",
        "fresh holdouts.",
        "",
        "## Crypto long/cash",
        "",
        f"Selected `{crypto['selected']}` from {crypto['eligible_count']} eligible configurations.",
        "",
        "| Scenario | Return | Drawdown | Ending value |",
        "|---|---:|---:|---:|",
    ]
    for name in ("evaluation", "cost_2x", "cost_4x", "delay_1_day", "frozen_comparison"):
        row = crypto[name]
        lines.append(
            f"| {name.replace('_', ' ')} | {row['net_return']:.2%} | "
            f"{row['max_drawdown']:.2%} | ${row['ending_equity']:.2f} |"
        )
    cw = crypto["two_month_windows"]
    lines.extend(
        [
            "",
            (
                f"Two-month resets: {cw['profitable']} profitable, "
                f"{cw['losing']} losing, {cw['flat']} flat; average "
                f"{cw['average_return']:.2%} (${cw['average_profit_usd']:.2f})."
            ),
            f"Calendar-year resets: {crypto['calendar_years']}.",
            (
                "Lower 95% weekly-mean bound: "
                f"{crypto['weekly']['mean_weekly_return_lower_95']:.3%}."
            ),
            f"Decision: **{crypto['decision']}**.",
            "",
            "## ETF long/cash",
            "",
            f"Selected `{etf['selected']}` from {etf['eligible_count']} eligible configurations.",
            "",
            "| Scenario | Return | Drawdown | Ending value |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in (
        "evaluation",
        "cost_2x",
        "cost_4x",
        "delay_1_session",
        "delay_3_sessions",
        "minimum_order_10",
        "frozen_comparison",
    ):
        row = etf[name]
        lines.append(
            f"| {name.replace('_', ' ')} | {row['net_return']:.2%} | "
            f"{row['max_drawdown']:.2%} | ${row['ending_equity']:.2f} |"
        )
    ew = etf["two_month_windows"]
    lines.extend(
        [
            "",
            (
                f"Two-month resets: {ew['profitable']} profitable, "
                f"{ew['losing']} losing, {ew['flat']} flat; average "
                f"{ew['average_return']:.2%} (${ew['average_profit_usd']:.2f})."
            ),
            (
                f"The 40%-SPY/cash comparison returned "
                f"{etf['spy_40']['net_return']:.2%} with "
                f"{etf['spy_40']['max_drawdown']:.2%} drawdown."
            ),
            f"Calendar-year resets: {etf['calendar_years']}.",
            (
                "Lower 95% weekly-mean bound: "
                f"{etf['weekly']['mean_weekly_return_lower_95']:.3%}."
            ),
            f"All single-asset removal tests remained profitable: **{etf['all_asset_removals_positive']}**.",
            f"Decision: **{etf['decision']}**.",
            "",
            "## Boundary",
            "",
            "Higher exposure is not a new source of alpha. Results must be read with",
            "their drawdown, passive SPY/cash comparison, cost and delay stresses.",
            "Neither result changes the running forward account or authorizes broker",
            "orders. A historically stronger extension requires a separate prospective",
            "record before any deployment decision.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines))


def evaluate() -> dict:
    protocol, protocol_hash = _protocol()
    summary = {
        "protocol_sha256": protocol_hash,
        "crypto": _evaluate_crypto(protocol, protocol_hash),
        "etf": _evaluate_etf(protocol, protocol_hash),
        "broker_orders_submitted": 0,
    }
    (OUT / "summary.json").write_text(dumps(summary) + "\n")
    summary_hash = hashlib.sha256((OUT / "summary.json").read_bytes()).hexdigest()
    for name in ("crypto", "etf"):
        path = OUT / f"{name}_selection_locked.json"
        lock = json.loads(path.read_text())
        lock["evaluation_summary_sha256"] = summary_hash
        path.write_text(dumps(lock) + "\n")
    _write_report(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("select", "evaluate"))
    args = parser.parse_args()
    result = select() if args.stage == "select" else evaluate()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
