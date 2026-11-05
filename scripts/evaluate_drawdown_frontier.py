"""Evaluate the defensive trend family at 20% and 50% drawdown budgets."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.db import dumps
from trader.growth.defensive import (
    INITIAL_CAPITAL,
    SPECS,
    DefensiveRisk,
    DefensiveSpec,
    prepare_daily,
    simulate,
)
from trader.growth.regime import load_long_history
from trader.growth.weekly import weekly_report

OUT = Path("research/drawdown_frontier")
SYMBOLS = ("BTC-USDT", "ETH-USDT")
DEVELOPMENT = ("2019-01-01", "2021-12-31 23:00:00+00:00")
VALIDATION = ("2022-01-01", "2023-12-31 23:00:00+00:00")
EVALUATION = ("2024-01-01", "2026-10-31 23:00:00+00:00")
TIERS = {
    "drawdown_20": {
        "drawdown_budget": 0.20,
        "risk": DefensiveRisk(per_asset_cap=0.20, max_deployment=0.40),
    },
    "drawdown_50": {
        "drawdown_budget": 0.50,
        "risk": DefensiveRisk(per_asset_cap=0.50, max_deployment=1.00),
    },
}


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


def _windows(first: pd.Timestamp, data_end: pd.Timestamp):
    start = first
    while start + pd.DateOffset(months=2) <= data_end + timedelta(hours=1):
        end = start + pd.DateOffset(months=2)
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


def _passive(
    data: dict[str, pd.DataFrame],
    start: str,
    end: str,
    risk: DefensiveRisk,
    cost_bps: float = 15.0,
) -> dict:
    """Buy equal allocations up to the tier's maximum deployment."""

    daily = prepare_daily(data)
    common = daily[SYMBOLS[0]].dropna().index.intersection(
        daily[SYMBOLS[1]].dropna().index
    )
    lower = pd.to_datetime(start, utc=True)
    upper = pd.to_datetime(end, utc=True)
    dates = common[(common >= lower) & (common <= upper)]
    allocation = min(risk.per_asset_cap, risk.max_deployment / len(SYMBOLS))
    cash = INITIAL_CAPITAL
    quantities = {}
    costs = 0.0
    for symbol in SYMBOLS:
        notional = INITIAL_CAPITAL * allocation
        price = float(daily[symbol].loc[dates[0], "open"])
        quantities[symbol] = notional / price
        cost = notional * cost_bps / 10_000
        cash -= notional + cost
        costs += cost
    values = [INITIAL_CAPITAL]
    for timestamp in dates:
        values.append(
            cash
            + sum(
                quantities[symbol]
                * float(daily[symbol].loc[timestamp, "open"])
                for symbol in SYMBOLS
            )
        )
    ending = cash + sum(
        quantities[symbol] * float(daily[symbol].loc[dates[-1], "close"])
        for symbol in SYMBOLS
    )
    values.append(ending)
    equity = np.asarray(values)
    return {
        "allocation_per_asset": allocation,
        "initial": INITIAL_CAPITAL,
        "ending_equity": ending,
        "net_return": ending / INITIAL_CAPITAL - 1,
        "max_drawdown": float(
            np.min(equity / np.maximum.accumulate(equity) - 1)
        ),
        "transaction_costs": costs,
    }


def _build_report(summary: dict) -> None:
    preference = summary["preference"]
    lines = [
        "# Drawdown frontier: 20% and 50% budgets",
        "",
        "This diagnostic scales the defensive trend family to higher exposure.",
        "A drawdown budget is an acceptance threshold, not a stop-loss guarantee.",
        "Price gaps, liquidity and execution failures can produce larger losses.",
        "The history was already inspected, so these results are not a fresh",
        "holdout and cannot qualify either tier for deployment.",
        "",
        "## Results",
        "",
        "| Tier | Maximum exposure | Development | Validation | Evaluation | 2x cost | Evaluation drawdown | Passive return / drawdown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, tier in summary["tiers"].items():
        periods = tier["periods"]
        passive = tier["passive_evaluation"]
        lines.append(
            f"| {name.replace('_', ' ')} | {tier['risk']['max_deployment']:.0%} | "
            f"{periods['development']['net_return']:.2%} | "
            f"{periods['validation']['net_return']:.2%} | "
            f"{periods['evaluation']['net_return']:.2%} | "
            f"{periods['evaluation_cost_2x']['net_return']:.2%} | "
            f"{periods['evaluation']['max_drawdown']:.2%} | "
            f"{passive['net_return']:.2%} / {passive['max_drawdown']:.2%} |"
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
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Among the newly requested tiers, the 20% budget has the stronger",
            "return-to-drawdown tradeoff. Moving to the 50% budget added only",
            f"{preference['additional_return']:.2%} of evaluation return while",
            f"worsening measured drawdown by {preference['additional_drawdown']:.2%}.",
            "The 50% tier is not preferred.",
            "The earlier 10% tier remains the least damaging measured option.",
            "",
            "Exposure scaling increases both modeled profit and loss. The passive",
            "comparators use the same maximum allocation, while the trend strategy",
            "often holds less because of volatility scaling or remains fully in cash.",
            "Cash earns 0% in every scenario.",
            "",
        ]
    )
    for name, tier in summary["tiers"].items():
        weekly = tier["weekly_evaluation"]
        lines.extend(
            [
                f"### {name.replace('_', ' ').title()}",
                "",
                f"- Selected configuration: `{tier['selected_name']}`",
                f"- Realized evaluation drawdown within budget: **{tier['within_budget']}**",
                (
                    f"- Complete weeks: {weekly['complete_weeks']}; profitable: "
                    f"{weekly['profitable_weeks']}; losing: "
                    f"{weekly['losing_weeks']}; flat: {weekly['flat_weeks']}"
                ),
                f"- Lower 95% weekly-mean bound: {weekly['mean_weekly_return_lower_95']:.2%}",
                "",
            ]
        )
    lines.extend(
        [
            "No tier is promoted. Both require a new prospective paper period,",
            "verified target-venue costs and account isolation. The 50% budget can",
            "lose roughly half the $500 account in the modeled path and can lose",
            "more in real execution. No external order was sent.",
            "",
            "Reproduce with `python -m scripts.evaluate_drawdown_frontier`.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "purpose": "Diagnostic drawdown frontier requested after prior evaluation",
        "capital": INITIAL_CAPITAL,
        "universe": list(SYMBOLS),
        "source": "Binance public hourly spot archives; research only",
        "development": list(DEVELOPMENT),
        "validation": list(VALIDATION),
        "evaluation": list(EVALUATION),
        "tiers": {
            name: {
                "drawdown_budget": tier["drawdown_budget"],
                "risk": tier["risk"].as_dict(),
            }
            for name, tier in TIERS.items()
        },
        "grid": [spec.as_dict() for spec in SPECS],
        "selection": (
            "Within each tier require positive development and validation net "
            "return, both drawdowns inside the tier budget, >=10 development "
            "fills and >=8 validation fills; rank validation return"
        ),
        "cost_bps_per_traded_notional": 15.0,
        "cost_stress_bps": 30.0,
        "execution": (
            "Lag completed UTC daily features and trade the following open on "
            "stable calendar rebalance dates; long-only fractional quantities"
        ),
        "contamination": (
            "All partitions and this strategy family were previously inspected; "
            "results are diagnostic and cannot be called untouched"
        ),
        "limitations": [
            "Drawdown budgets do not cap realized or future losses.",
            "The 162 tier/configuration combinations create multiple-testing risk.",
            "Historical spread and depth are unavailable; costs are modeled.",
            "Cross-venue data do not establish target-broker execution.",
            "Cash earns zero and taxes are excluded.",
        ],
    }
    protocol_text = dumps(protocol)
    (OUT / "protocol.json").write_text(protocol_text + "\n")
    protocol_hash = hashlib.sha256(protocol_text.encode()).hexdigest()
    data = {symbol: load_long_history(symbol) for symbol in SYMBOLS}

    trials = []
    selections = {}
    for tier_name, tier in TIERS.items():
        risk = tier["risk"]
        budget = tier["drawdown_budget"]
        candidates: list[tuple[DefensiveSpec, dict]] = []
        for spec in SPECS:
            development = simulate(data, spec, *DEVELOPMENT, risk=risk)
            validation = simulate(data, spec, *VALIDATION, risk=risk)
            eligible = (
                development["net_return"] > 0
                and validation["net_return"] > 0
                and development["max_drawdown"] > -budget
                and validation["max_drawdown"] > -budget
                and development["fill_count"] >= 10
                and validation["fill_count"] >= 8
            )
            row = {
                "tier": tier_name,
                "name": spec.name,
                "spec": spec.as_dict(),
                "risk": risk.as_dict(),
                "development": _brief(development),
                "validation": _brief(validation),
                "eligible": bool(eligible),
            }
            trials.append(row)
            if eligible:
                candidates.append((spec, row))
        if not candidates:
            raise RuntimeError(f"No eligible configuration for {tier_name}")
        spec, row = max(
            candidates, key=lambda item: item[1]["validation"]["net_return"]
        )
        selections[tier_name] = {
            "spec": spec,
            "row": row,
            "eligible_count": len(candidates),
        }
    _write_json(OUT / "trials.json", trials)
    lock = {
        "protocol_sha256": protocol_hash,
        "evaluation_previously_inspected": True,
        "tiers": {
            name: {
                "selected_name": selected["spec"].name,
                "selected_spec": selected["spec"].as_dict(),
                "eligible_count": selected["eligible_count"],
                "development": selected["row"]["development"],
                "validation": selected["row"]["validation"],
            }
            for name, selected in selections.items()
        },
    }
    _write_json(OUT / "selection_locked.json", lock)

    summary_tiers = {}
    data_end = min(frame.index[-1] for frame in data.values())
    for tier_name, selected in selections.items():
        tier = TIERS[tier_name]
        risk = tier["risk"]
        budget = tier["drawdown_budget"]
        spec = selected["spec"]
        evaluation = simulate(data, spec, *EVALUATION, risk=risk)
        stress = simulate(data, spec, *EVALUATION, risk=risk, cost_bps=30.0)
        weekly = weekly_report(
            evaluation["points"],
            INITIAL_CAPITAL,
            evaluation["sell_count"],
            stress_positive=stress["net_return"] > 0,
        )
        passive = _passive(data, *EVALUATION, risk)
        _write_gzip(OUT / f"{tier_name}_evaluation.json.gz", evaluation)
        _write_gzip(OUT / f"{tier_name}_cost_2x.json.gz", stress)
        window_rows = []
        for start, end in _windows(pd.Timestamp("2022-01-01", tz="UTC"), data_end):
            result = simulate(
                data,
                spec,
                start,
                end - timedelta(hours=1),
                risk=risk,
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
            OUT / f"{tier_name}_two_month_windows.csv", index=False
        )
        periods = {
            "development": selected["row"]["development"],
            "validation": selected["row"]["validation"],
            "evaluation": _brief(evaluation),
            "evaluation_cost_2x": _brief(stress),
        }
        within_budget = evaluation["max_drawdown"] > -budget
        historically_profitable = (
            all(result["net_return"] > 0 for result in periods.values())
            and within_budget
        )
        summary_tiers[tier_name] = {
            "drawdown_budget": budget,
            "risk": risk.as_dict(),
            "selected_name": spec.name,
            "selected_spec": spec.as_dict(),
            "eligible_candidates": selected["eligible_count"],
            "periods": periods,
            "passive_evaluation": passive,
            "two_month_windows": _window_summary(window_rows),
            "weekly_evaluation": weekly,
            "within_budget": bool(within_budget),
            "historically_profitable": bool(historically_profitable),
            "deployment_qualified": False,
        }
    moderate = summary_tiers["drawdown_20"]["periods"]["evaluation"]
    aggressive = summary_tiers["drawdown_50"]["periods"]["evaluation"]
    additional_return = aggressive["net_return"] - moderate["net_return"]
    additional_drawdown = abs(aggressive["max_drawdown"]) - abs(
        moderate["max_drawdown"]
    )
    summary = {
        "conclusion": "DIAGNOSTIC RISK FRONTIER; NO TIER DEPLOYMENT QUALIFIED",
        "protocol_sha256": protocol_hash,
        "tested_configurations": len(trials),
        "tiers": summary_tiers,
        "preference": {
            "among_new_tiers": "drawdown_20",
            "additional_return": additional_return,
            "additional_drawdown": additional_drawdown,
            "reason": (
                "The 50% tier added limited evaluation return relative to the "
                "additional drawdown versus the 20% tier"
            ),
            "deployment_recommendation": "none",
        },
        "deployment_reasons": [
            "All historical partitions were previously inspected.",
            "No new 12-week prospective paper period has completed.",
            "Target-account fees, liquidity, eligibility, and fills are unverified.",
            "A drawdown budget cannot guarantee a maximum realized loss.",
        ],
    }
    _write_json(OUT / "summary.json", summary)
    _build_report(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
