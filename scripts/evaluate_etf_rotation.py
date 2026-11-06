"""Predeclared liquid-ETF rotation challenger with staged evaluation."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from trader.data import MarketData
from trader.db import dumps
from trader.growth.weekly import weekly_report

OUT = Path("research/etf_rotation_challenger")
DATA = OUT / "data"
PROTOCOL_PATH = OUT / "protocol.json"
SELECTION_PATH = OUT / "selection_locked.json"
RISK_SYMBOLS = ("SPY", "QQQ", "IWM", "GLD", "TLT")
ALL_SYMBOLS = (*RISK_SYMBOLS, "SHY")
CAPITAL = 500.0
MAX_ASSET = 0.20
MAX_DEPLOYMENT = 0.40
MIN_ORDER = 1.0


@dataclass(frozen=True)
class RotationSpec:
    lookback: int
    trend_days: int
    top_n: int
    volatility_target: float

    @property
    def name(self) -> str:
        return (
            f"mom{self.lookback}_sma{self.trend_days}_top{self.top_n}_"
            f"vol{int(self.volatility_target * 100)}"
        )


def specifications() -> tuple[RotationSpec, ...]:
    return tuple(
        RotationSpec(*values)
        for values in itertools.product((126, 252), (150, 200), (1, 2), (0.15, 0.25))
    )


def _protocol() -> tuple[dict, str]:
    raw = PROTOCOL_PATH.read_bytes()
    protocol = json.loads(raw)
    return protocol, hashlib.sha256(raw).hexdigest()


def _data_hashes() -> dict[str, str]:
    return {
        symbol: hashlib.sha256((DATA / f"{symbol}.csv").read_bytes()).hexdigest()
        for symbol in ALL_SYMBOLS
    }


def load_data() -> dict[str, pd.DataFrame]:
    data = MarketData(DATA).load(list(ALL_SYMBOLS))
    common = None
    for frame in data.values():
        common = frame.index if common is None else common.intersection(frame.index)
    if common is None or len(common) < 500:
        raise ValueError("Insufficient common ETF history")
    return {symbol: frame.loc[common].copy() for symbol, frame in data.items()}


def target_weights(
    data: dict[str, pd.DataFrame], decision_date: pd.Timestamp, spec: RotationSpec
) -> tuple[dict[str, float], dict]:
    """Use completed prior closes only; return capped target weights and features."""

    decision_date = pd.Timestamp(decision_date)
    features = {}
    shy = data["SHY"].loc[data["SHY"].index < decision_date, "close"]
    if len(shy) < max(spec.lookback, spec.trend_days, 31):
        raise ValueError("Insufficient lagged ETF history")
    shy_momentum = float(shy.iloc[-1] / shy.iloc[-spec.lookback] - 1)
    eligible = []
    for symbol in RISK_SYMBOLS:
        closes = data[symbol].loc[data[symbol].index < decision_date, "close"]
        if len(closes) < max(spec.lookback, spec.trend_days, 31):
            raise ValueError("Insufficient lagged ETF history")
        momentum = float(closes.iloc[-1] / closes.iloc[-spec.lookback] - 1)
        trend = float(closes.iloc[-1] / closes.iloc[-spec.trend_days :].mean() - 1)
        volatility = float(closes.pct_change().iloc[-30:].std() * np.sqrt(252))
        if not np.isfinite([momentum, trend, volatility]).all() or volatility <= 0:
            raise ValueError("Invalid ETF feature")
        is_eligible = momentum > 0 and trend > 0 and momentum > shy_momentum
        features[symbol] = {
            "momentum": momentum,
            "trend": trend,
            "volatility": volatility,
            "eligible": bool(is_eligible),
        }
        if is_eligible:
            eligible.append(symbol)
    selected = sorted(
        eligible, key=lambda symbol: features[symbol]["momentum"], reverse=True
    )[: spec.top_n]
    weights = {symbol: 0.0 for symbol in RISK_SYMBOLS}
    for symbol in selected:
        weights[symbol] = min(
            MAX_ASSET,
            MAX_ASSET * spec.volatility_target / features[symbol]["volatility"],
        )
    total = sum(weights.values())
    if total > MAX_DEPLOYMENT:
        weights = {
            symbol: weight * MAX_DEPLOYMENT / total
            for symbol, weight in weights.items()
        }
    return weights, {
        "shy_momentum": shy_momentum,
        "selected": selected,
        "assets": features,
    }


def _drawdown(values: list[float]) -> float:
    array = np.asarray(values, dtype=float)
    return float(np.min(array / np.maximum.accumulate(array) - 1))


def simulate(
    data: dict[str, pd.DataFrame],
    spec: RotationSpec,
    start: str,
    end: str,
    *,
    cost_bps: float = 15.0,
) -> dict:
    common = data["SPY"].index
    dates = common[(common >= pd.Timestamp(start)) & (common <= pd.Timestamp(end))]
    if not len(dates):
        raise ValueError("No ETF sessions in requested period")
    cost_rate = cost_bps / 10_000
    cash = CAPITAL
    quantities = {symbol: 0.0 for symbol in RISK_SYMBOLS}
    points = []
    fills = []
    decisions = []
    total_costs = 0.0
    gross_turnover = 0.0
    previous_month = None
    for date in dates:
        opens = {symbol: float(data[symbol].loc[date, "open"]) for symbol in RISK_SYMBOLS}
        month = (date.year, date.month)
        if month != previous_month:
            previous_month = month
            try:
                weights, features = target_weights(data, date, spec)
            except ValueError as exc:
                if not str(exc).startswith("Insufficient lagged ETF history"):
                    raise
                weights = {symbol: 0.0 for symbol in RISK_SYMBOLS}
                features = {
                    "selected": [],
                    "reason": "Full declared warmup not yet available; hold cash",
                }
            equity_open = cash + sum(
                quantities[symbol] * opens[symbol] for symbol in RISK_SYMBOLS
            )
            targets = {
                symbol: equity_open * weights[symbol] for symbol in RISK_SYMBOLS
            }
            # Reductions settle immediately in this research model; all sales precede buys.
            for symbol in RISK_SYMBOLS:
                current = quantities[symbol] * opens[symbol]
                difference = current - targets[symbol]
                if difference < MIN_ORDER:
                    continue
                quantity = min(quantities[symbol], difference / opens[symbol])
                notional = quantity * opens[symbol]
                fee = notional * cost_rate
                quantities[symbol] -= quantity
                cash += notional - fee
                total_costs += fee
                gross_turnover += notional
                fills.append(
                    {
                        "date": date.date().isoformat(),
                        "symbol": symbol,
                        "side": "SELL",
                        "quantity": quantity,
                        "price": opens[symbol],
                        "notional": notional,
                        "cost": fee,
                    }
                )
            for symbol in RISK_SYMBOLS:
                current = quantities[symbol] * opens[symbol]
                difference = targets[symbol] - current
                if difference < MIN_ORDER:
                    continue
                affordable = cash / (1 + cost_rate)
                notional = min(difference, affordable)
                if notional < MIN_ORDER:
                    continue
                quantity = notional / opens[symbol]
                fee = notional * cost_rate
                quantities[symbol] += quantity
                cash -= notional + fee
                total_costs += fee
                gross_turnover += notional
                fills.append(
                    {
                        "date": date.date().isoformat(),
                        "symbol": symbol,
                        "side": "BUY",
                        "quantity": quantity,
                        "price": opens[symbol],
                        "notional": notional,
                        "cost": fee,
                    }
                )
            decisions.append(
                {
                    "date": date.date().isoformat(),
                    "weights": weights,
                    "features": features,
                }
            )
        closes = {
            symbol: float(data[symbol].loc[date, "close"]) for symbol in RISK_SYMBOLS
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
    values = [CAPITAL, *[point["equity"] for point in points]]
    return {
        "spec": asdict(spec),
        "name": spec.name,
        "start": str(dates[0].date()),
        "end": str(dates[-1].date()),
        "initial": CAPITAL,
        "ending_equity": ending,
        "net_return": ending / CAPITAL - 1,
        "max_drawdown": _drawdown(values),
        "fill_count": len(fills),
        "sell_count": sum(fill["side"] == "SELL" for fill in fills),
        "transaction_costs": total_costs,
        "turnover": gross_turnover / CAPITAL,
        "cash": cash,
        "positions": quantities,
        "points": points,
        "fills": fills,
        "decisions": decisions,
    }


def _brief(result: dict) -> dict:
    keys = (
        "name",
        "start",
        "end",
        "initial",
        "ending_equity",
        "net_return",
        "max_drawdown",
        "fill_count",
        "sell_count",
        "transaction_costs",
        "turnover",
    )
    return {key: result[key] for key in keys}


def _calendar_years(
    data: dict[str, pd.DataFrame], spec: RotationSpec, start: str, end: str
) -> dict[str, float]:
    first = pd.Timestamp(start).year
    last = pd.Timestamp(end).year
    returns = {}
    for year in range(first, last + 1):
        lower = max(pd.Timestamp(start), pd.Timestamp(f"{year}-01-01"))
        upper = min(pd.Timestamp(end), pd.Timestamp(f"{year}-12-31"))
        returns[str(year)] = simulate(
            data, spec, str(lower.date()), str(upper.date())
        )["net_return"]
    return returns


def select() -> dict:
    protocol, protocol_hash = _protocol()
    data = load_data()
    development = protocol["partitions"]["development"]
    validation = protocol["partitions"]["validation"]
    trials = []
    eligible = []
    for spec in specifications():
        dev = simulate(data, spec, *development)
        dev_stress = simulate(data, spec, *development, cost_bps=30)
        val = simulate(data, spec, *validation)
        val_stress = simulate(data, spec, *validation, cost_bps=30)
        years = _calendar_years(data, spec, *validation)
        passed = (
            dev["net_return"] > 0
            and val["net_return"] > 0
            and dev_stress["net_return"] > 0
            and val_stress["net_return"] > 0
            and dev["max_drawdown"] >= -0.20
            and val["max_drawdown"] >= -0.20
            and dev["fill_count"] >= 8
            and val["fill_count"] >= 8
        )
        row = {
            "name": spec.name,
            "spec": asdict(spec),
            "development": _brief(dev),
            "development_cost_2x": _brief(dev_stress),
            "validation": _brief(val),
            "validation_cost_2x": _brief(val_stress),
            "validation_calendar_year_returns": years,
            "minimum_validation_calendar_year_return": min(years.values()),
            "eligible": bool(passed),
        }
        trials.append(row)
        if passed:
            eligible.append(row)
    (OUT / "selection_trials.json").write_text(dumps(trials) + "\n")
    if not eligible:
        lock = {
            "protocol_sha256": protocol_hash,
            "data_sha256": _data_hashes(),
            "selected": None,
            "eligible_count": 0,
            "reason": "No configuration passed the predeclared selection gate",
            "evaluation_opened": False,
        }
    else:
        winner = max(
            eligible,
            key=lambda row: (
                row["minimum_validation_calendar_year_return"],
                row["validation"]["net_return"],
                row["validation"]["max_drawdown"],
            ),
        )
        lock = {
            "protocol_sha256": protocol_hash,
            "data_sha256": _data_hashes(),
            "selected": winner["name"],
            "selected_spec": winner["spec"],
            "eligible_count": len(eligible),
            "selection_evidence": winner,
            "selection_rule": protocol["selection"],
            "evaluation_opened": False,
        }
    SELECTION_PATH.write_text(dumps(lock) + "\n")
    return lock


def _passive(
    data: dict[str, pd.DataFrame], symbols: tuple[str, ...], start: str, end: str
) -> dict:
    dates = data["SPY"].index
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    allocation = MAX_DEPLOYMENT / len(symbols)
    cash = CAPITAL
    quantities = {}
    costs = 0.0
    for symbol in symbols:
        notional = CAPITAL * allocation
        quantity = notional / float(data[symbol].loc[dates[0], "open"])
        quantities[symbol] = quantity
        fee = notional * 15 / 10_000
        costs += fee
        cash -= notional + fee
    values = [CAPITAL]
    points = []
    for date in dates:
        equity = cash + sum(
            quantity * float(data[symbol].loc[date, "close"])
            for symbol, quantity in quantities.items()
        )
        values.append(equity)
        points.append(
            {
                "timestamp": pd.Timestamp(date).tz_localize("UTC").isoformat(),
                "equity": equity,
            }
        )
    return {
        "symbols": list(symbols),
        "ending_equity": values[-1],
        "net_return": values[-1] / CAPITAL - 1,
        "max_drawdown": _drawdown(values),
        "transaction_costs": costs,
        "points": points,
    }


def _two_month_windows(data: dict[str, pd.DataFrame], spec: RotationSpec) -> list[dict]:
    rows = []
    start = pd.Timestamp("2022-01-01")
    last = pd.Timestamp("2026-10-30")
    while start + pd.DateOffset(months=2) <= last + pd.Timedelta(days=1):
        end = start + pd.DateOffset(months=2) - pd.Timedelta(days=1)
        result = simulate(data, spec, str(start.date()), str(end.date()))
        rows.append(
            {
                "window": f"{start.date()} to {end.date()}",
                "net_return": result["net_return"],
                "profit_usd": result["ending_equity"] - CAPITAL,
                "max_drawdown": result["max_drawdown"],
                "fills": result["fill_count"],
            }
        )
        start = start + pd.DateOffset(months=2)
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
        "median_return": float(np.median(returns)),
        "average_profit_usd": float(returns.mean() * CAPITAL),
        "average_max_drawdown": float(drawdowns.mean()),
        "worst_max_drawdown": float(drawdowns.min()),
        "best_return": float(returns.max()),
        "worst_return": float(returns.min()),
    }


def _write_report(summary: dict) -> None:
    p = summary["periods"]
    windows = summary["two_month_summary"]
    weekly = summary["weekly_evaluation"]
    benchmarks = summary["benchmarks"]
    lines = [
        "# ETF rotation challenger — staged result",
        "",
        f"**Outcome: {summary['outcome']}**",
        "",
        "The protocol was committed before the dedicated data snapshot was",
        "downloaded. Development and validation selected and locked the winner",
        "before the evaluation partition was opened.",
        "",
        (
            f"Selected configuration: `{summary['selected']}` from "
            f"{summary['eligible_count']} eligible configurations."
        ),
        "",
        "| Partition | Net return | Ending value | Maximum drawdown | Fills | Costs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in ("development", "validation", "evaluation", "evaluation_cost_2x"):
        row = p[label]
        lines.append(
            f"| {label.replace('_', ' ')} | {row['net_return']:.2%} | "
            f"${row['ending_equity']:.2f} | {row['max_drawdown']:.2%} | "
            f"{row['fill_count']} | ${row['transaction_costs']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Evaluation benchmarks at the same $500 start",
            "",
            "| Benchmark | Net return | Maximum drawdown |",
            "|---|---:|---:|",
            f"| 40% SPY / 60% cash | {benchmarks['spy_40']['net_return']:.2%} | {benchmarks['spy_40']['max_drawdown']:.2%} |",
            f"| 8% each ETF / 60% cash | {benchmarks['equal_40']['net_return']:.2%} | {benchmarks['equal_40']['max_drawdown']:.2%} |",
            "",
            "## Consistency diagnostics",
            "",
            (
                f"- Independent two-month resets from January 2022: "
                f"{windows['profitable']} profitable, {windows['losing']} losing "
                f"and {windows['flat']} flat of {windows['windows']}."
            ),
            f"- Average two-month return: {windows['average_return']:.2%} (${windows['average_profit_usd']:.2f}).",
            f"- Average / worst two-month drawdown: {windows['average_max_drawdown']:.2%} / {windows['worst_max_drawdown']:.2%}.",
            f"- Evaluation weeks: {weekly['profitable_weeks']} profitable, {weekly['losing_weeks']} losing and {weekly['flat_weeks']} flat.",
            f"- Lower 95% weekly-mean bound: {weekly['mean_weekly_return_lower_95']:.3%}.",
            "",
            "## Decision boundary",
            "",
            summary["decision"],
            "",
            "This is adjusted-price retrospective research with a current fixed",
            "ETF universe, modeled proportional costs, fractional research units",
            "and no taxes or cash yield. Yahoo history can be revised. It is not",
            "a broker fill record and cannot alter the existing defensive forward",
            "account. No external order was submitted.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines))


def evaluate() -> dict:
    protocol, protocol_hash = _protocol()
    lock = json.loads(SELECTION_PATH.read_text())
    if lock["protocol_sha256"] != protocol_hash:
        raise ValueError("Protocol changed after selection")
    if lock["data_sha256"] != _data_hashes():
        raise ValueError("Data changed after selection")
    if not lock.get("selected"):
        raise ValueError("No selected ETF challenger")
    spec = RotationSpec(**lock["selected_spec"])
    data = load_data()
    periods = {}
    for label in ("development", "validation", "evaluation"):
        periods[label] = simulate(data, spec, *protocol["partitions"][label])
    periods["evaluation_cost_2x"] = simulate(
        data, spec, *protocol["partitions"]["evaluation"], cost_bps=30
    )
    windows = _two_month_windows(data, spec)
    pd.DataFrame(windows).to_csv(OUT / "two_month_windows.csv", index=False)
    weekly = weekly_report(
        periods["evaluation"]["points"],
        CAPITAL,
        periods["evaluation"]["sell_count"],
        periods["evaluation_cost_2x"]["net_return"] > 0,
    )
    benchmarks = {
        "spy_40": _passive(
            data, ("SPY",), *protocol["partitions"]["evaluation"]
        ),
        "equal_40": _passive(
            data, RISK_SYMBOLS, *protocol["partitions"]["evaluation"]
        ),
    }
    evaluation = periods["evaluation"]
    beats_current = (
        evaluation["net_return"] > 0.0504
        and evaluation["max_drawdown"] >= -0.20
        and periods["evaluation_cost_2x"]["net_return"] > 0
    )
    summary = {
        "protocol_sha256": protocol_hash,
        "data_sha256": lock["data_sha256"],
        "selected": spec.name,
        "selected_spec": asdict(spec),
        "eligible_count": lock["eligible_count"],
        "periods": {name: _brief(result) for name, result in periods.items()},
        "validation_calendar_year_returns": _calendar_years(
            data, spec, *protocol["partitions"]["validation"]
        ),
        "evaluation_calendar_year_returns": _calendar_years(
            data, spec, *protocol["partitions"]["evaluation"]
        ),
        "two_month_summary": _window_summary(windows),
        "weekly_evaluation": weekly,
        "benchmarks": {
            name: {
                key: value[key]
                for key in ("symbols", "ending_equity", "net_return", "max_drawdown", "transaction_costs")
            }
            for name, value in benchmarks.items()
        },
        "beats_selected_20pct_historical_return": beats_current,
        "outcome": (
            "historically stronger challenger; prospective paper comparison warranted"
            if beats_current
            else "did not beat the selected defensive candidate under the declared gate"
        ),
        "decision": (
            "Run this candidate only as a separate forward-paper challenger. Do not replace the frozen BTC/ETH account until both have comparable prospective evidence."
            if beats_current
            else "Reject this challenger. Preserve its failed result and continue the frozen BTC/ETH forward account unchanged."
        ),
        "broker_orders_submitted": 0,
    }
    (OUT / "summary.json").write_text(dumps(summary) + "\n")
    for label, result in periods.items():
        detail = {
            key: result[key]
            for key in ("name", "start", "end", "points", "fills", "decisions")
        }
        (OUT / f"{label}_detail.json").write_text(dumps(detail) + "\n")
    lock["evaluation_opened"] = True
    lock["evaluation_summary_sha256"] = hashlib.sha256(
        (OUT / "summary.json").read_bytes()
    ).hexdigest()
    SELECTION_PATH.write_text(dumps(lock) + "\n")
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
