"""Research API extension. No intraday live routing is exposed."""

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .engine import Experiment, backtest

LOCK = threading.Lock()


class Request(BaseModel):
    settings: Experiment
    start: str
    end: str


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

    return routes
