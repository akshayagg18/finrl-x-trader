"""Select and evaluate the low-exposure trend allocation reproducibly."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.db import dumps
from trader.growth.defensive import INITIAL_CAPITAL, SPECS, DefensiveSpec, simulate
from trader.growth.regime import load_long_history
from trader.growth.weekly import weekly_report

OUT = Path("research/defensive_trend")
SYMBOLS = ("BTC-USDT", "ETH-USDT")
DEVELOPMENT = ("2019-01-01", "2021-12-31 23:00:00+00:00")
VALIDATION = ("2022-01-01", "2023-12-31 23:00:00+00:00")
EVALUATION = ("2024-01-01", "2026-10-31 23:00:00+00:00")


def _brief(result: dict) -> dict:
    return {
        key: result[key]
        for key in (
            "initial",
            "ending_equity",
            "net_return",
            "same_trade_gross_return",
            "max_drawdown",
            "fill_count",
            "sell_count",
            "transaction_costs",
        )
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _write_gzip(path: Path, value: object) -> None:
    with gzip.open(path, "wt") as handle:
        handle.write(dumps(value))


def _complete_two_month_windows(first: pd.Timestamp, data_end: pd.Timestamp):
    start = first
    data_end_exclusive = data_end + timedelta(hours=1)
    while True:
        end = start + pd.DateOffset(months=2)
        if end > data_end_exclusive:
            return
        yield start, end
        start = end


def _window_summary(rows: list[dict]) -> dict:
    returns = np.array([row["net_return"] for row in rows])
    profits = np.array([row["profit_usd"] for row in rows])
    drawdowns = np.array([row["max_drawdown"] for row in rows])
    return {
        "windows": len(rows),
        "profitable_windows": int((returns > 0).sum()),
        "losing_windows": int((returns < 0).sum()),
        "flat_windows": int((returns == 0).sum()),
        "profitable_fraction": float((returns > 0).mean()),
        "average_profit_usd": float(profits.mean()),
        "median_profit_usd": float(np.median(profits)),
        "average_return": float(returns.mean()),
        "median_return": float(np.median(returns)),
        "average_max_drawdown": float(drawdowns.mean()),
        "worst_max_drawdown": float(drawdowns.min()),
        "best_window": rows[int(returns.argmax())]["window"],
        "best_return": float(returns.max()),
        "worst_window": rows[int(returns.argmin())]["window"],
        "worst_return": float(returns.min()),
    }


def _hold(data: dict[str, pd.DataFrame], start: str, end: str) -> dict:
    """Same-risk 10% BTC + 10% ETH passive comparator."""

    daily = {}
    for symbol, frame in data.items():
        count = frame.close.resample("1D").count()
        daily[symbol] = pd.DataFrame(
            {
                "open": frame.open.resample("1D").first().where(count == 24),
                "close": frame.close.resample("1D").last().where(count == 24),
            }
        )
    common = daily[SYMBOLS[0]].dropna().index.intersection(
        daily[SYMBOLS[1]].dropna().index
    )
    lower = pd.to_datetime(start, utc=True)
    upper = pd.to_datetime(end, utc=True)
    dates = common[(common >= lower) & (common <= upper)]
    cost_rate = 15 / 10_000
    cash = INITIAL_CAPITAL
    quantity = {}
    fees = 0.0
    first = dates[0]
    for symbol in SYMBOLS:
        notional = INITIAL_CAPITAL * 0.10
        price = float(daily[symbol].loc[first, "open"])
        quantity[symbol] = notional / price
        fee = notional * cost_rate
        fees += fee
        cash -= notional + fee
    points = []
    for timestamp in dates:
        equity = cash + sum(
            quantity[symbol] * float(daily[symbol].loc[timestamp, "open"])
            for symbol in SYMBOLS
        )
        points.append({"timestamp": timestamp.isoformat(), "equity": equity})
    ending = cash + sum(
        quantity[symbol] * float(daily[symbol].loc[dates[-1], "close"])
        for symbol in SYMBOLS
    )
    values = np.array(
        [INITIAL_CAPITAL, *[row["equity"] for row in points], ending]
    )
    return {
        "initial": INITIAL_CAPITAL,
        "ending_equity": ending,
        "net_return": ending / INITIAL_CAPITAL - 1,
        "max_drawdown": float(
            np.min(values / np.maximum.accumulate(values) - 1)
        ),
        "transaction_costs": fees,
    }


def _report(summary: dict, trials: list[dict], windows: list[dict]) -> None:
    selected = summary["selected_spec"]
    periods = summary["periods"]
    window = summary["two_month_windows"]
    qualification = summary["qualification"]
    lines = [
        "# Defensive BTC/ETH trend research",
        "",
        "## Result",
        "",
        "This search found a **historically profitable candidate**, but it is",
        "**not qualified for broker deployment**. It made money after modeled",
        "costs in all three chronological partitions and at doubled costs in the",
        "last partition. That is retrospective evidence, not a promise of future",
        "profit or consistent weekly income.",
        "",
        "The selected rule checks every Monday at 00:00 UTC. It uses only the",
        f"previous completed close: BTC must be above its {selected['slow_days']}-day",
        f"average and have positive {selected['momentum_days']}-day momentum. When",
        "the gate is open, BTC and ETH may each receive up to 10% of equity,",
        "scaled down when 30-day annualized volatility exceeds 30%. At least 80%",
        "remains cash. The gate closing returns the allocation to cash.",
        "",
        "## Chronological results",
        "",
        "| Partition | Dates | Net return | Ending value | Max drawdown | Fills |",
        "|---|---|---:|---:|---:|---:|",
    ]
    labels = {
        "development": DEVELOPMENT,
        "validation": VALIDATION,
        "evaluation": EVALUATION,
        "evaluation_cost_2x": EVALUATION,
    }
    for name in ("development", "validation", "evaluation", "evaluation_cost_2x"):
        row = periods[name]
        lines.append(
            f"| {name.replace('_', ' ')} | {labels[name][0][:10]} to "
            f"{labels[name][1][:10]} | {row['net_return']:.2%} | "
            f"${row['ending_equity']:.2f} | {row['max_drawdown']:.2%} | "
            f"{row['fill_count']} |"
        )
    benchmark = summary["same_risk_hold_evaluation"]
    lines.extend(
        [
            "",
            "The same-risk passive comparator (10% BTC, 10% ETH, 80% cash) returned",
            f"**{benchmark['net_return']:.2%}** with **{benchmark['max_drawdown']:.2%}**",
            "maximum drawdown during the evaluation partition. Cash earns 0% in",
            "both simulations, so neither result includes interest on the reserve.",
            "",
            "## Independent two-month windows",
            "",
            f"From January 2022 through October 2026, {window['windows']} reset",
            f"windows averaged **${window['average_profit_usd']:.2f}**",
            f"(**{window['average_return']:.2%}**) with **{window['average_max_drawdown']:.2%}**",
            f"average maximum drawdown. {window['profitable_windows']} gained,",
            f"{window['losing_windows']} lost, and {window['flat_windows']} were flat.",
            "These arithmetic window averages are not a compounded account return.",
            "",
            "| Window | P/L | Return | Maximum drawdown |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in windows:
        lines.append(
            f"| {row['window']} | ${row['profit_usd']:.2f} | "
            f"{row['net_return']:.2%} | {row['max_drawdown']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Selection and limits",
            "",
            f"The search evaluated **{len(trials)}** prespecified combinations;",
            f"**{sum(row['eligible'] for row in trials)}** passed development and",
            "validation gates. Selection ranked only validation return among those",
            "eligible candidates. The final period was already viewed during",
            "exploratory work before this formal record, so it is chronological but",
            "not a pristine holdout. Multiple testing can exaggerate apparent edge.",
            "",
            f"Historical profitability condition: **{qualification['historically_profitable']}**.",
            f"Deployment qualified: **{qualification['deployment_qualified']}**.",
            "",
            "Deployment remains blocked because:",
            "",
        ]
    )
    lines.extend(f"- {reason}" for reason in qualification["deployment_reasons"])
    lines.extend(
        [
            "",
            "Data are public Binance spot hourly archives. Fees, adverse fills,",
            "market depth, USDT/USD parity, target-broker eligibility, taxes, and",
            "cash yield are not verified. No real or broker-paper order was sent.",
            "A new prospective paper period is required before deployment is",
            "reconsidered.",
            "",
            "Reproduce with `python -m scripts.evaluate_defensive_trend`.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "capital": INITIAL_CAPITAL,
        "universe": list(SYMBOLS),
        "source": "Binance public hourly spot archives; research only",
        "development": list(DEVELOPMENT),
        "validation": list(VALIDATION),
        "evaluation": list(EVALUATION),
        "configuration_count": len(SPECS),
        "grid": [spec.as_dict() for spec in SPECS],
        "fixed_risk": {
            "maximum_per_asset": 0.10,
            "maximum_total_deployment": 0.20,
            "minimum_cash": 0.80,
            "annualized_volatility_target": 0.30,
            "long_only": True,
            "leverage": False,
        },
        "execution": (
            "Lag completed UTC daily features; rebalance at the next 00:00 UTC "
            "open on stable calendar Mondays; fractional quantities"
        ),
        "cost_bps_per_traded_notional": 15.0,
        "cost_stress_bps": 30.0,
        "selection": (
            "Require positive net return and drawdown above -10% in development "
            "and validation, >=10 development fills and >=8 validation fills; "
            "select highest validation net return without using evaluation"
        ),
        "historical_profitability_condition": (
            "Positive development, validation, evaluation and doubled-cost "
            "evaluation return; evaluation drawdown above -10%"
        ),
        "deployment_condition": (
            "Historical condition plus a new prospective 12-week paper period, "
            "verified target-account costs/fills, and weekly uncertainty gate"
        ),
        "known_contamination": (
            "The 2024-2026 interval was inspected during exploratory prototyping "
            "on 2026-11-05 before this formal protocol; it is not pristine"
        ),
        "limitations": [
            "Retrospective results cannot guarantee future profitability.",
            "The 81-variant search creates multiple-testing risk.",
            "Historical spread and depth are unavailable; costs are modeled.",
            "Cross-venue data do not establish target-broker execution.",
            "Cash reserve earns zero in this simulation.",
        ],
    }
    protocol_text = dumps(protocol)
    (OUT / "protocol.json").write_text(protocol_text + "\n")
    protocol_hash = hashlib.sha256(protocol_text.encode()).hexdigest()

    data = {symbol: load_long_history(symbol) for symbol in SYMBOLS}
    trials = []
    selected_candidates: list[tuple[DefensiveSpec, dict]] = []
    for spec in SPECS:
        development = simulate(data, spec, *DEVELOPMENT)
        validation = simulate(data, spec, *VALIDATION)
        eligible = (
            development["net_return"] > 0
            and validation["net_return"] > 0
            and development["max_drawdown"] > -0.10
            and validation["max_drawdown"] > -0.10
            and development["fill_count"] >= 10
            and validation["fill_count"] >= 8
        )
        row = {
            "name": spec.name,
            "spec": spec.as_dict(),
            "development": _brief(development),
            "validation": _brief(validation),
            "eligible": bool(eligible),
        }
        trials.append(row)
        if eligible:
            selected_candidates.append((spec, row))
    _write_json(OUT / "trials.json", trials)
    if not selected_candidates:
        raise RuntimeError("No candidate passed the locked selection gates")
    selected_spec, selected_row = max(
        selected_candidates, key=lambda item: item[1]["validation"]["net_return"]
    )
    lock = {
        "protocol_sha256": protocol_hash,
        "selected": selected_spec.as_dict(),
        "name": selected_spec.name,
        "eligible_candidates": len(selected_candidates),
        "selection_metric": "highest validation net return among eligible candidates",
        "development": selected_row["development"],
        "validation": selected_row["validation"],
        "evaluation_opened_after_formal_lock": True,
        "evaluation_previously_inspected_during_exploration": True,
    }
    _write_json(OUT / "selection_locked.json", lock)

    evaluation = simulate(data, selected_spec, *EVALUATION)
    stress = simulate(data, selected_spec, *EVALUATION, cost_bps=30.0)
    weekly = weekly_report(
        evaluation["points"],
        INITIAL_CAPITAL,
        evaluation["sell_count"],
        stress_positive=stress["net_return"] > 0,
    )
    hold = _hold(data, *EVALUATION)
    _write_gzip(OUT / "evaluation.json.gz", evaluation)
    _write_gzip(OUT / "evaluation_cost_2x.json.gz", stress)

    windows = []
    data_end = min(frame.index[-1] for frame in data.values())
    first_window = pd.Timestamp("2022-01-01", tz="UTC")
    for start, end in _complete_two_month_windows(first_window, data_end):
        result = simulate(
            data,
            selected_spec,
            start,
            end - timedelta(hours=1),
        )
        windows.append(
            {
                "window": f"{start:%Y-%m} to {(end - timedelta(hours=1)):%Y-%m}",
                "start": start.isoformat(),
                "end_exclusive": end.isoformat(),
                "ending_equity": result["ending_equity"],
                "profit_usd": result["ending_equity"] - INITIAL_CAPITAL,
                "net_return": result["net_return"],
                "max_drawdown": result["max_drawdown"],
                "fill_count": result["fill_count"],
                "transaction_costs": result["transaction_costs"],
            }
        )
    pd.DataFrame(windows).to_csv(OUT / "two_month_windows.csv", index=False)
    window_summary = _window_summary(windows)

    historical = (
        selected_row["development"]["net_return"] > 0
        and selected_row["validation"]["net_return"] > 0
        and evaluation["net_return"] > 0
        and stress["net_return"] > 0
        and evaluation["max_drawdown"] > -0.10
    )
    deployment_reasons = [
        "The final historical interval was inspected during exploratory tuning.",
        "No new 12-week prospective paper observation has completed.",
        "Target-account fees, liquidity, eligibility, and actual fills are unverified.",
    ]
    if not weekly["qualified"]:
        deployment_reasons.extend(weekly["reasons"])
    summary = {
        "conclusion": (
            "HISTORICALLY PROFITABLE CANDIDATE; NOT DEPLOYMENT QUALIFIED"
            if historical
            else "NO HISTORICALLY PROFITABLE CANDIDATE"
        ),
        "selected_name": selected_spec.name,
        "selected_spec": selected_spec.as_dict(),
        "risk": protocol["fixed_risk"],
        "periods": {
            "development": selected_row["development"],
            "validation": selected_row["validation"],
            "evaluation": _brief(evaluation),
            "evaluation_cost_2x": _brief(stress),
        },
        "same_risk_hold_evaluation": hold,
        "two_month_windows": window_summary,
        "weekly_evaluation": weekly,
        "selection": {
            "tested": len(trials),
            "eligible": len(selected_candidates),
            "protocol_sha256": protocol_hash,
        },
        "qualification": {
            "historically_profitable": bool(historical),
            "deployment_qualified": False,
            "deployment_reasons": list(dict.fromkeys(deployment_reasons)),
        },
    }
    _write_json(OUT / "summary.json", summary)
    _report(summary, trials, windows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
