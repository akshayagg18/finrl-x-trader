import hashlib
import json
from pathlib import Path

from trader.db import dumps


def test_frontier_protocol_selection_and_risk_budgets():
    root = Path("research/drawdown_frontier")
    protocol = json.loads((root / "protocol.json").read_text())
    lock = json.loads((root / "selection_locked.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    assert hashlib.sha256(dumps(protocol).encode()).hexdigest() == lock[
        "protocol_sha256"
    ]
    assert summary["tested_configurations"] == 162
    assert summary["preference"]["among_new_tiers"] == "drawdown_20"
    assert summary["preference"]["deployment_recommendation"] == "none"
    for name, budget in (("drawdown_20", 0.20), ("drawdown_50", 0.50)):
        tier = summary["tiers"][name]
        assert tier["drawdown_budget"] == budget
        assert tier["risk"]["max_deployment"] <= 1
        assert tier["periods"]["evaluation"]["net_return"] > 0
        assert tier["periods"]["evaluation_cost_2x"]["net_return"] > 0
        assert tier["periods"]["evaluation"]["max_drawdown"] > -budget
        assert tier["within_budget"]
        assert tier["historically_profitable"]
        assert not tier["deployment_qualified"]


def test_fifty_percent_tier_has_materially_more_risk_than_twenty_percent_tier():
    summary = json.loads(
        Path("research/drawdown_frontier/summary.json").read_text()
    )
    moderate = summary["tiers"]["drawdown_20"]["periods"]["evaluation"]
    aggressive = summary["tiers"]["drawdown_50"]["periods"]["evaluation"]
    assert aggressive["net_return"] > moderate["net_return"]
    assert aggressive["max_drawdown"] < moderate["max_drawdown"] - 0.20
