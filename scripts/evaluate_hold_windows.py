"""Evaluate the fixed 60%-deployed BTC/ETH hold benchmark in two-month windows."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.growth.config import GrowthConfig
from trader.growth.portfolio import execute
from trader.growth.regime import load_long_history

OUT = Path("research/strategy_v2")
SYMBOLS = ("BTC-USDT", "ETH-USDT")
FIRST_WINDOW = pd.Timestamp("2022-01-01", tz="UTC")


def complete_two_month_windows(first: pd.Timestamp, data_end: pd.Timestamp):
    """Yield non-overlapping half-open windows fully covered by the data."""

    start = first
    data_end_exclusive = data_end + timedelta(hours=1)
    while True:
        end = start + pd.DateOffset(months=2)
        if end > data_end_exclusive:
            return
        yield start, end
        start = end


def _drawdown(points: list[dict], initial: float) -> float:
    equity = np.array([initial, *[float(point["equity"]) for point in points]])
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity / peaks - 1))


def summarize(rows: list[dict]) -> dict:
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
        "return_standard_deviation": float(returns.std(ddof=1)),
        "average_max_drawdown": float(drawdowns.mean()),
        "median_max_drawdown": float(np.median(drawdowns)),
        "worst_max_drawdown": float(drawdowns.min()),
        "best_window": rows[int(returns.argmax())]["window"],
        "best_return": float(returns.max()),
        "worst_window": rows[int(returns.argmin())]["window"],
        "worst_return": float(returns.min()),
    }


def main() -> None:
    config = GrowthConfig()
    data = {symbol: load_long_history(symbol) for symbol in SYMBOLS}
    data_end = min(frame.index[-1] for frame in data.values())
    rows = []
    for start, end in complete_two_month_windows(FIRST_WINDOW, data_end):
        sliced = {
            symbol: frame.loc[(frame.index >= start) & (frame.index < end)].dropna()
            for symbol, frame in data.items()
        }
        common = sliced[SYMBOLS[0]].index.intersection(sliced[SYMBOLS[1]].index)
        sliced = {symbol: frame.loc[common] for symbol, frame in sliced.items()}
        decisions = {
            timestamp.value: {
                symbol: {
                    "enter": True,
                    "liquidate": False,
                    "horizon": 24 * 365 * 20,
                    "stop": 0.03,
                }
                for symbol in SYMBOLS
            }
            for timestamp in common
        }
        result = execute(sliced, decisions, config.model_dump(), benchmark=True)
        rows.append(
            {
                "window": f"{start:%Y-%m} to {(end - timedelta(hours=1)):%Y-%m}",
                "start": start.isoformat(),
                "end_exclusive": end.isoformat(),
                "observations": len(common),
                "ending_equity": result["ending_equity"],
                "profit_usd": result["ending_equity"] - config.capital,
                "net_return": result["net_return"],
                "max_drawdown": _drawdown(result["equity"], config.capital),
                "fees": result["fees"],
                "execution_friction": result["execution_friction"],
            }
        )

    summary = summarize(rows)
    payload = {
        "method": (
            "Independent non-overlapping two-month calendar windows; reset to $500, "
            "buy 30% BTC and 30% ETH, keep 40% cash, no active exits"
        ),
        "data_cutoff": data_end.isoformat(),
        "costs": {
            "fee_bps_per_side": config.fee_bps,
            "adverse_execution_bps_per_side": config.friction_bps,
        },
        "summary": summary,
        "windows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hold_2month_windows.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    pd.DataFrame(rows).to_csv(OUT / "hold_2month_windows.csv", index=False)

    lines = [
        "# Independent two-month BTC/ETH hold windows",
        "",
        "Each row resets to **$500**, buys **30% BTC and 30% ETH**, and keeps",
        "**40% cash**. The benchmark has no stop-loss or drawdown exit. Returns",
        "include the configured 10 bp fee and 5 bp adverse execution per side.",
        "Windows are non-overlapping; incomplete November 2026 is excluded.",
        "",
        "## Summary",
        "",
        f"- Complete windows: **{summary['windows']}**",
        f"- Profitable / losing: **{summary['profitable_windows']} / {summary['losing_windows']}**",
        f"- Profitable fraction: **{summary['profitable_fraction']:.1%}**",
        (
            f"- Average P/L per window: **${summary['average_profit_usd']:.2f}** "
            f"(**{summary['average_return']:.2%}**)"
        ),
        (
            f"- Median P/L per window: **${summary['median_profit_usd']:.2f}** "
            f"(**{summary['median_return']:.2%}**)"
        ),
        f"- Average maximum drawdown: **{summary['average_max_drawdown']:.2%}**",
        f"- Median maximum drawdown: **{summary['median_max_drawdown']:.2%}**",
        f"- Worst maximum drawdown: **{summary['worst_max_drawdown']:.2%}**",
        f"- Best window: **{summary['best_window']} ({summary['best_return']:.2%})**",
        f"- Worst window: **{summary['worst_window']} ({summary['worst_return']:.2%})**",
        "",
        "## Windows",
        "",
        "| Window | P/L | Return | Maximum drawdown | Ending value |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['window']} | ${row['profit_usd']:.2f} | "
            f"{row['net_return']:.2%} | {row['max_drawdown']:.2%} | "
            f"${row['ending_equity']:.2f} |"
        )
    lines.extend(
        [
            "",
            "Arithmetic averages describe independent reset windows; they are not a",
            "compounded account return. This is retrospective Binance spot history,",
            "not evidence of target-broker fills or a guarantee of future returns.",
            "The same period is now inspected and cannot be treated as a fresh holdout.",
            "",
        ]
    )
    (OUT / "HOLD_2MONTH_REPORT.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
