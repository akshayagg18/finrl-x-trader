"""Persistent local simulation through deterministic Nautilus replay reconstruction.

Each session owns virtual capital only. No broker orders are issued. All session
config/data are frozen; restarts reconstruct the same engine history, then append
new fills atomically. No forced liquidation occurs between cycles.
"""

import hashlib
import json
import uuid

import pandas as pd
from filelock import FileLock

from trader.db import dumps, now

from .engine import Experiment, backtest, load

SCHEMA = """
CREATE TABLE IF NOT EXISTS intraday_sessions(id TEXT PRIMARY KEY, created TEXT NOT NULL, config TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, cursor INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 0, policies TEXT NOT NULL DEFAULT '[]', data_hash TEXT NOT NULL, result TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS intraday_fills(session TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(session,id));
CREATE TABLE IF NOT EXISTS intraday_cycles(session TEXT NOT NULL, cursor INTEGER NOT NULL, result_hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(session,cursor));
"""


def initialize(db):
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def digest(df):
    return hashlib.sha256(df.to_csv().encode()).hexdigest()


def create(db, config, start, end):
    initialize(db)
    c = Experiment.model_validate(config)
    df = load(c.symbol, c.interval)
    dates = df.loc[start:end].index
    if len(dates) < 2:
        raise ValueError("Require at least two replay bars")
    if c.strategy == "ml":
        from .ml import prediction

        _, meta = prediction(df, c.model_id, c.symbol, c.interval)
        if dates[0] < pd.Timestamp(meta["cutoff"]):
            raise ValueError("Model not available at replay start")
    sid = uuid.uuid4().hex
    with FileLock(db.path + ".intraday.lock"), db.connect() as conn:
        if conn.execute("SELECT 1 FROM intraday_sessions WHERE active=1").fetchone():
            raise ValueError("Pause or stop the active session before starting another")
        conn.execute(
            "INSERT INTO intraday_sessions(id,created,config,start,end,data_hash) VALUES(?,?,?,?,?,?)",
            (
                sid,
                now(),
                dumps(c.model_dump()),
                str(dates[0]),
                str(dates[-1]),
                digest(df),
            ),
        )
    return sid


def sessions(db):
    initialize(db)
    return db.rows(
        "SELECT id,created,config,start,end,cursor,active,policies,error FROM intraday_sessions ORDER BY created DESC"
    )


def inspect(db, sid):
    initialize(db)
    rows = db.rows("SELECT * FROM intraday_sessions WHERE id=?", (sid,))
    if not rows:
        raise ValueError("Unknown simulation session")
    r = rows[0]
    for key in ("config", "policies", "result"):
        r[key] = json.loads(r[key]) if r[key] else None
    r["active"] = bool(r["active"])
    r["mode"] = "local historical simulation"
    r["next_operation"] = "next scheduler tick (10s)" if r["active"] else None
    return r


def control(db, sid, action):
    if action not in ("start", "pause", "resume", "stop", "liquidate"):
        raise ValueError("Unknown simulation control")
    with FileLock(db.path + ".intraday.lock"):
        r = inspect(db, sid)
        if action in ("start", "resume") and db.state("kill", False):
            raise ValueError("Global kill switch is active")
        if action in ("start", "resume", "pause", "liquidate"):
            for other in sessions(db):
                if other["active"] and other["id"] != sid:
                    raise ValueError("Another virtual session is active")
        data = load(r["config"]["symbol"], r["config"]["interval"]).loc[
            r["start"] : r["end"]
        ]
        ts = str(data.index[min(r["cursor"], len(data) - 1)])
        policies = r["policies"] + [
            {
                "at": ts,
                "mode": {"pause": "pause", "liquidate": "flatten"}.get(action, "trade"),
            }
        ]
        with db.connect() as conn:
            conn.execute(
                "UPDATE intraday_sessions SET active=?,policies=? WHERE id=?",
                (int(action != "stop"), dumps(policies), sid),
            )
        db.event("intraday:" + sid, "control", {"action": action, "effective_bar": ts})
    return inspect(db, sid)


def step(db, sid, bars=16):
    if not 1 <= bars <= 1000:
        raise ValueError("Replay batch must be 1–1000 bars")
    with FileLock(db.path + ".intraday.lock", timeout=1):
        r = inspect(db, sid)
        if db.state("kill", False):
            with db.connect() as conn:
                conn.execute(
                    "UPDATE intraday_sessions SET active=0,error=? WHERE id=?",
                    ("Global kill switch", sid),
                )
            return inspect(db, sid)
        if not r["active"]:
            return r
        c = r["config"]
        df = load(c["symbol"], c["interval"])
        if digest(df) != r["data_hash"]:
            raise ValueError("Frozen replay dataset changed; no execution")
        selected = df.loc[r["start"] : r["end"]]
        cursor = min(len(selected), r["cursor"] + bars)
        if cursor == r["cursor"]:
            return r
        # Engine reconstructs deterministic prior state, never submits repeated external orders.
        result = backtest(
            c,
            r["start"],
            str(selected.index[cursor - 1]),
            liquidate=False,
            policies=r["policies"],
        )
        state = dumps(result)
        with db.connect() as conn:
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
                conn.execute(
                    "INSERT OR IGNORE INTO intraday_fills VALUES(?,?,?)",
                    (sid, fid, dumps(fill)),
                )
            conn.execute(
                "INSERT INTO intraday_cycles VALUES(?,?,?,?)",
                (sid, cursor, hashlib.sha256(state.encode()).hexdigest(), now()),
            )
            conn.execute(
                "UPDATE intraday_sessions SET cursor=?,result=?,active=?,error=NULL WHERE id=?",
                (cursor, state, int(cursor < len(selected)), sid),
            )
        db.event(
            "intraday:" + sid,
            "cycle",
            {
                "cursor": cursor,
                "equity": result["ending_equity"],
                "quantity": result["quantity"],
            },
        )
        return inspect(db, sid)


def tick(db):
    initialize(db)
    for row in db.rows("SELECT id FROM intraday_sessions WHERE active=1"):
        try:
            step(db, row["id"])
        except Exception as exc:  # noqa: BLE001 -- fail closed, preserve last atomic state
            with db.connect() as conn:
                conn.execute(
                    "UPDATE intraday_sessions SET active=0,error=? WHERE id=?",
                    (type(exc).__name__, row["id"]),
                )
            db.event(
                "intraday:" + row["id"],
                "scheduler_blocked",
                {"error": type(exc).__name__},
            )
