"""Public-observation forward simulation. No private broker APIs or real orders."""

import hashlib
import json
from datetime import UTC, datetime

import pandas as pd
import requests
from filelock import FileLock

from trader.db import dumps, now

from .config import GrowthConfig
from .models import SYMBOLS, predict, restore
from .portfolio import execute
from .weekly import weekly_report

SCHEMA = """CREATE TABLE IF NOT EXISTS growth_forward(id INTEGER PRIMARY KEY CHECK(id=1),created TEXT NOT NULL,active INTEGER NOT NULL,config TEXT NOT NULL,models TEXT NOT NULL,result TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS growth_observations(bucket INTEGER PRIMARY KEY,received TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS growth_fills(id TEXT PRIMARY KEY,body TEXT NOT NULL);"""


def initialize(db):
    with db.connect() as c:
        c.executescript(SCHEMA)


def configure(db, config, models=None):
    initialize(db)
    c = GrowthConfig.model_validate(config)
    with FileLock(db.path + ".growth.lock"):
        if db.rows("SELECT 1 FROM growth_observations LIMIT 1"):
            raise ValueError("Forward configuration frozen after first observation")
        models = models or {}
        if models:
            from pathlib import Path

            path = Path("research/growth/summary.json")
            summary = json.loads(path.read_text()) if path.exists() else {}
            if not summary.get("selected", {}).get("qualified", False):
                raise ValueError(
                    "No historically qualified model; forward cash observation only"
                )
        for symbol, mid in models.items():
            if symbol not in SYMBOLS:
                raise ValueError("Invalid symbol")
            _, m = restore(mid)
            if m["symbol"] != symbol:
                raise ValueError("Model mismatch")
        with db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO growth_forward VALUES(1,?,0,?,?,NULL,NULL)",
                (now(), dumps(c.model_dump()), dumps(models)),
            )
    return status(db)


def status(db):
    initialize(db)
    rows = db.rows("SELECT * FROM growth_forward")
    if not rows:
        return {"configured": False, "mode": "forward local simulation"}
    r = rows[0]
    for k in ("config", "models", "result"):
        r[k] = json.loads(r[k]) if r[k] else None
    r["active"] = bool(r["active"])
    r["mode"] = "forward local simulation"
    r["observations"] = db.rows("SELECT COUNT(*) AS n FROM growth_observations")[0]["n"]
    if r["result"]:
        r["qualification"] = weekly_report(
            r["result"]["equity"],
            r["config"]["capital"],
            r["result"]["completed_trades"],
            r["result"].get("doubled_cost_return", 0) > 0,
            forward=True,
        )
    return r


def control(db, action):
    initialize(db)
    if action not in ("start", "stop"):
        raise ValueError("Unknown forward action")
    if action == "start" and db.state("kill", False):
        raise ValueError("Global kill active")
    if not db.rows("SELECT 1 FROM growth_forward"):
        raise ValueError("Configure forward account first")
    db.set_state("growth_forward_enabled", True)
    with FileLock(db.path + ".growth.lock"), db.connect() as c:
        c.execute(
            "UPDATE growth_forward SET active=? WHERE id=1", (int(action == "start"),)
        )
    return status(db)


def observe(at=None):
    received = pd.Timestamp(at or datetime.now(UTC))
    out = {}
    for symbol in SYMBOLS:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": symbol},
            timeout=10,
        )
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise ValueError("Quote provider error")
        q = j["data"][0]
        bid = float(q["bidPx"])
        ask = float(q["askPx"])
        stamp = int(q["ts"])
        if (
            not (0 < bid <= ask)
            or abs(received.timestamp() * 1000 - stamp) > 30000
            or (ask / bid - 1) > 0.005
        ):
            raise ValueError("Invalid, stale or excessive-spread quote")
        out[symbol] = {"bid": bid, "ask": ask, "provider_timestamp": stamp}
    return received, out


def tick(db, observation=None):
    initialize(db)
    with FileLock(db.path + ".growth.lock", timeout=1):
        state = status(db)
        if not state.get("active"):
            return state
        if db.state("kill", False):
            with db.connect() as c:
                c.execute(
                    "UPDATE growth_forward SET active=0,error=?", ("Global kill",)
                )
            return status(db)
        try:
            at, quotes = observation or observe()
            at = pd.Timestamp(at)
            if at.tzinfo is None:
                raise ValueError("Observation must be UTC-aware")
            bucket = int(at.timestamp() // 3600)
            if db.rows("SELECT 1 FROM growth_observations WHERE bucket=?", (bucket,)):
                return status(db)
            if db.rows("SELECT 1 FROM growth_observations WHERE bucket>?", (bucket,)):
                raise ValueError("Out-of-order observation")
            decisions = {}
            for s, mid in state["models"].items():
                model, meta = restore(mid)
                if pd.Timestamp(meta["cutoff"]) > at:
                    raise ValueError("Future model")
                # Stale models fail closed; monthly research must produce a freshly validated version.
                if (at - pd.Timestamp(meta["cutoff"])).days > 31:
                    raise ValueError("Monthly model validation overdue")
                r = requests.get(
                    "https://www.okx.com/api/v5/market/history-candles",
                    params={"instId": s, "bar": "1H", "limit": 300},
                    timeout=10,
                )
                r.raise_for_status()
                j = r.json()
                rows = [x for x in j["data"] if x[-1] == "1"]
                frame = pd.DataFrame(
                    [[float(x[i]) for i in range(1, 6)] for x in rows],
                    columns=["open", "high", "low", "close", "volume"],
                    index=pd.to_datetime(
                        [int(x[0]) for x in rows], unit="ms", utc=True
                    ),
                ).sort_index()
                frame = frame[frame.index + pd.Timedelta(hours=1) <= at]
                if frame.empty or at - (
                    frame.index[-1] + pd.Timedelta(hours=1)
                ) > pd.Timedelta(hours=1):
                    raise ValueError("Stale feature data")
                # Add decision-time row; features shift and use only completed history.
                decision_time = at.floor("h")
                frame.loc[decision_time] = frame.iloc[-1]
                pred = float(predict(model, frame).loc[decision_time])
                vol = frame.close.shift(1).pct_change().rolling(48).std().iloc[-1]
                decisions[s] = {
                    "enter": bool(pred > meta["calibration_bound"]),
                    "horizon": meta["horizon"],
                    "stop": float(max(0.01, min(0.15, 2 * vol * 24**0.5))),
                }
            body = {"quotes": quotes, "decisions": decisions, "models": state["models"]}
            records = [
                {"received": x["received"], "body": json.loads(x["body"])}
                for x in db.rows("SELECT * FROM growth_observations ORDER BY bucket")
            ] + [{"received": str(at), "body": body}]
            indexes = pd.to_datetime([r["received"] for r in records], utc=True)
            data = {
                s: pd.DataFrame(
                    {
                        "open": [
                            (
                                r["body"]["quotes"][s]["bid"]
                                + r["body"]["quotes"][s]["ask"]
                            )
                            / 2
                            for r in records
                        ]
                    },
                    index=indexes,
                )
                for s in SYMBOLS
            }
            observed = {
                t.value: {
                    s: (r["body"]["quotes"][s]["bid"], r["body"]["quotes"][s]["ask"])
                    for s in SYMBOLS
                }
                for t, r in zip(indexes, records)
            }
            signals = {
                t.value: r["body"]["decisions"] for t, r in zip(indexes, records)
            }
            # Explicit additional slippage beyond the observed spread.
            slip = state["config"]["friction_bps"] / 10000
            observed = {
                t: {s: (b * (1 - slip), a * (1 + slip)) for s, (b, a) in q.items()}
                for t, q in observed.items()
            }
            result = execute(data, signals, state["config"], observed_quotes=observed)
            stress_config = {
                **state["config"],
                "fee_bps": state["config"]["fee_bps"] * 2,
            }
            stress_quotes = {
                t: {
                    sym: (
                        max(
                            0.000001,
                            2 * b
                            - float(data[sym].loc[pd.Timestamp(t, tz="UTC"), "open"]),
                        ),
                        2 * a - float(data[sym].loc[pd.Timestamp(t, tz="UTC"), "open"]),
                    )
                    for sym, (b, a) in q.items()
                }
                for t, q in observed.items()
            }
            result["doubled_cost_return"] = execute(
                data, signals, stress_config, observed_quotes=stress_quotes
            )["net_return"]

            with db.connect() as c:
                c.execute(
                    "INSERT INTO growth_observations VALUES(?,?,?)",
                    (bucket, str(at), dumps(body)),
                )
                for fill in result["fills"]:
                    fid = hashlib.sha256(
                        dumps(
                            [
                                fill["instrument_id"],
                                fill["ts_last"],
                                fill["side"],
                                fill["filled_qty"],
                                fill["avg_px"],
                            ]
                        ).encode()
                    ).hexdigest()
                    c.execute(
                        "INSERT OR IGNORE INTO growth_fills VALUES(?,?)",
                        (fid, dumps(fill)),
                    )
                c.execute(
                    "UPDATE growth_forward SET result=?,error=NULL WHERE id=1",
                    (dumps(result),),
                )
        except Exception as exc:  # noqa: BLE001 -- fail closed, no unverified trades
            with db.connect() as c:
                c.execute(
                    "UPDATE growth_forward SET active=0,error=? WHERE id=1",
                    (type(exc).__name__,),
                )
            db.event("growth_forward", "blocked", {"reason": type(exc).__name__})
    return status(db)


def promote(db, models):
    """Append a future decision-time model change without resetting the account."""
    from pathlib import Path

    report = Path("research/growth/summary.json")
    summary = json.loads(report.read_text()) if report.exists() else {}
    if models and not summary.get("selected", {}).get("qualified", False):
        raise ValueError("No historically qualified model")
    at = pd.Timestamp.now(tz="UTC")
    for symbol, mid in models.items():
        if symbol not in SYMBOLS:
            raise ValueError("Invalid instrument")
        _, meta = restore(mid)
        cutoff = pd.Timestamp(meta["cutoff"])
        if meta["symbol"] != symbol or not cutoff <= at < cutoff + pd.Timedelta(
            days=31
        ):
            raise ValueError("Model unavailable or outdated")
    with FileLock(db.path + ".growth.lock"):
        if not db.rows("SELECT 1 FROM growth_forward"):
            raise ValueError("Configure forward account first")
        with db.connect() as conn:
            conn.execute(
                "UPDATE growth_forward SET models=? WHERE id=1", (dumps(models),)
            )
        db.event(
            "growth_forward",
            "model_versions_changed",
            {"at": str(at), "models": models},
        )
    return status(db)
