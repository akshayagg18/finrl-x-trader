from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Evidence(StrictSchema):
    source_id: str = Field(max_length=160)
    available_at: datetime
    claim: str = Field(max_length=500)


class VetoAssessment(StrictSchema):
    decision: Literal["permit", "reject", "abstain"]
    confidence: float = Field(ge=0, le=1)
    reason_category: Literal[
        "none", "stale_data", "event_risk", "liquidity", "volatility", "contradictory_evidence", "insufficient_evidence"
    ]
    rationale: str = Field(max_length=800)
    evidence: list[Evidence] = Field(max_length=8)


class SentimentFeature(StrictSchema):
    sentiment: float = Field(ge=-1, le=1)
    relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    severity: float = Field(ge=0, le=1)
    directional_uncertainty: float = Field(ge=0, le=1)
    event_category: Literal[
        "earnings", "macro", "regulatory", "product", "security", "management", "market", "other"
    ]
    evidence: list[Evidence] = Field(max_length=8)


class TradeProposal(StrictSchema):
    asset: str
    action: Literal["buy", "sell", "hold"]
    allocation: float = Field(ge=0, le=0.60)
    holding_horizon_hours: int = Field(ge=1, le=720)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(max_length=8)
    invalidation_conditions: list[str] = Field(max_length=8)

    @field_validator("asset")
    @classmethod
    def valid_asset(cls, value):
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,19}", value):
            raise ValueError("Invalid asset")
        return value

    @model_validator(mode="after")
    def hold_has_no_allocation(self):
        if self.action == "hold" and self.allocation != 0:
            raise ValueError("Hold proposal must allocate zero")
        return self


class NewsEvent(StrictSchema):
    source_id: str = Field(min_length=1, max_length=160)
    publisher: str = Field(min_length=1, max_length=160)
    source_url: str = Field(min_length=1, max_length=1000)
    published_at: datetime
    updated_at: datetime | None = None
    earliest_available_at: datetime
    retrieved_at: datetime
    assets: list[str] = Field(max_length=20)
    title: str = Field(max_length=500)
    content: str = Field(max_length=12000)

    @model_validator(mode="after")
    def temporal_integrity(self):
        for name in ("published_at", "updated_at", "earliest_available_at", "retrieved_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.earliest_available_at < self.published_at:
            raise ValueError("Availability cannot precede publication")
        if self.retrieved_at < self.earliest_available_at:
            raise ValueError("Retrieval cannot precede availability")
        return self

    def available_for(self, decision_time: datetime) -> bool:
        if decision_time.tzinfo is None:
            decision_time = decision_time.replace(tzinfo=timezone.utc)
        return self.earliest_available_at <= decision_time
