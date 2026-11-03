"""Cash-only, long-only opening-range-breakout research adaptation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def opening_range_backtest(
    data: dict[str, pd.DataFrame],
    *,
    capital: float = 500.0,
    risk_fraction: float = 0.005,
    max_position_fraction: float = 0.50,
    relative_volume_min: float = 1.0,
    friction_bps: float = 3.0,
) -> dict:
    """Evaluate the paper's core filters with feasible small-account sizing.

    Input bars must be regular-session 15-minute bars.  This is explicitly a
    15-minute adaptation: the repository has no 5-minute equity history.
    Fractional shares are used, positions are closed the same day, and proceeds
    are not reused until the next session (a conservative T+1-compatible model).
    """
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol, frame in data.items():
        local = frame.tz_convert("America/New_York")
        for day, group in local.groupby(local.index.date):
            sessions.setdefault(pd.Timestamp(day), {})[symbol] = group
    cash = capital
    points, trades, diagnostics = [], [], []
    opening_history: dict[str, list[float]] = {s: [] for s in data}
    daily_history: dict[str, list[dict]] = {s: [] for s in data}
    total_costs = turnover = 0.0
    for day in sorted(sessions):
        candidates = []
        for symbol, bars in sessions[day].items():
            if len(bars) < 2:
                continue
            first = bars.iloc[0]
            history = daily_history[symbol]
            open_volumes = opening_history[symbol]
            prior = history[-14:]
            if len(prior) >= 14 and len(open_volumes) >= 14:
                previous_close = prior[-1]["close"]
                true_ranges = [
                    max(x["high"] - x["low"], abs(x["high"] - x["previous_close"]), abs(x["low"] - x["previous_close"]))
                    for x in prior
                ]
                atr = float(np.mean(true_ranges))
                avg_volume = float(np.mean([x["volume"] for x in prior]))
                relative_volume = float(first.volume / np.mean(open_volumes[-14:]))
                eligible = (
                    first.open > 5
                    and avg_volume >= 1_000_000
                    and atr > 0.50
                    and relative_volume >= relative_volume_min
                    and first.close > first.open
                )
                diagnostics.append(
                    {
                        "date": str(day.date()),
                        "symbol": symbol,
                        "relative_volume": relative_volume,
                        "atr_14": atr,
                        "average_volume_14": avg_volume,
                        "direction": "long" if first.close > first.open else "short_rejected",
                        "eligible": bool(eligible),
                    }
                )
                if eligible:
                    candidates.append((relative_volume, symbol, bars, atr))
            opening_history[symbol].append(float(first.volume))
            prior_close = daily_history[symbol][-1]["close"] if daily_history[symbol] else float(first.open)
            daily_history[symbol].append(
                {
                    "high": float(bars.high.max()),
                    "low": float(bars.low.min()),
                    "close": float(bars.close.iloc[-1]),
                    "volume": float(bars.volume.sum()),
                    "previous_close": float(prior_close),
                }
            )
        # Paper ranks the top 20.  Only three symbols exist in the local sample.
        candidates.sort(reverse=True)
        day_start_cash = cash
        slots = max(1, len(candidates[:20]))
        for _, symbol, bars, atr in candidates[:20]:
            opening_high = float(bars.high.iloc[0])
            breakout = bars.iloc[1:][bars.high.iloc[1:] > opening_high]
            if breakout.empty:
                continue
            ts = breakout.index[0]
            bar = breakout.iloc[0]
            mid_entry = max(float(bar.open), opening_high)
            entry = mid_entry * (1 + friction_bps / 10_000)
            stop_distance = 0.10 * atr
            risk_budget = capital * risk_fraction
            risk_units = risk_budget / stop_distance
            cash_cap = min(cash / max(1, slots), capital * max_position_fraction)
            units = min(risk_units, cash_cap / entry)
            if units * entry < 1:
                continue
            notional = units * entry
            cash -= notional
            stop = entry - stop_distance
            later = bars.loc[ts:]
            stopped = bool((later.low <= stop).any())
            if stopped:
                stop_ts = later.index[(later.low <= stop)][0]
                exit_mid = min(float(later.loc[stop_ts, "open"]), stop) if float(later.loc[stop_ts, "open"]) < stop else stop
                exit_time = stop_ts
            else:
                exit_mid = float(bars.close.iloc[-1])
                exit_time = bars.index[-1]
            exit_price = exit_mid * (1 - friction_bps / 10_000)
            proceeds = units * exit_price
            cash += proceeds
            pnl = proceeds - notional
            cost = units * (entry - mid_entry) + units * (exit_mid - exit_price)
            total_costs += cost
            turnover += notional + proceeds
            trades.append(
                {
                    "date": str(day.date()),
                    "symbol": symbol,
                    "entry_time": str(ts),
                    "exit_time": str(exit_time),
                    "entry": entry,
                    "exit": exit_price,
                    "units": units,
                    "pnl": pnl,
                    "stopped": stopped,
                    "cost": cost,
                }
            )
        points.append({"timestamp": str(day.tz_localize("UTC")), "equity": cash, "day_start_cash": day_start_cash})
    values = pd.Series([p["equity"] for p in points], index=pd.to_datetime([p["timestamp"] for p in points], utc=True))
    returns = values.pct_change().dropna()
    drawdown = values / values.cummax() - 1
    pnl = [t["pnl"] for t in trades]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x < 0]
    metrics = {
        "net_profit_usd": cash - capital,
        "net_return": cash / capital - 1,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "completed_trades": len(trades),
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "average_net_profit_per_trade": float(np.mean(pnl)) if pnl else None,
        "total_costs": total_costs,
        "turnover": turnover / values.mean() if len(values) else 0.0,
        "sharpe": float(returns.mean() / returns.std() * np.sqrt(252)) if len(returns) >= 30 and returns.std() > 0 else None,
    }
    return {
        "initial": capital,
        "ending_equity": cash,
        "points": points,
        "trades": trades,
        "diagnostics": diagnostics,
        "metrics": metrics,
        "limitations": [
            "15-minute adaptation; the published strategy uses a 5-minute opening range",
            "Three surviving large-cap/ETF symbols and about 60 sessions, not the paper's 7,000-stock survivorship-free universe",
            "Long-only, fractional, no leverage; the paper is long-short with up to 4x leverage and $25,000 capital",
        ],
    }
