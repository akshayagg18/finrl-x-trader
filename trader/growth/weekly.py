import numpy as np
import pandas as pd


def weekly_report(points, initial, exits=0, stress_positive=False, forward=False):
    if not points:
        return {"qualified": False, "reasons": ["No observations"]}
    s = pd.Series(
        [p["equity"] for p in points],
        index=pd.to_datetime([p["timestamp"] for p in points], utc=True),
    ).sort_index()
    # Monday-start weeks in Singapore; all observations are marked values.
    local = s.tz_convert("Asia/Singapore")
    values = (
        local.resample("W-SUN", closed="left", label="left", offset="1D")
        .last()
        .dropna()
    )
    # Use explicit local Monday dates, avoiding ambiguous resampling labels.
    keys = [
        (t.normalize() - pd.Timedelta(days=t.weekday())).date().isoformat()
        for t in local.index
    ]
    values = pd.Series(local.to_numpy(), index=keys).groupby(level=0).last()
    r = values / pd.Series([initial, *values.iloc[:-1]], index=values.index) - 1
    # Exclude partial first/last weeks from consistency/confidence claims.
    first = local.index[0]
    last = local.index[-1]
    complete = r.copy()
    first_monday = first.normalize() - pd.Timedelta(days=first.weekday())
    last_monday = last.normalize() - pd.Timedelta(days=last.weekday())
    if first > first_monday:
        complete = complete.drop(first_monday.date().isoformat(), errors="ignore")
    if last < last_monday + pd.Timedelta(days=7) - pd.Timedelta(hours=1):
        complete = complete.drop(last_monday.date().isoformat(), errors="ignore")
    rng = np.random.default_rng(17)
    lower = None
    if len(complete) >= 8:
        a = complete.to_numpy()
        n = len(a)
        boot = []
        for _ in range(2000):
            starts = rng.integers(0, n, size=(n + 3) // 4)
            sample = np.concatenate([a[(st + np.arange(4)) % n] for st in starts])[:n]
            boot.append(float(np.mean(sample)))
        lower = float(np.quantile(boot, 0.025))
    arr = np.r_[initial, s.to_numpy()]
    draw = arr / np.maximum.accumulate(arr) - 1
    streak = worst = 0
    for x in complete:
        streak = streak + 1 if x < 0 else 0
        worst = max(worst, streak)
    underwater = 0
    recovery = 0
    for x in draw:
        underwater = underwater + 1 if x < 0 else 0
        recovery = max(recovery, underwater)
    reasons = []
    if len(complete) < (12 if forward else 52):
        reasons.append("Insufficient complete weeks")
    if exits < (30 if forward else 100):
        reasons.append("Insufficient completed trades")
    if s.iloc[-1] <= initial:
        reasons.append("Nonpositive net return")
    if draw.min() <= -0.1:
        reasons.append("Drawdown exceeds tolerance")
    if not stress_positive:
        reasons.append("Doubled-cost robustness not established")
    if lower is None or lower <= 0:
        reasons.append("Positive lower 95% block-bootstrap bound not established")
    return {
        "qualified": not reasons,
        "reasons": reasons,
        "net_return": float(s.iloc[-1] / initial - 1),
        "max_drawdown": float(draw.min()),
        "complete_weeks": len(complete),
        "profitable_weeks": int((complete > 0).sum()),
        "losing_weeks": int((complete < 0).sum()),
        "flat_weeks": int((complete == 0).sum()),
        "profitable_week_fraction": float((complete > 0).mean())
        if len(complete)
        else None,
        "median_week": float(complete.median()) if len(complete) else None,
        "worst_week": float(complete.min()) if len(complete) else None,
        "longest_losing_streak": worst,
        "longest_underwater_observations": recovery,
        "mean_weekly_return_lower_95": lower,
        "completed_trades": exits,
        "weeks": r.to_dict(),
        "partial_weeks_excluded_from_statistics": len(r) - len(complete),
    }
