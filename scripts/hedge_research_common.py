"""Shared locked evaluation workflow for hedge research tracks."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.db import dumps
from trader.growth.defensive import (
    INITIAL_CAPITAL,
    DefensiveRisk,
    DefensiveSpec,
    simulate,
)
from trader.growth.regime import load_long_history
from trader.growth.weekly import weekly_report

SYMBOLS = ("BTC-USDT", "ETH-USDT")
DEVELOPMENT = ("2019-01-01", "2021-12-31 23:00:00+00:00")
VALIDATION = ("2022-01-01", "2023-12-31 23:00:00+00:00")
EVALUATION = ("2024-01-01", "2026-10-31 23:00:00+00:00")
RISKS = {
    "drawdown_10": {
        "budget": 0.10,
        "risk": DefensiveRisk(0.10, 0.20, 0.30),
    },
    "drawdown_20": {
        "budget": 0.20,
        "risk": DefensiveRisk(0.20, 0.40, 0.30),
    },
    "drawdown_50": {
        "budget": 0.50,
        "risk": DefensiveRisk(0.50, 1.00, 0.30),
    },
}
BASE_LONG_SPEC = DefensiveSpec(100, 90, "weekly", "btc_gate")


def _brief(result: dict) -> dict:
    keys = (
        "initial",
        "ending_equity",
        "net_return",
        "same_trade_gross_return",
        "max_drawdown",
        "fill_count",
        "transaction_costs",
        "financing_costs",
        "premium_paid",
        "option_sale_value",
    )
    return {key: result[key] for key in keys if key in result}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _write_gzip(path: Path, value: object) -> None:
    with gzip.open(path, "wt") as handle:
        handle.write(dumps(value))


def _windows(first: pd.Timestamp, data_end: pd.Timestamp):
    start = first
    while start + pd.DateOffset(months=2) <= data_end + timedelta(hours=1):
        end = start + pd.DateOffset(months=2)
        yield start, end
        start = end


def _window_summary(rows: list[dict]) -> dict:
    returns = np.asarray([row["net_return"] for row in rows])
    profits = np.asarray([row["profit_usd"] for row in rows])
    drawdowns = np.asarray([row["max_drawdown"] for row in rows])
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


def _report(
    out: Path,
    title: str,
    summary: dict,
    mechanism: str,
    limitations: list[str],
) -> None:
    lines = [
        f"# {title}",
        "",
        mechanism,
        "",
        "All periods were already inspected before this experiment. Results are",
        "diagnostic and cannot establish an untouched out-of-sample edge.",
        "",
        "## Chronological results",
        "",
        "| Tier | Selected | Development | Validation | Evaluation | Stress | Drawdown | Long/cash comparator |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, tier in summary["tiers"].items():
        periods = tier["periods"]
        comparator = tier["long_cash_comparator"]
        lines.append(
            f"| {name.replace('_', ' ')} | `{tier['selected_name']}` | "
            f"{periods['development']['net_return']:.2%} | "
            f"{periods['validation']['net_return']:.2%} | "
            f"{periods['evaluation']['net_return']:.2%} | "
            f"{periods['stress']['net_return']:.2%} | "
            f"{periods['evaluation']['max_drawdown']:.2%} | "
            f"{comparator['net_return']:.2%} / "
            f"{comparator['max_drawdown']:.2%} DD |"
        )
    lines.extend(
        [
            "",
            "## Independent two-month windows",
            "",
            "| Tier | Average P/L | Average return | Positive / negative / flat | Average drawdown | Worst drawdown |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, tier in summary["tiers"].items():
        window = tier["two_month_windows"]
        lines.append(
            f"| {name.replace('_', ' ')} | ${window['average_profit_usd']:.2f} | "
            f"{window['average_return']:.2%} | {window['profitable_windows']} / "
            f"{window['losing_windows']} / {window['flat_windows']} | "
            f"{window['average_max_drawdown']:.2%} | "
            f"{window['worst_max_drawdown']:.2%} |"
        )
    lines.extend(["", "## Qualification", ""])
    for name, tier in summary["tiers"].items():
        weekly = tier["weekly_evaluation"]
        lines.extend(
            [
                f"### {name.replace('_', ' ').title()}",
                "",
                f"- Passed development/validation selection: **{tier['selection_passed']}**",
                f"- Historically profitable condition: **{tier['historically_profitable']}**",
                f"- Within drawdown budget: **{tier['within_budget']}**",
                (
                    f"- Complete evaluation weeks: {weekly['complete_weeks']}; "
                    f"profitable {weekly['profitable_weeks']}, losing "
                    f"{weekly['losing_weeks']}, flat {weekly['flat_weeks']}"
                ),
                (
                    f"- Lower 95% weekly-mean bound: "
                    f"{weekly['mean_weekly_return_lower_95']:.2%}"
                ),
                "- Deployment qualified: **False**",
                "",
            ]
        )
    lines.extend(["## Material limitations", ""])
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "- A drawdown budget is an acceptance threshold, not a guaranteed loss cap.",
            "- Fees, liquidity, eligibility and fills require target-account verification.",
            "- No external order was submitted and no track is connected to broker routing.",
            "",
            f"Reproduce with `python -m {summary['script']}`.",
            "",
        ]
    )
    (out / "REPORT.md").write_text("\n".join(lines))


def run_track(
    *,
    track: str,
    title: str,
    script: str,
    specs: Iterable,
    simulator: Callable,
    base_kwargs: dict,
    stress_kwargs: dict,
    mechanism: str,
    limitations: list[str],
) -> dict:
    out = Path("research") / track
    out.mkdir(parents=True, exist_ok=True)
    specs = tuple(specs)
    protocol = {
        "track": track,
        "capital": INITIAL_CAPITAL,
        "universe": list(SYMBOLS),
        "source": "Binance public hourly spot archives; research only",
        "development": list(DEVELOPMENT),
        "validation": list(VALIDATION),
        "evaluation": list(EVALUATION),
        "risk_tiers": {
            name: {"drawdown_budget": item["budget"], "risk": item["risk"].as_dict()}
            for name, item in RISKS.items()
        },
        "grid": [spec.as_dict() for spec in specs],
        "configuration_count_per_tier": len(specs),
        "selection": (
            "Require positive development and validation returns, drawdowns "
            "inside the tier budget, >=10 development and >=8 validation "
            "execution events; rank validation return"
        ),
        "base_assumptions": base_kwargs,
        "stress_assumptions": stress_kwargs,
        "execution": (
            "Lag completed UTC daily features; execute at a later daily open; "
            "fractional quantities and explicit proportional friction"
        ),
        "contamination": (
            "All historical partitions and the underlying trend family were "
            "previously inspected; evaluation is diagnostic, not pristine"
        ),
        "limitations": limitations,
    }
    protocol_text = dumps(protocol)
    (out / "protocol.json").write_text(protocol_text + "\n")
    protocol_hash = hashlib.sha256(protocol_text.encode()).hexdigest()
    data = {symbol: load_long_history(symbol) for symbol in SYMBOLS}

    trials = []
    selections = {}
    for tier_name, tier in RISKS.items():
        risk = tier["risk"]
        budget = tier["budget"]
        eligible = []
        diagnostic = []
        for spec in specs:
            development = simulator(
                data, spec, *DEVELOPMENT, risk=risk, **base_kwargs
            )
            validation = simulator(data, spec, *VALIDATION, risk=risk, **base_kwargs)
            activity = (
                development["fill_count"] >= 10
                and validation["fill_count"] >= 8
            )
            passed = (
                activity
                and development["net_return"] > 0
                and validation["net_return"] > 0
                and development["max_drawdown"] > -budget
                and validation["max_drawdown"] > -budget
            )
            row = {
                "tier": tier_name,
                "name": spec.name,
                "spec": spec.as_dict(),
                "development": _brief(development),
                "validation": _brief(validation),
                "eligible": bool(passed),
            }
            trials.append(row)
            if activity:
                diagnostic.append((spec, row))
            if passed:
                eligible.append((spec, row))
        if not diagnostic:
            raise RuntimeError(f"No active {track} configuration for {tier_name}")
        spec, row = max(
            eligible or diagnostic,
            key=lambda item: item[1]["validation"]["net_return"],
        )
        selections[tier_name] = {
            "spec": spec,
            "row": row,
            "eligible_count": len(eligible),
            "selection_passed": bool(eligible),
        }
    _write_json(out / "trials.json", trials)
    lock = {
        "protocol_sha256": protocol_hash,
        "evaluation_previously_inspected": True,
        "tiers": {
            name: {
                "selected_name": selected["spec"].name,
                "selected_spec": selected["spec"].as_dict(),
                "eligible_count": selected["eligible_count"],
                "selection_passed": selected["selection_passed"],
                "development": selected["row"]["development"],
                "validation": selected["row"]["validation"],
            }
            for name, selected in selections.items()
        },
    }
    _write_json(out / "selection_locked.json", lock)

    data_end = min(frame.index[-1] for frame in data.values())
    summary_tiers = {}
    for tier_name, selected in selections.items():
        tier = RISKS[tier_name]
        risk = tier["risk"]
        budget = tier["budget"]
        spec = selected["spec"]
        evaluation = simulator(data, spec, *EVALUATION, risk=risk, **base_kwargs)
        stress = simulator(data, spec, *EVALUATION, risk=risk, **stress_kwargs)
        comparator = simulate(data, BASE_LONG_SPEC, *EVALUATION, risk=risk)
        weekly = weekly_report(
            evaluation["points"],
            INITIAL_CAPITAL,
            evaluation["fill_count"],
            stress_positive=stress["net_return"] > 0,
        )
        _write_gzip(out / f"{tier_name}_evaluation.json.gz", evaluation)
        _write_gzip(out / f"{tier_name}_stress.json.gz", stress)
        window_rows = []
        for start, end in _windows(pd.Timestamp("2022-01-01", tz="UTC"), data_end):
            result = simulator(
                data,
                spec,
                start,
                end - timedelta(hours=1),
                risk=risk,
                **base_kwargs,
            )
            window_rows.append(
                {
                    "tier": tier_name,
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
        pd.DataFrame(window_rows).to_csv(
            out / f"{tier_name}_two_month_windows.csv", index=False
        )
        periods = {
            "development": selected["row"]["development"],
            "validation": selected["row"]["validation"],
            "evaluation": _brief(evaluation),
            "stress": _brief(stress),
        }
        within_budget = evaluation["max_drawdown"] > -budget
        historically_profitable = (
            selected["selection_passed"]
            and all(result["net_return"] > 0 for result in periods.values())
            and within_budget
        )
        summary_tiers[tier_name] = {
            "drawdown_budget": budget,
            "risk": risk.as_dict(),
            "selected_name": spec.name,
            "selected_spec": spec.as_dict(),
            "eligible_candidates": selected["eligible_count"],
            "selection_passed": selected["selection_passed"],
            "periods": periods,
            "long_cash_comparator": _brief(comparator),
            "two_month_windows": _window_summary(window_rows),
            "weekly_evaluation": weekly,
            "within_budget": bool(within_budget),
            "historically_profitable": bool(historically_profitable),
            "deployment_qualified": False,
        }
    summary = {
        "track": track,
        "script": script,
        "conclusion": "DIAGNOSTIC ONLY; NO TRACK DEPLOYMENT QUALIFIED",
        "protocol_sha256": protocol_hash,
        "tested_configurations": len(trials),
        "tiers": summary_tiers,
        "deployment_reasons": [
            "All historical partitions were previously inspected.",
            "No new prospective paper period has completed.",
            "Derivative or borrow execution is not integrated or externally verified.",
            "Target-account fees, liquidity, eligibility, and fills are unverified.",
        ],
    }
    _write_json(out / "summary.json", summary)
    _report(out, title, summary, mechanism, limitations)
    return summary
