"""Build the four-track comparison from locked research artifacts."""

import json
from pathlib import Path

OUT = Path("research/hedge_comparison")
TIERS = ("drawdown_10", "drawdown_20", "drawdown_50")


def _read(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _long_cash() -> dict:
    defensive = _read("research/defensive_trend/summary.json")
    frontier = _read("research/drawdown_frontier/summary.json")
    low = {
        "selected_name": defensive["selected_name"],
        "periods": {
            "evaluation": defensive["periods"]["evaluation"],
            "stress": defensive["periods"]["evaluation_cost_2x"],
        },
        "two_month_windows": defensive["two_month_windows"],
        "weekly_evaluation": defensive["weekly_evaluation"],
        "within_budget": True,
        "historically_profitable": defensive["qualification"][
            "historically_profitable"
        ],
        "deployment_qualified": False,
    }
    result = {"drawdown_10": low}
    for name in ("drawdown_20", "drawdown_50"):
        source = frontier["tiers"][name]
        result[name] = {
            "selected_name": source["selected_name"],
            "periods": {
                "evaluation": source["periods"]["evaluation"],
                "stress": source["periods"]["evaluation_cost_2x"],
            },
            "two_month_windows": source["two_month_windows"],
            "weekly_evaluation": source["weekly_evaluation"],
            "within_budget": source["within_budget"],
            "historically_profitable": source["historically_profitable"],
            "deployment_qualified": False,
        }
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = {
        "long_cash": {"tiers": _long_cash()},
        "short_hedge": _read("research/short_hedge/summary.json"),
        "relative_value": _read("research/relative_value/summary.json"),
        "put_protection": _read("research/put_protection/summary.json"),
    }
    tracks = {}
    for track, source in raw.items():
        tracks[track] = {}
        for tier in TIERS:
            item = source["tiers"][tier]
            evaluation = item["periods"]["evaluation"]
            stress = item["periods"]["stress"]
            weekly = item["weekly_evaluation"]
            tracks[track][tier] = {
                "selected_name": item["selected_name"],
                "evaluation_return": evaluation["net_return"],
                "stress_return": stress["net_return"],
                "max_drawdown": evaluation["max_drawdown"],
                "transaction_costs": evaluation["transaction_costs"],
                "financing_costs": evaluation.get("financing_costs", 0.0),
                "premium_paid": evaluation.get("premium_paid", 0.0),
                "two_month_windows": item["two_month_windows"],
                "profitable_weeks": weekly["profitable_weeks"],
                "losing_weeks": weekly["losing_weeks"],
                "flat_weeks": weekly["flat_weeks"],
                "weekly_lower_95": weekly["mean_weekly_return_lower_95"],
                "within_budget": item["within_budget"],
                "historically_profitable": item["historically_profitable"],
                "deployment_qualified": False,
            }
    preferred = {}
    for tier in TIERS:
        eligible = [
            (track, values[tier])
            for track, values in tracks.items()
            if values[tier]["historically_profitable"]
        ]
        preferred[tier] = max(
            eligible, key=lambda item: item[1]["evaluation_return"]
        )[0]
    summary = {
        "conclusion": (
            "LONG/CASH REMAINS THE BEST HISTORICAL CANDIDATE; "
            "NO TRACK IS DEPLOYMENT QUALIFIED"
        ),
        "period": {
            "development": "2019-01-01 through 2021-12-31",
            "validation": "2022-01-01 through 2023-12-31",
            "evaluation": "2024-01-01 through 2026-10-31",
        },
        "preferred_historical_track": preferred,
        "tracks": tracks,
        "deployment_qualified": False,
        "deployment_reasons": [
            "Every historical period is already inspected.",
            "Every weekly lower 95% confidence bound is nonpositive.",
            "No track has completed a new prospective paper period.",
            "Short, relative-value, and put execution are modeled, not broker verified.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Four-track hedge comparison",
        "",
        "## Decision",
        "",
        "**The existing long/cash trend strategy remains the best historical",
        "candidate at every risk tier. No track is qualified for deployment.**",
        "The BTC short hedge and BTC/ETH relative-value tracks failed the later",
        "evaluation. Protective puts slightly reduced drawdown but surrendered",
        "more return than they protected and failed stress above the 10% tier.",
        "",
        "## Evaluation comparison: January 2024 through October 2026",
        "",
        "| Track | Tier | Net return | Stress return | Max drawdown | Avg two-month return | Positive / negative / flat windows | Weekly lower 95% |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for track, tiers in tracks.items():
        for tier, item in tiers.items():
            windows = item["two_month_windows"]
            lines.append(
                f"| {track.replace('_', ' ')} | {tier.replace('_', ' ')} | "
                f"{item['evaluation_return']:.2%} | {item['stress_return']:.2%} | "
                f"{item['max_drawdown']:.2%} | {windows['average_return']:.2%} | "
                f"{windows['profitable_windows']} / {windows['losing_windows']} / "
                f"{windows['flat_windows']} | {item['weekly_lower_95']:.2%} |"
            )
    lines.extend(
        [
            "",
            "## What each track established",
            "",
            "1. **Long/cash:** positive in all chronological partitions and cost",
            "   stress, but modest later returns and negative weekly confidence bounds.",
            "2. **BTC short hedge:** selected on development/validation, then lost",
            "   money at every evaluation tier. Short rebounds and carry erased gains.",
            "3. **Market-neutral relative value:** later ratio behavior did not",
            "   mean-revert reliably enough to overcome turnover and short carry.",
            "4. **Protective puts:** the 10% tier stayed positive under synthetic",
            "   stress, but underperformed unhedged long/cash for only a small",
            "   drawdown improvement. Higher tiers lost money under stress.",
            "",
            "## Boundaries",
            "",
            "The short and pair tracks use spot prices as derivative proxies and",
            "charge explicit carry. The put track uses Black-Scholes marks from lagged",
            "realized volatility because historical option chains are unavailable.",
            "These assumptions are useful rejection tests, not executable fills.",
            "All history is now inspected. The only valid next profitability test is",
            "a frozen prospective paper observation; increasing leverage cannot turn",
            "these retrospective results into a reliable profit promise.",
            "",
            "No real, paper-broker, short, derivative, or option order was submitted.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
