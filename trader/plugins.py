"""Optional research extensions cannot issue orders or bypass target risk validation."""

from typing import Protocol
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResearchSignal:
    symbol: str
    observed_at: datetime
    available_at: datetime
    source: str
    score: float
    evidence: str
    version: str


class ResearchPlugin(Protocol):
    name: str

    def signals(self, asof: datetime) -> list[ResearchSignal]: ...


# No extension registered in deployed strategy. Promotion requires a separate
# audited evaluation and a coded StrategyEngine adapter; paid APIs are optional.
