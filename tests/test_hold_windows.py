import pandas as pd

from scripts.evaluate_hold_windows import complete_two_month_windows, summarize


def test_complete_two_month_windows_and_summary():
    windows = list(
        complete_two_month_windows(
            pd.Timestamp("2022-01-01", tz="UTC"),
            pd.Timestamp("2026-10-31 23:00:00", tz="UTC"),
        )
    )
    assert len(windows) == 29
    assert windows[0] == (
        pd.Timestamp("2022-01-01", tz="UTC"),
        pd.Timestamp("2022-03-01", tz="UTC"),
    )
    assert windows[-1] == (
        pd.Timestamp("2026-09-01", tz="UTC"),
        pd.Timestamp("2026-11-01", tz="UTC"),
    )

    rows = [
        {"window": "gain", "net_return": 0.1, "profit_usd": 50, "max_drawdown": -0.05},
        {"window": "loss", "net_return": -0.2, "profit_usd": -100, "max_drawdown": -0.3},
    ]
    result = summarize(rows)
    assert result["average_profit_usd"] == -25
    assert result["average_return"] == -0.05
    assert result["average_max_drawdown"] == -0.175
    assert result["profitable_windows"] == result["losing_windows"] == 1
    assert result["best_window"] == "gain"
    assert result["worst_window"] == "loss"
