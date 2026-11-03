from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .config import LLMSettings
from .news import NewsStore
from .schemas import NewsEvent, SentimentFeature, TradeProposal, VetoAssessment
from .service import LLMService, fallback_to_baseline
from .sentiment import LexiconFinancialSentiment
from .shadow import ShadowRecorder
from .strategies import apply_trade_veto, feature_vector, validate_research_proposal


def router(db):
    routes = APIRouter(prefix="/api/llm")
    service = LLMService(db)
    news = NewsStore(db)
    shadow = ShadowRecorder(db)

    @routes.get("/status")
    def status():
        return service.status()

    @routes.get("/config")
    def config():
        return service.config().model_dump()

    @routes.put("/config")
    def save_config(value: LLMSettings):
        return service.save_config(value).model_dump()

    @routes.get("/recent")
    def recent():
        return db.rows(
            "SELECT id,created,cycle_id,provider,model,prompt_version,input_refs,output,input_tokens,output_tokens,cost_usd,latency_ms,status,cached,request_id FROM llm_requests ORDER BY id DESC LIMIT 100"
        )

    @routes.post("/news")
    def ingest_news(event: NewsEvent):
        return {"source_id": event.source_id, "content_hash": news.ingest(event)}

    @routes.get("/news")
    def list_news(decision_time: datetime | None = None, asset: str | None = None):
        at = decision_time or datetime.now(timezone.utc)
        return news.as_of(at, [asset] if asset else None)

    @routes.post("/veto")
    def veto(body: dict):
        if body.get("mode", "simulation") != "simulation":
            raise HTTPException(400, "LLM analysis is research-only and cannot run in paper/live mode")
        baseline_action = body.get("baseline_action", "hold")
        if baseline_action not in {"buy", "sell", "hold"}:
            raise HTTPException(422, "Invalid baseline action")
        assessment, fallback_error = fallback_to_baseline(
            baseline_action,
            lambda: service.analyze(
                VetoAssessment,
                body.get("context", {}),
                input_refs=list(body.get("input_refs", [])),
                cycle_id=str(body.get("cycle_id", "manual-research")),
            ),
        )
        effective = (
            baseline_action
            if fallback_error
            else apply_trade_veto(baseline_action, assessment)
        )
        return {
            "assessment": None if fallback_error else assessment.model_dump(mode="json"),
            "baseline_action": baseline_action,
            "effective_action": effective,
            "fallback_used": bool(fallback_error),
            "fallback_reason": fallback_error,
            "research_only": True,
            "order_submitted": False,
        }

    @routes.post("/analyze/{variant}")
    def analyze_variant(variant: str, body: dict):
        if body.get("mode", "simulation") != "simulation":
            raise HTTPException(400, "LLM analysis is research-only and cannot run in paper/live mode")
        common = dict(
            input_refs=list(body.get("input_refs", [])),
            cycle_id=str(body.get("cycle_id", "manual-research")),
        )
        if variant == "baseline":
            return {"variant": variant, "action": body.get("baseline_action", "hold"), "llm_requests": 0}
        if variant == "features":
            value = service.analyze(SentimentFeature, body.get("context", {}), **common)
            return {"variant": variant, "features": feature_vector(value), "assessment": value.model_dump(mode="json")}
        if variant == "agent":
            value = service.analyze(TradeProposal, body.get("context", {}), **common)
            proposal = validate_research_proposal(
                value,
                eligible_assets=set(body.get("eligible_assets", [])),
                max_allocation=float(body.get("max_allocation", 0.60)),
                owned_assets=set(body.get("owned_assets", [])),
            )
            return {"variant": variant, "proposal": proposal, "assessment": value.model_dump(mode="json")}
        raise HTTPException(404, "Unknown LLM research variant")

    @routes.post("/sentiment/non-llm")
    def non_llm_sentiment(body: dict):
        return LexiconFinancialSentiment().score(str(body.get("text", "")))

    @routes.get("/shadow")
    def shadow_rows():
        return shadow.rows()

    @routes.post("/shadow")
    def record_shadow(body: dict):
        return {
            "id": shadow.record(
                decision_time=datetime.fromisoformat(body["decision_time"]),
                variant=body["variant"], asset=body["asset"],
                baseline_action=body["baseline_action"], llm_output=body.get("llm_output"),
                effective_action=body["effective_action"],
            ),
            "order_submitted": False,
        }

    @routes.get("/experiments")
    def experiments():
        path = Path("research/llm/experiments.json")
        return json.loads(path.read_text()) if path.exists() else {"status": "not_run"}

    return routes
