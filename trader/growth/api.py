import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .config import GrowthConfig


class ForwardRequest(BaseModel):
    config: GrowthConfig = Field(default_factory=GrowthConfig)
    models: dict[str, str] = Field(default_factory=dict)


class DefensiveForwardRequest(BaseModel):
    capital: float = Field(500.0, gt=0, le=100000)
    fee_bps: float = Field(10.0, ge=0, le=100)
    friction_bps: float = Field(5.0, ge=0, le=100)


from . import defensive_forward, forward


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

    @routes.get("/hedges")
    def hedges():
        tracks = ("short_hedge", "relative_value", "put_protection")
        return {
            "comparison": json.loads(
                Path("research/hedge_comparison/summary.json").read_text()
            )
            if Path("research/hedge_comparison/summary.json").exists()
            else None,
            "tracks": {
                name: json.loads(
                    (Path("research") / name / "summary.json").read_text()
                )
                if (Path("research") / name / "summary.json").exists()
                else None
                for name in tracks
            },
        }

    @routes.get("/etf-challenger")
    def etf_challenger():
        """Read-only locked challenger evidence; never executes the strategy."""
        root = Path("research/etf_rotation_challenger")
        return {
            key: json.loads((root / f"{key}.json").read_text())
            if (root / f"{key}.json").exists()
            else None
            for key in ("protocol", "selection_locked", "summary")
        }

    @routes.get("/forward")
    def status():
        return forward.status(db)

    @routes.get("/defensive-forward")
    def defensive_forward_status():
        return defensive_forward.status(db)

    @routes.post("/defensive-forward/configure")
    def defensive_forward_configure(request: DefensiveForwardRequest):
        return defensive_forward.configure(db, request.model_dump())

    @routes.post("/defensive-forward/{action}")
    def defensive_forward_control(action: str):
        return defensive_forward.control(db, action)

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
