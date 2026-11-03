"""Predeclared rolling selection; inspected history remains development evidence."""

import gzip
from pathlib import Path

import numpy as np
import pandas as pd

from trader.db import dumps
from trader.growth.config import GrowthConfig
from trader.growth.models import SYMBOLS, fit, hourly, predict, save
from trader.growth.portfolio import execute
from trader.growth.weekly import weekly_report

OUT = Path("research/growth")
OUT.mkdir(parents=True, exist_ok=True)


def decisions_for(df, pred, horizon, bound):
    vol = df.close.shift(1).pct_change().rolling(48).std() * np.sqrt(24) * 2
    return {
        t.value: {
            "enter": bool(np.isfinite(pred.loc[t]) and pred.loc[t] > bound),
            "horizon": horizon,
            "stop": float(np.clip(vol.loc[t], 0.01, 0.15))
            if np.isfinite(vol.loc[t])
            else 0.03,
        }
        for t in df.index
    }


def run():
    c = GrowthConfig()
    cost = 2 * (c.fee_bps + c.friction_bps) / 10000
    data = {s: hourly(s) for s in SYMBOLS}
    protocol = {
        "capital": 500,
        "risk": c.model_dump(),
        "universe": list(SYMBOLS),
        "training_months": 9,
        "validation_months": 3,
        "calibration": "First validation month; residual quantiles .5/.8; labels mature by calibration end",
        "selection": "Last two validation months: >=20 exits, positive net return in each calendar month, drawdown <10%; maximize net return, otherwise cash",
        "families": ["forest", "boosted"],
        "horizons_hours": [4, 24, 72],
        "confidence_quantiles": [0.5, 0.8],
        "test_start": "2025-11-01",
        "test_end": "2026-10-31",
        "status": "Previously inspected historical periods: development evidence, not pristine holdout",
        "qualification": "52 complete weeks,100 exits,positive net and lower95 week-block bound,drawdown<10%,positive doubled-cost result; then12weeks/30exits forward",
    }
    (OUT / "protocol.json").write_text(dumps(protocol))
    schedule = {}
    trials = []
    versions = []
    for month in pd.date_range("2025-11-01", "2026-10-01", freq="MS", tz="UTC"):
        validation_start = month - pd.DateOffset(months=3)
        calibration_end = validation_start + pd.DateOffset(months=1)
        chosen = {}
        for symbol in SYMBOLS:
            df = data[symbol]
            window = {
                s: d.loc[(d.index >= calibration_end) & (d.index < month)]
                for s, d in data.items()
            }
            candidates = []
            for family in ("forest", "boosted"):
                for horizon in (4, 24, 72):
                    model, meta = fit(
                        df, symbol, validation_start, family, horizon, cost
                    )
                    p = predict(model, df)
                    y = df.open.shift(-horizon) / df.open - 1 - cost
                    maturity = df.index.to_series().shift(-horizon)
                    calibration = (
                        (df.index >= validation_start)
                        & (df.index < calibration_end)
                        & (maturity < calibration_end)
                        & p.notna()
                        & y.notna()
                    )
                    for confidence in (0.5, 0.8):
                        bound = max(
                            0,
                            float(
                                (p[calibration] - y[calibration]).quantile(confidence)
                            ),
                        )
                        dec = {
                            k: {symbol: v}
                            for k, v in decisions_for(
                                window[symbol], p, horizon, bound
                            ).items()
                        }
                        r = execute(window, dec, c.model_dump())
                        w = weekly_report(r["equity"], 500, r["completed_trades"])
                        ep = pd.Series(
                            [x["equity"] for x in r["equity"]],
                            index=pd.to_datetime([x["timestamp"] for x in r["equity"]]),
                        )
                        ends = ep.resample("ME").last()
                        monthly = ends / np.r_[500, ends.iloc[:-1].to_numpy()] - 1
                        eligible = (
                            r["completed_trades"] >= c.min_validation_exits
                            and w["max_drawdown"] > -0.1
                            and (monthly > 0).all()
                        )
                        trial = {
                            "month": str(month),
                            "symbol": symbol,
                            "family": family,
                            "horizon": horizon,
                            "confidence": confidence,
                            "bound": bound,
                            "return": r["net_return"],
                            "exits": r["completed_trades"],
                            "drawdown": w["max_drawdown"],
                            "eligible": bool(eligible),
                        }
                        trials.append(trial)
                        candidates.append(trial)
            passing = [x for x in candidates if x["eligible"]]
            if passing:
                winner = max(passing, key=lambda x: x["return"])
                model, meta = fit(
                    df, symbol, month, winner["family"], winner["horizon"], cost
                )
                meta.update(
                    calibration_bound=winner["bound"],
                    confidence=winner["confidence"],
                    status="research candidate; forward qualification pending",
                )
                manifest = save(model, meta)
                versions.append(manifest)
                chosen[symbol] = manifest
                p = predict(model, df)
                end = month + pd.DateOffset(months=1)
                for k, v in decisions_for(
                    df.loc[(df.index >= month) & (df.index < end)],
                    p,
                    winner["horizon"],
                    winner["bound"],
                ).items():
                    schedule.setdefault(k, {})[symbol] = v
        (OUT / "trials.json").write_text(dumps(trials))
        (OUT / "versions.json").write_text(dumps(versions))
        print(str(month), {s: m["id"] for s, m in chosen.items()}, flush=True)
    # Freeze all monthly selections before running the continuous final account.
    (OUT / "decision_schedule.json.gz").write_bytes(
        gzip.compress(dumps(schedule).encode())
    )
    data = {s: d.loc["2025-11-01":"2026-10-31"] for s, d in data.items()}
    results = {}
    for label, mult in [("selected", 1), ("cost_1.5x", 1.5), ("cost_2x", 2)]:
        config = c.model_dump()
        config.update(fee_bps=c.fee_bps * mult, friction_bps=c.friction_bps * mult)
        results[label] = execute(data, schedule, config)
    results["cash"] = execute(data, {}, c.model_dump())
    hold = {
        t.value: {s: {"enter": True, "horizon": 72, "stop": 0.03} for s in SYMBOLS}
        for t in data[SYMBOLS[0]].index
    }
    results["hold"] = execute(data, hold, c.model_dump(), benchmark=True)
    trend = {}
    for s, d in data.items():
        full = hourly(s)
        past = full.close.shift(1)
        p = (past / past.rolling(168).mean() - 1).loc[d.index]
        for t in d.index:
            trend.setdefault(t.value, {})[s] = {
                "enter": bool(p.loc[t] > 0.01),
                "horizon": 24,
                "stop": 0.03,
            }
    results["trend"] = execute(data, trend, c.model_dump())
    summary = {}
    for label, r in results.items():
        report = weekly_report(
            r["equity"],
            500,
            r["completed_trades"],
            results["cost_2x"]["net_return"] > 0,
        )
        r["weekly"] = report
        with gzip.open(OUT / (label + ".json.gz"), "wt") as f:
            f.write(dumps(r))
        summary[label] = {
            **report,
            "ending_equity": r["ending_equity"],
            "same_trade_gross_return": r["same_trade_gross_return"],
            "fees": r["fees"],
            "execution_friction": r["execution_friction"],
        }
    (OUT / "summary.json").write_text(dumps(summary))
    print(dumps(summary), flush=True)


if __name__ == "__main__":
    run()
