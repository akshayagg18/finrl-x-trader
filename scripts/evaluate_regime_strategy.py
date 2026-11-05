"""Locked long-history evaluation of a low-turnover regime strategy and ML filter."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import pandas as pd

from trader.db import dumps
from trader.growth.config import GrowthConfig
from trader.growth.portfolio import execute
from trader.growth.regime import (
    FILTER_FAMILIES,
    FILTER_THRESHOLDS,
    SPECS,
    decision_schedule,
    decision_schedule_between,
    filter_probability,
    fit_filter,
    load_long_history,
    save_filter,
)
from trader.growth.weekly import weekly_report

OUT = Path("research/strategy_v2")
SYMBOLS = ("BTC-USDT", "ETH-USDT")
DEVELOPMENT = ("2019-01-01", "2021-12-31 23:00:00+00:00")
VALIDATION = ("2022-01-01", "2022-12-31 23:00:00+00:00")
EVALUATION = ("2023-01-01", "2026-10-31 23:00:00+00:00")


def _available(data: dict[str, pd.DataFrame], start: str, end: str) -> dict:
    lower = pd.Timestamp(start)
    upper = pd.Timestamp(end)
    lower = (
        lower.tz_localize("UTC") if lower.tzinfo is None else lower.tz_convert("UTC")
    )
    upper = (
        upper.tz_localize("UTC") if upper.tzinfo is None else upper.tz_convert("UTC")
    )
    sliced = {
        symbol: frame.loc[(frame.index >= lower) & (frame.index <= upper)].dropna()
        for symbol, frame in data.items()
    }
    common = sliced[SYMBOLS[0]].index.intersection(sliced[SYMBOLS[1]].index)
    return {symbol: frame.loc[common] for symbol, frame in sliced.items()}


def _combine(per_symbol: dict[str, dict[int, dict]]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for symbol, decisions in per_symbol.items():
        for timestamp, decision in decisions.items():
            result.setdefault(timestamp, {})[symbol] = decision
    return result


def _year_returns(result: dict) -> dict[str, float]:
    points = pd.DataFrame(result["equity"])
    equity = pd.Series(
        points.equity.to_numpy(), index=pd.to_datetime(points.timestamp, utc=True)
    )
    years = {}
    prior = result["initial"]
    for year, group in equity.groupby(equity.index.year):
        years[str(year)] = float(group.iloc[-1] / prior - 1)
        prior = group.iloc[-1]
    return years


def _brief(result: dict) -> dict:
    return {
        "net_return": result["net_return"],
        "same_trade_gross_return": result["same_trade_gross_return"],
        "ending_equity": result["ending_equity"],
        "fees": result["fees"],
        "execution_friction": result["execution_friction"],
        "completed_trades": result["completed_trades"],
        "year_returns": _year_returns(result),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    config = GrowthConfig()
    round_trip_cost = 2 * (config.fee_bps + config.friction_bps) / 10000
    protocol = {
        "written_before_evaluation": True,
        "capital": 500,
        "universe": list(SYMBOLS),
        "source": "Binance public hourly spot archives; research only",
        "source_warning": "Cross-venue data cannot verify OKX Singapore execution",
        "development": list(DEVELOPMENT),
        "validation": list(VALIDATION),
        "evaluation": list(EVALUATION),
        "rule_grid": [asdict(spec) for spec in SPECS],
        "rule_selection": (
            "Require positive development and validation net returns, validation "
            "drawdown above -10%, and >=20 combined completed exits; rank by "
            "validation return. If none qualifies, evaluate the top validation "
            "candidate with >=20 combined exits and >=1 validation exit "
            "diagnostically and forbid promotion."
        ),
        "ml_filter": {
            "families": list(FILTER_FAMILIES),
            "thresholds": list(FILTER_THRESHOLDS),
            "label": "positive seven-day return after modeled round-trip cost",
            "behavior": "filters entries only; base regime controls exits",
            "selection": (
                "On 2022 validation require positive return, drawdown above -10%, "
                "and >=10 exits; rank by validation return."
            ),
        },
        "evaluation_refits": "Annual at UTC year boundary using prior three years only",
        "costs": {
            "fee_bps_per_side": config.fee_bps,
            "adverse_execution_bps_per_side": config.friction_bps,
            "stress": [1.0, 1.5, 2.0],
            "verified_account_tariff": False,
        },
        "risk": config.model_dump(),
        "qualification": (
            "Positive net and doubled-cost result, drawdown below 10%, >=52 "
            "complete Singapore weeks, >=100 exits, positive lower 95% four-week "
            "block-bootstrap mean; then 12 forward weeks and 30 exits."
        ),
        "limitations": [
            "All dates are retrospective and do not replace prospective evidence.",
            "Vendor history may be revised; missing hours remain explicit in features.",
            "Historical bid/ask and depth are unavailable; fills are modeled.",
            "USDT/USD parity is assumed.",
        ],
    }
    protocol_text = dumps(protocol)
    (OUT / "protocol.json").write_text(protocol_text + "\n")
    protocol_hash = hashlib.sha256(protocol_text.encode()).hexdigest()

    data = {symbol: load_long_history(symbol) for symbol in SYMBOLS}
    trials = []
    candidates = []
    for spec in SPECS:
        decisions = _combine(
            {symbol: decision_schedule(data[symbol], spec) for symbol in SYMBOLS}
        )
        development = execute(
            _available(data, *DEVELOPMENT), decisions, config.model_dump()
        )
        validation = execute(
            _available(data, *VALIDATION), decisions, config.model_dump()
        )
        validation_weekly = weekly_report(
            validation["equity"], 500, validation["completed_trades"]
        )
        combined_exits = (
            development["completed_trades"] + validation["completed_trades"]
        )
        eligible = (
            development["net_return"] > 0
            and validation["net_return"] > 0
            and validation["completed_trades"] > 0
            and combined_exits >= 20
            and validation_weekly["max_drawdown"] > -0.1
        )
        row = {
            "name": spec.name,
            "spec": asdict(spec),
            "development": _brief(development),
            "validation": _brief(validation),
            "combined_exits": combined_exits,
            "validation_max_drawdown": validation_weekly["max_drawdown"],
            "eligible": bool(eligible),
        }
        trials.append(row)
        candidates.append((spec, row))
        print(
            json.dumps(
                {
                    "stage": "rule_selection",
                    "name": spec.name,
                    "development": development["net_return"],
                    "validation": validation["net_return"],
                    "exits": combined_exits,
                    "eligible": bool(eligible),
                }
            ),
            flush=True,
        )
    eligible_rules = [item for item in candidates if item[1]["eligible"]]
    diagnostic_rules = [
        item
        for item in candidates
        if item[1]["combined_exits"] >= 20
        and item[1]["validation"]["completed_trades"] >= 1
    ]
    selected_spec, selected_rule = max(
        eligible_rules or diagnostic_rules,
        key=lambda item: item[1]["validation"]["net_return"],
    )
    rule_qualified_for_evaluation = bool(eligible_rules)

    validation_data = _available(data, *VALIDATION)
    ml_trials = []
    filter_candidates = []
    for family in FILTER_FAMILIES:
        models = {}
        probabilities = {}
        manifests = {}
        try:
            for symbol in SYMBOLS:
                model, metadata = fit_filter(
                    data[symbol],
                    symbol,
                    selected_spec,
                    VALIDATION[0],
                    family,
                    round_trip_cost,
                )
                models[symbol] = model
                manifests[symbol] = metadata
                probabilities[symbol] = filter_probability(
                    model, data[symbol], selected_spec
                )
        except ValueError as exc:
            ml_trials.append(
                {
                    "family": family,
                    "error": type(exc).__name__ + ": " + str(exc),
                    "eligible": False,
                }
            )
            continue
        for threshold in FILTER_THRESHOLDS:
            decisions = _combine(
                {
                    symbol: decision_schedule(
                        data[symbol],
                        selected_spec,
                        probabilities[symbol],
                        threshold,
                    )
                    for symbol in SYMBOLS
                }
            )
            validation = execute(validation_data, decisions, config.model_dump())
            weekly = weekly_report(
                validation["equity"], 500, validation["completed_trades"]
            )
            eligible = (
                validation["net_return"] > 0
                and weekly["max_drawdown"] > -0.1
                and validation["completed_trades"] >= 10
            )
            row = {
                "family": family,
                "threshold": threshold,
                "validation": _brief(validation),
                "max_drawdown": weekly["max_drawdown"],
                "eligible": bool(eligible),
                "training": manifests,
            }
            ml_trials.append(row)
            filter_candidates.append((family, threshold, row))
            print(
                json.dumps(
                    {
                        "stage": "filter_selection",
                        "family": family,
                        "threshold": threshold,
                        "return": validation["net_return"],
                        "exits": validation["completed_trades"],
                        "eligible": bool(eligible),
                    }
                ),
                flush=True,
            )
    eligible_filters = [item for item in filter_candidates if item[2]["eligible"]]
    if not filter_candidates:
        raise RuntimeError("No ML filter could be trained for the selected base regime")
    selected_family, selected_threshold, selected_filter = max(
        eligible_filters or filter_candidates,
        key=lambda item: item[2]["validation"]["net_return"],
    )
    filter_qualified_for_evaluation = bool(eligible_filters)

    lock = {
        "protocol_sha256": protocol_hash,
        "locked_before_evaluation": True,
        "rule": selected_rule,
        "rule_passed_selection": rule_qualified_for_evaluation,
        "filter": selected_filter,
        "filter_passed_selection": filter_qualified_for_evaluation,
    }
    (OUT / "selection_locked.json").write_text(dumps(lock) + "\n")
    (OUT / "rule_trials.json").write_text(dumps(trials) + "\n")
    (OUT / "filter_trials.json").write_text(dumps(ml_trials) + "\n")

    evaluation_data = _available(data, *EVALUATION)
    rule_schedule = _combine(
        {symbol: decision_schedule(data[symbol], selected_spec) for symbol in SYMBOLS}
    )
    filter_schedule: dict[int, dict] = {}
    version_manifests = []
    evaluation_end_exclusive = pd.Timestamp(EVALUATION[1]) + timedelta(hours=1)
    for year in range(2023, 2027):
        cutoff = pd.Timestamp(f"{year}-01-01", tz="UTC")
        end = min(
            pd.Timestamp(f"{year + 1}-01-01", tz="UTC"),
            evaluation_end_exclusive,
        )
        per_symbol = {}
        for symbol in SYMBOLS:
            model, metadata = fit_filter(
                data[symbol],
                symbol,
                selected_spec,
                cutoff,
                selected_family,
                round_trip_cost,
            )
            metadata.update(
                threshold=selected_threshold,
                protocol_sha256=protocol_hash,
                selected_rule=selected_spec.name,
                evaluation_year=year,
            )
            version_manifests.append(save_filter(model, metadata))
            probability = filter_probability(model, data[symbol], selected_spec)
            per_symbol[symbol] = decision_schedule_between(
                data[symbol],
                selected_spec,
                cutoff,
                end,
                probability,
                selected_threshold,
            )
        for timestamp, decisions in _combine(per_symbol).items():
            filter_schedule.setdefault(timestamp, {}).update(decisions)
    (OUT / "model_versions.json").write_text(dumps(version_manifests) + "\n")

    results = {}
    fixed_schedules = {"rule": rule_schedule, "ml_filter": filter_schedule}
    for name, schedule in fixed_schedules.items():
        for label, multiplier in (("base", 1.0), ("cost_1.5x", 1.5), ("cost_2x", 2.0)):
            stressed = config.model_dump()
            stressed.update(
                fee_bps=config.fee_bps * multiplier,
                friction_bps=config.friction_bps * multiplier,
            )
            results[f"{name}_{label}"] = execute(evaluation_data, schedule, stressed)
    results["cash"] = execute(evaluation_data, {}, config.model_dump())
    hold = {
        timestamp.value: {
            symbol: {
                "enter": True,
                "liquidate": False,
                "horizon": 24 * 365 * 20,
                "stop": 0.03,
            }
            for symbol in SYMBOLS
        }
        for timestamp in evaluation_data[SYMBOLS[0]].index
    }
    results["hold"] = execute(
        evaluation_data, hold, config.model_dump(), benchmark=True
    )

    summary = {}
    for name, result in results.items():
        stress_name = (
            "rule_cost_2x"
            if name.startswith("rule")
            else "ml_filter_cost_2x"
            if name.startswith("ml_filter")
            else None
        )
        stress_positive = (
            results[stress_name]["net_return"] > 0 if stress_name else False
        )
        weekly = weekly_report(
            result["equity"],
            500,
            result["completed_trades"],
            stress_positive,
        )
        if name.startswith("rule") and not rule_qualified_for_evaluation:
            weekly["qualified"] = False
            weekly["reasons"].append("Rule failed pre-evaluation selection gate")
        if name.startswith("ml_filter") and not filter_qualified_for_evaluation:
            weekly["qualified"] = False
            weekly["reasons"].append("ML filter failed pre-evaluation selection gate")
        if name.startswith("ml_filter") and not rule_qualified_for_evaluation:
            weekly["qualified"] = False
            weekly["reasons"].append("Base rule failed pre-evaluation selection gate")
        weekly["live_qualified"] = False
        weekly["live_reasons"] = [
            "Historical results use cross-venue Binance data rather than OKX execution data",
            "Account-specific fees, spreads, fills, and instrument eligibility are unverified",
            "Prospective forward qualification has not been completed",
        ]
        if not weekly["qualified"]:
            weekly["live_reasons"].insert(0, "Historical qualification gate failed")
        result["weekly"] = weekly
        with gzip.open(OUT / f"{name}.json.gz", "wt") as handle:
            handle.write(dumps(result))
        summary[name] = {**_brief(result), **weekly}
    (OUT / "summary.json").write_text(dumps(summary) + "\n")
    pd.DataFrame(
        [
            {"scenario": name, **{k: v for k, v in values.items() if k != "weeks"}}
            for name, values in summary.items()
        ]
    ).to_csv(OUT / "comparison.csv", index=False)
    pd.DataFrame({name: values["weeks"] for name, values in summary.items()}).to_csv(
        OUT / "weekly_returns.csv", index_label="singapore_week_start"
    )
    print("COMPLETE " + dumps(summary), flush=True)


if __name__ == "__main__":
    main()
