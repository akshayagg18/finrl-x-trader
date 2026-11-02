import numpy as np


def metrics(points, orders, initial):
    if not points:
        return {"observations": 0, "note": "No observations"}
    if all("date" in p for p in points):
        days = {}
        for point in points:
            key = point["date"][:10]
            prior_flow = days.get(key, {}).get("flow", 0)
            days[key] = {**point, "flow": prior_flow + point.get("flow", 0)}
        points = [days[k] for k in sorted(days)]
    v = np.asarray([p["equity"] for p in points], float)
    flows = np.asarray([p.get("flow", 0) for p in points], float)
    prev = np.r_[initial, v[:-1]]
    r = (v - flows) / prev - 1
    growth = np.cumprod(1 + r)
    total = float(growth[-1] - 1)
    std = float(np.std(r, ddof=1)) if len(r) > 1 else 0
    down = np.minimum(r, 0)
    downstd = float(np.sqrt(np.mean(down**2)))
    draw = growth / np.maximum.accumulate(np.r_[1, growth])[1:] - 1
    sells = [
        o["realized"] for o in orders if o["side"] == "sell" and o["filled_qty"] > 0
    ]
    wins = [x for x in sells if x > 0]
    losses = [x for x in sells if x < 0]
    meaningful = len(v) >= 30
    return {
        "observations": len(v),
        "total_return": total,
        "annualized_return": float((1 + total) ** (252 / len(v)) - 1)
        if len(v) >= 252
        else None,
        "volatility": std * np.sqrt(252) if meaningful else None,
        "sharpe": float(np.mean(r) / std * np.sqrt(252))
        if meaningful and std > 0
        else None,
        "sortino": float(np.mean(r) / downstd * np.sqrt(252))
        if meaningful and downstd > 0
        else None,
        "max_drawdown": float(min(0, draw.min())),
        "win_rate": len(wins) / len(sells) if sells else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "average_gain": float(np.mean(wins)) if wins else None,
        "average_loss": float(np.mean(losses)) if losses else None,
        "turnover": sum(o["filled_qty"] * (o["fill_price"] or 0) for o in orders)
        / float(np.mean(v)),
        "transaction_costs": sum(o["fees"] for o in orders),
        "note": "Risk ratios require 30 daily observations; annualized return requires 252. Win statistics are realized sale fills, not inferred round trips. Risk-free rate 0.",
    }
