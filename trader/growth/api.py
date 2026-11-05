import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .config import GrowthConfig


class ForwardRequest(BaseModel):
    config: GrowthConfig = Field(default_factory=GrowthConfig)
    models: dict[str, str] = Field(default_factory=dict)


from . import forward


def router(db):
    routes = APIRouter(prefix="/api/growth")

    @routes.get("/research")
    def research():
        root = Path("research/growth")
        return {
            k: json.loads((root / (k + ".json")).read_text())
            if (root / (k + ".json")).exists()
            else None
            for k in ("protocol", "summary", "versions", "trials")
        }

    @routes.get("/profitability")
    def profitability():
        """Read-only results; this endpoint never trains or submits orders."""
        root = Path("research/profitability")
        return {
            name: json.loads((root / f"{name}.json").read_text())
            if (root / f"{name}.json").exists()
            else None
            for name in ("protocol", "selection_locked", "screening", "summary")
        }

    @routes.get("/regime")
    def regime():
        root = Path("research/strategy_v2")
        return {
            key: json.loads((root / f"{key}.json").read_text())
            if (root / f"{key}.json").exists()
            else None
            for key in ("protocol", "selection_locked", "summary")
        }

    @routes.get("/defensive")
    def defensive():
        """Return reproducible low-exposure research artifacts only."""
        root = Path("research/defensive_trend")
        return {
            key: json.loads((root / f"{key}.json").read_text())
            if (root / f"{key}.json").exists()
            else None
            for key in ("protocol", "selection_locked", "summary")
        }

    @routes.get("/drawdown-frontier")
    def drawdown_frontier():
        root = Path("research/drawdown_frontier")
        return {
            key: json.loads((root / f"{key}.json").read_text())
            if (root / f"{key}.json").exists()
            else None
            for key in ("protocol", "selection_locked", "summary")
        }

    @routes.get("/forward")
    def status():
        return forward.status(db)

    @routes.post("/forward/configure")
    def configure(request: ForwardRequest):
        return forward.configure(db, request.config.model_dump(), request.models)

    @routes.post("/forward/models")
    def models(models: dict[str, str]):
        return forward.promote(db, models)

    @routes.post("/forward/{action}")
    def control(action: str):
        return forward.control(db, action)

    return routes
