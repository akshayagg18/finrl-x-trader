from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .config import LLMSettings


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    output: dict
    input_tokens: int
    output_tokens: int
    model: str
    request_id: str | None
    latency_ms: float


def _schema_payload(schema) -> dict:
    value = schema.model_json_schema()
    value["additionalProperties"] = False
    return value


class HTTPProvider:
    def __init__(self, config: LLMSettings, session=None):
        self.config = config
        self.session = session or requests.Session()

    def generate(self, system: str, prompt: str, schema) -> ProviderResult:
        last = None
        for attempt in range(self.config.retries + 1):
            try:
                return self._once(system, prompt, schema)
            except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
                last = exc
                if attempt < self.config.retries:
                    time.sleep(0.2 * (2**attempt))
        raise LLMProviderError(type(last).__name__) from last

    def _key(self) -> str:
        return os.getenv(self.config.key_environment_name, "")

    def _once(self, system: str, prompt: str, schema) -> ProviderResult:
        started = time.perf_counter()
        if self.config.provider == "openai":
            data, headers = self._openai(system, prompt, schema)
            text = next(
                c["text"]
                for item in data["output"]
                if item.get("type") == "message"
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            )
            usage = data.get("usage") or {}
            request_id = data.get("id")
        elif self.config.provider == "anthropic":
            data, headers = self._anthropic(system, prompt, schema)
            block = next(x for x in data["content"] if x.get("type") == "tool_use")
            text = json.dumps(block["input"])
            usage = data.get("usage") or {}
            request_id = data.get("id")
        else:
            data, headers = self._compatible(system, prompt, schema)
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            request_id = data.get("id")
        output = json.loads(text) if isinstance(text, str) else text
        return ProviderResult(
            output=output,
            input_tokens=int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
            output_tokens=int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
            model=str(data.get("model") or self.config.model),
            request_id=request_id,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _post(self, payload, headers):
        response = self.session.post(
            self.config.endpoint,
            json=payload,
            headers=headers,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _openai(self, system, prompt, schema):
        key = self._key()
        if not key:
            raise LLMProviderError("Missing server-side API key")
        payload = {
            "model": self.config.model,
            "input": [
                {"role": "developer", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__.lower(),
                    "strict": True,
                    "schema": _schema_payload(schema),
                }
            },
        }
        return self._post(payload, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}), {}

    def _anthropic(self, system, prompt, schema):
        key = self._key()
        if not key:
            raise LLMProviderError("Missing server-side API key")
        payload = {
            "model": self.config.model,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "tools": [
                {
                    "name": "submit_research_assessment",
                    "description": "Return the requested research assessment only",
                    "input_schema": _schema_payload(schema),
                }
            ],
            "tool_choice": {"type": "tool", "name": "submit_research_assessment"},
        }
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        return self._post(payload, headers), {}

    def _compatible(self, system, prompt, schema):
        headers = {"Content-Type": "application/json"}
        key = self._key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "strict": True,
                    "schema": _schema_payload(schema),
                },
            },
        }
        return self._post(payload, headers), {}


def create_provider(config: LLMSettings, session=None):
    return HTTPProvider(config, session=session)
