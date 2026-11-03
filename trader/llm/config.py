from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMSettings(BaseModel):
    """Persisted non-secret research configuration."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    research_budget_authorized: bool = False
    provider: Literal["openai", "anthropic", "openai_compatible", "ollama"] = "ollama"
    model: str = ""
    endpoint: str = "http://127.0.0.1:11434/v1/chat/completions"
    api_key_env: str = ""
    temperature: float = Field(0.0, ge=0, le=1)
    timeout_seconds: float = Field(20, ge=1, le=120)
    retries: int = Field(1, ge=0, le=3)
    max_tokens: int = Field(400, ge=32, le=4096)
    max_requests_per_cycle: int = Field(2, ge=1, le=10)
    daily_spending_cap_usd: float = Field(0.25, ge=0, le=25)
    monthly_spending_cap_usd: float = Field(5.0, ge=0, le=100)
    input_cost_per_million_usd: float = Field(0.0, ge=0, le=1000)
    output_cost_per_million_usd: float = Field(0.0, ge=0, le=5000)
    inference_frequency_minutes: int = Field(60, ge=1, le=1440)
    prompt_template_version: str = "llm-research-v1"

    @model_validator(mode="after")
    def validate_provider(self):
        if self.model and len(self.model) > 120:
            raise ValueError("Model identifier too long")
        if self.endpoint and not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("Endpoint must use http or https")
        if self.api_key_env and not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", self.api_key_env):
            raise ValueError("API key environment variable name is invalid")
        if self.provider == "openai" and not self.endpoint:
            self.endpoint = "https://api.openai.com/v1/responses"
        if self.provider == "anthropic" and not self.endpoint:
            self.endpoint = "https://api.anthropic.com/v1/messages"
        if self.provider == "ollama" and not self.endpoint:
            self.endpoint = "http://127.0.0.1:11434/v1/chat/completions"
        return self

    @property
    def paid_remote(self) -> bool:
        return self.provider in {"openai", "anthropic", "openai_compatible"} and not any(
            host in self.endpoint.lower() for host in ("127.0.0.1", "localhost", "[::1]")
        )

    @property
    def key_environment_name(self) -> str:
        if self.api_key_env:
            return self.api_key_env
        return {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(
            self.provider, "LLM_API_KEY"
        )
