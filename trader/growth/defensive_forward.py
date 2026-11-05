"""Persistent forward-paper observation for the selected defensive strategy."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import requests
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from trader.db import dumps, now

from .weekly import weekly_report

SYMBOLS = ("BTC-USDT", "ETH-USDT")
PROVIDER_SYMBOLS = {"BTC-USDT": "BTCUSDT", "ETH-USDT": "ETHUSDT"}
CANDIDATE = "trend_100_momentum_90_weekly_btc_gate"
PER_ASSET_CAP = 0.20
MAX_DEPLOYMENT = 0.40
VOLATILITY_TARGET = 0.30

SCHEMA = """
CREATE TABLE IF NOT EXISTS defensive_forward(
    id INTEGER PRIMARY KEY CHECK(id=1), created TEXT NOT NULL,
    active INTEGER NOT NULL, config TEXT NOT NULL, result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS defensive_forward_observations(
    day TEXT PRIMARY KEY, received TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS defensive_forward_fills(
    id TEXT PRIMARY KEY, day TEXT NOT NULL, body TEXT NOT NULL
);
"""


class ForwardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capital: float = Field(500.0, gt=0, le=100_000)
    fee_bps: float = Field(10.0, ge=0, le=100)
    friction_bps: float = Field(5.0, ge=0, le=100)


def initialize(db) -> None:
    with db.connect() as connection:
        connection.executescript(SCHEMA)


def configure(db, config: dict | None = None) -> dict:
    initialize(db)
    validated = ForwardConfig.model_validate(config or {})
    with FileLock(db.path + ".defensive-forward.lock"):
        if db.rows("SELECT 1 FROM defensive_forward_observations LIMIT 1"):
            raise ValueError("Forward configuration frozen after first observation")
        with db.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO defensive_forward VALUES(1,?,0,?,NULL,NULL)",
                (now(), dumps(validated.model_dump())),
            )
    db.event(
        "defensive_forward",
        "configured",
        {
            "candidate": CANDIDATE,
            "risk": {
                "per_asset": PER_ASSET_CAP,
                "deployment": MAX_DEPLOYMENT,
                "volatility_target": VOLATILITY_TARGET,
            },
        },
    )
    return status(db)


def _next_observation(at: pd.Timestamp | None = None) -> str:
    current = pd.Timestamp(at or datetime.now(UTC))
    next_day = current.normalize() + pd.Timedelta(days=1, minutes=5)
    return next_day.isoformat()


def status(db) -> dict:
    initialize(db)
    rows = db.rows("SELECT * FROM defensive_forward")
    if not rows:
        return {
            "configured": False,
            "active": False,
            "mode": "prospective forward paper",
            "candidate": CANDIDATE,
        }
    row = rows[0]
    config = json.loads(row["config"])
    result = json.loads(row["result"]) if row["result"] else None
    observations = db.rows(
        "SELECT COUNT(*) AS count FROM defensive_forward_observations"
    )[0]["count"]
    decision_weeks = db.rows(
        "SELECT body FROM defensive_forward_observations ORDER BY day"
    )
    decision_weeks = sum(
        json.loads(item["body"]).get("weights") is not None
        for item in decision_weeks
    )
    qualification = None
    if result:
        qualification = weekly_report(
            result["points"],
            config["capital"],
            result["completed_trades"],
            result.get("doubled_cost_return", 0) > 0,
            forward=True,
        )
        qualification["decision_weeks"] = decision_weeks
        qualification["prospective_gate_complete"] = bool(
            qualification["qualified"] and decision_weeks >= 12
        )
        qualification["broker_promotion_allowed"] = False
    return {
        "configured": True,
        "active": bool(row["active"]),
        "mode": "prospective forward paper",
        "candidate": CANDIDATE,
        "risk": {
            "per_asset": PER_ASSET_CAP,
            "deployment": MAX_DEPLOYMENT,
            "minimum_cash": 1 - MAX_DEPLOYMENT,
            "volatility_target": VOLATILITY_TARGET,
            "drawdown_budget": 0.20,
        },
        "config": config,
        "result": result,
        "error": row["error"],
        "observations": observations,
        "decision_weeks": decision_weeks,
        "qualification": qualification,
        "next_observation": _next_observation(),
        "live_orders_possible": False,
    }


def control(db, action: str) -> dict:
    initialize(db)
    if action not in ("start", "stop"):
        raise ValueError("Unknown defensive-forward action")
    if not db.rows("SELECT 1 FROM defensive_forward"):
        raise ValueError("Configure defensive forward paper first")
    if action == "start" and db.state("kill", False):
        raise ValueError("Global kill active")
    with FileLock(db.path + ".defensive-forward.lock"), db.connect() as connection:
        connection.execute(
            "UPDATE defensive_forward SET active=?,error=NULL WHERE id=1",
            (int(action == "start"),),
        )
    db.set_state("defensive_forward_enabled", True)
    db.event("defensive_forward", action, {"candidate": CANDIDATE})
    return status(db)


def _validated_closes(
    symbol: str, rows: list, received: pd.Timestamp
) -> pd.Series:
    completed = [row for row in rows if int(row[6]) < received.timestamp() * 1000]
    if len(completed) < 120:
        raise ValueError(f"Insufficient completed history for {symbol}")
    index = pd.to_datetime([int(row[0]) for row in completed], unit="ms", utc=True)
    closes = pd.Series([float(row[4]) for row in completed], index=index)
    closes = closes[~closes.index.duplicated()].sort_index()
    if (
        not closes.index.is_monotonic_increasing
        or (closes.index.to_series().diff().dropna() != pd.Timedelta(days=1)).any()
        or received - (closes.index[-1] + pd.Timedelta(days=1))
        > pd.Timedelta(hours=36)
        or (closes <= 0).any()
    ):
        raise ValueError(f"Invalid or stale completed history for {symbol}")
    return closes


def observe(at=None) -> tuple[pd.Timestamp, dict, dict[str, pd.Series]]:
    received = pd.Timestamp(at or datetime.now(UTC))
    if received.tzinfo is None:
        raise ValueError("Observation must be UTC-aware")
    quotes = {}
    histories = {}
    for symbol, provider_symbol in PROVIDER_SYMBOLS.items():
        history_response = requests.get(
            "https://data-api.binance.vision/api/v3/klines",
            params={"symbol": provider_symbol, "interval": "1d", "limit": 220},
            timeout=15,
        )
        history_response.raise_for_status()
        histories[symbol] = _validated_closes(
            symbol, history_response.json(), received
        )
        quote_response = requests.get(
            "https://data-api.binance.vision/api/v3/ticker/bookTicker",
            params={"symbol": provider_symbol},
            timeout=15,
        )
        quote_response.raise_for_status()
        quote = quote_response.json()
        bid = float(quote["bidPrice"])
        ask = float(quote["askPrice"])
        if not 0 < bid <= ask or ask / bid - 1 > 0.005:
            raise ValueError(f"Invalid or excessive-spread quote for {symbol}")
        quotes[symbol] = {"bid": bid, "ask": ask}
    return received, quotes, histories


def decision_from_closes(histories: dict[str, pd.Series]) -> tuple[dict, dict]:
    features = {}
    for symbol in SYMBOLS:
        closes = histories[symbol].dropna().sort_index()
        if len(closes) < 120:
            raise ValueError("Insufficient completed history")
        prior = float(closes.iloc[-1])
        trend = prior / float(closes.iloc[-100:].mean()) - 1
        momentum = prior / float(closes.iloc[-91]) - 1
        volatility = float(closes.pct_change().iloc[-30:].std() * np.sqrt(365))
        if not np.isfinite([trend, momentum, volatility]).all() or volatility <= 0:
            raise ValueError("Invalid defensive feature")
        features[symbol] = {
            "completed_close": prior,
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
        }
    active = (
        features["BTC-USDT"]["trend"] > 0
        and features["BTC-USDT"]["momentum"] > 0
    )
    weights = {}
    for symbol in SYMBOLS:
        volatility = features[symbol]["volatility"]
        weights[symbol] = (
            min(
                PER_ASSET_CAP,
                PER_ASSET_CAP * VOLATILITY_TARGET / volatility,
            )
            if active
            else 0.0
        )
    total = sum(weights.values())
    if total > MAX_DEPLOYMENT:
        weights = {
            symbol: weight * MAX_DEPLOYMENT / total
            for symbol, weight in weights.items()
        }
    return weights, features


def _replay(records: list[dict], config: dict, *, stress: bool = False) -> dict:
    capital = float(config["capital"])
    fee_rate = float(config["fee_bps"]) * (2 if stress else 1) / 10_000
    friction_rate = float(config["friction_bps"]) * (2 if stress else 1) / 10_000
    cash = capital
    quantities = {symbol: 0.0 for symbol in SYMBOLS}
    fills = []
    points = []
    total_costs = 0.0
    for record in records:
        quotes = record["body"]["quotes"]
        mids = {
            symbol: (quotes[symbol]["bid"] + quotes[symbol]["ask"]) / 2
            for symbol in SYMBOLS
        }
        equity = cash + sum(
            quantities[symbol] * mids[symbol] for symbol in SYMBOLS
        )
        weights = record["body"].get("weights")
        if weights is not None:
            targets = {symbol: equity * weights[symbol] for symbol in SYMBOLS}
            for symbol in SYMBOLS:
                current = quantities[symbol] * mids[symbol]
                if current > targets[symbol] + 0.01:
                    quantity = (current - targets[symbol]) / mids[symbol]
                    price = quotes[symbol]["bid"] * (1 - friction_rate)
                    notional = quantity * price
                    fee = notional * fee_rate
                    quantities[symbol] -= quantity
                    cash += notional - fee
                    total_costs += fee + quantity * (mids[symbol] - price)
                    fills.append(
                        {
                            "day": record["day"],
                            "symbol": symbol,
                            "side": "SELL",
                            "quantity": quantity,
                            "price": price,
                            "notional": notional,
                            "fee": fee,
                            "reason": "weekly target rebalance",
                        }
                    )
            for symbol in SYMBOLS:
                current = quantities[symbol] * mids[symbol]
                if targets[symbol] > current + 0.01:
                    price = quotes[symbol]["ask"] * (1 + friction_rate)
                    desired = (targets[symbol] - current) / mids[symbol]
                    quantity = min(desired, cash / (price * (1 + fee_rate)))
                    notional = quantity * price
                    fee = notional * fee_rate
                    quantities[symbol] += quantity
                    cash -= notional + fee
                    total_costs += fee + quantity * (price - mids[symbol])
                    fills.append(
                        {
                            "day": record["day"],
                            "symbol": symbol,
                            "side": "BUY",
                            "quantity": quantity,
                            "price": price,
                            "notional": notional,
                            "fee": fee,
                            "reason": "weekly target rebalance",
                        }
                    )
        equity = cash + sum(
            quantities[symbol] * mids[symbol] for symbol in SYMBOLS
        )
        points.append(
            {
                "timestamp": record["received"],
                "equity": equity,
                "cash": cash,
            }
        )
    values = np.asarray([capital, *[point["equity"] for point in points]])
    ending = float(values[-1])
    return {
        "initial": capital,
        "ending_equity": ending,
        "net_return": ending / capital - 1,
        "max_drawdown": float(
            np.min(values / np.maximum.accumulate(values) - 1)
        ),
        "cash": cash,
        "positions": quantities,
        "fills": fills,
        "completed_trades": sum(fill["side"] == "SELL" for fill in fills),
        "transaction_costs": total_costs,
        "points": points,
    }


def _stored_records(db, extra: dict | None = None) -> list[dict]:
    records = [
        {
            "day": row["day"],
            "received": row["received"],
            "body": json.loads(row["body"]),
        }
        for row in db.rows(
            "SELECT day,received,body FROM defensive_forward_observations ORDER BY day"
        )
    ]
    if extra:
        records.append(extra)
    return records


def tick(db, observation=None) -> dict:
    initialize(db)
    with FileLock(db.path + ".defensive-forward.lock", timeout=1):
        state = status(db)
        if not state.get("active"):
            return state
        if db.state("kill", False):
            with db.connect() as connection:
                connection.execute(
                    "UPDATE defensive_forward SET active=0,error='Global kill' WHERE id=1"
                )
            return status(db)
        try:
            if observation is None:
                current = pd.Timestamp.now(tz="UTC")
                day = current.date().isoformat()
                if db.rows(
                    "SELECT 1 FROM defensive_forward_observations WHERE day=?", (day,)
                ):
                    return status(db)
                at, quotes, histories = observe(current)
            else:
                at, quotes, histories = observation
                at = pd.Timestamp(at)
                if at.tzinfo is None:
                    raise ValueError("Observation must be UTC-aware")
                day = at.date().isoformat()
            if db.rows(
                "SELECT 1 FROM defensive_forward_observations WHERE day=?", (day,)
            ):
                return status(db)
            later = db.rows(
                "SELECT 1 FROM defensive_forward_observations WHERE day>?", (day,)
            )
            if later:
                raise ValueError("Out-of-order defensive observation")
            iso = at.isocalendar()
            week = f"{iso.year}-W{iso.week:02d}"
            prior_weeks = {
                json.loads(row["body"]).get("decision_week")
                for row in db.rows(
                    "SELECT body FROM defensive_forward_observations ORDER BY day"
                )
            }
            weights = None
            features = None
            if week not in prior_weeks:
                weights, features = decision_from_closes(histories)
            body = {
                "provider": "Binance public spot",
                "quotes": quotes,
                "weights": weights,
                "features": features,
                "decision_week": week if weights is not None else None,
                "candidate": CANDIDATE,
            }
            extra = {"day": day, "received": at.isoformat(), "body": body}
            records = _stored_records(db, extra)
            result = _replay(records, state["config"])
            stress = _replay(records, state["config"], stress=True)
            result["doubled_cost_return"] = stress["net_return"]
            with db.connect() as connection:
                connection.execute(
                    "INSERT INTO defensive_forward_observations VALUES(?,?,?)",
                    (day, at.isoformat(), dumps(body)),
                )
                for fill in result["fills"]:
                    identifier = hashlib.sha256(
                        dumps(
                            [
                                fill["day"],
                                fill["symbol"],
                                fill["side"],
                                fill["quantity"],
                                fill["price"],
                            ]
                        ).encode()
                    ).hexdigest()
                    connection.execute(
                        "INSERT OR IGNORE INTO defensive_forward_fills VALUES(?,?,?)",
                        (identifier, fill["day"], dumps(fill)),
                    )
                connection.execute(
                    "UPDATE defensive_forward SET result=?,error=NULL WHERE id=1",
                    (dumps(result),),
                )
        except Exception as exc:  # noqa: BLE001 -- fail closed, no broker routing
            with db.connect() as connection:
                connection.execute(
                    "UPDATE defensive_forward SET active=0,error=? WHERE id=1",
                    (type(exc).__name__,),
                )
            db.event(
                "defensive_forward",
                "blocked",
                {"reason": type(exc).__name__},
            )
    return status(db)
