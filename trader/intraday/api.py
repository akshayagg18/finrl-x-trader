"""Research API extension. No intraday live routing is exposed."""

import json
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .engine import Experiment, backtest

LOCK = threading.Lock()


class Request(BaseModel):
    settings: Experiment
    start: str
    end: str


class TrainRequest(BaseModel):
    symbol: Literal["BTC-USDT", "ETH-USDT", "AAPL", "SPY", "QQQ"]
    interval: Literal[5, 15] = 15
    cutoff: str
    family: Literal["forest", "boosted"] = "boosted"
    horizon: Literal[8, 16] = 16


def router(db):
    routes = APIRouter(prefix="/api/intraday")

    @routes.get("/settings")
    def settings():
        return db.state("intraday_settings", Experiment().model_dump())

    @routes.put("/settings")
    def save(settings: Experiment):
        db.set_state("intraday_settings", settings.model_dump())
        db.event("intraday_research", "settings", settings.model_dump())
        return settings

    @routes.get("/runs")
    def runs():
        return db.state("intraday_runs", [])

    @routes.post("/backtest")
    def run(request: Request):
        if not LOCK.acquire(blocking=False):
            raise HTTPException(409, "Intraday research already running")
        try:
            result = backtest(request.settings.model_dump(), request.start, request.end)
            # Independent state namespace: never mix intraday research with deployed portfolio.
            history = db.state("intraday_runs", [])
            result["id"] = len(history) + 1
            history.append(result)
            db.set_state("intraday_runs", history)
            db.event(
                "intraday_research",
                "backtest",
                {"id": result["id"], "net_return": result["net_return"]},
            )
            return result
        finally:
            LOCK.release()

    @routes.post("/models/train")
    def train_model(request: TrainRequest):
        from .ml import train

        result = train(**request.model_dump())
        db.event("intraday_research", "model_trained", result)
        return result

    @routes.get("/models")
    def models():
        from .ml import ROOT

        return [
            {"id": p.stem, **json.loads(p.read_text())}
            for p in sorted(ROOT.glob("*.json"))
        ]

    @routes.post("/sessions")
    def session_create(request: Request):
        from .replay import create, inspect

        sid = create(db, request.settings.model_dump(), request.start, request.end)
        db.set_state("intraday_enabled", True)
        return inspect(db, sid)

    @routes.get("/sessions")
    def session_list():
        from .replay import sessions

        return sessions(db)

    @routes.get("/sessions/{sid}")
    def session_status(sid: str):
        from .replay import inspect

        return inspect(db, sid)

    @routes.post("/sessions/{sid}/{action}")
    def session_control(sid: str, action: str):
        from .replay import control, step

        if action == "step":
            return step(db, sid)
        return control(db, sid, action)

    return routes
