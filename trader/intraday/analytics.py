"""Analytics from actual Nautilus fills and daily marked equity, not signal intentions."""

import numpy as np
import pandas as pd


def analyze(result):
    p = pd.DataFrame(result["equity"])
    v = p.equity.astype(float)
    series = pd.Series(v.to_numpy(), index=pd.to_datetime(p.timestamp, utc=True))
    daily = series.resample("1D").last().dropna()
    returns = daily.pct_change()
    returns.iloc[0] = daily.iloc[0] / result["config"]["capital"] - 1
    fills = result["fills"]
    fees = 0
    basis = 0
    units = 0
    entry = None
    pnl = []
    holds = []
    turnover = 0
    for f in fills:
        qty = float(f["filled_qty"])
        price = float(f["avg_px"])
        fee = sum(float(str(x).split()[0]) for x in f["commissions"])
        fees += fee
        turnover += qty * price
        if f["side"] == "BUY":
            basis += qty * price + fee
            units += qty
            entry = pd.Timestamp(f["ts_last"])
        elif units > 0:
            portion = min(1, qty / units)
            cost = basis * portion
            pnl.append(qty * price - fee - cost)
            holds.append((pd.Timestamp(f["ts_last"]) - entry).total_seconds() / 60)
            units -= qty
            basis -= cost
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    streak = worst = 0
    for x in pnl:
        streak = streak + 1 if x < 0 else 0
        worst = max(worst, streak)
    annual = 365 if "-" in result["config"]["symbol"] else 252
    std = returns.std()
    down = np.sqrt(np.mean(np.minimum(returns, 0) ** 2))
    return {
        "daily_observations": len(daily),
        "annualized_return": (1 + result["net_return"]) ** (annual / len(daily)) - 1
        if len(daily) >= annual
        else None,
        "sharpe": float(returns.mean() / std * np.sqrt(annual))
        if len(daily) >= 30 and std > 0
        else None,
        "sortino": float(returns.mean() / down * np.sqrt(annual))
        if len(daily) >= 30 and down > 0
        else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "average_winner": float(np.mean(wins)) if wins else None,
        "average_loser": float(np.mean(losses)) if losses else None,
        "average_net_profit_per_exit": float(np.mean(pnl)) if pnl else None,
        "completed_exits": len(pnl),
        "fees": fees,
        "estimated_spread_slippage": turnover
        * result["config"]["friction_bps"]
        / 10000,
        "turnover": turnover / v.mean(),
        "average_holding_minutes": float(np.mean(holds)) if holds else None,
        "time_invested": float((p.cash < p.equity - 0.01).mean()),
        "worst_day": float(returns.min()),
        "worst_losing_streak": worst,
        "risk_free_rate": 0,
    }
