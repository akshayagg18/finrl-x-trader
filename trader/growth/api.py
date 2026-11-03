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
