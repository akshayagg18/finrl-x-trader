from __future__ import annotations

from .schemas import SentimentFeature, TradeProposal, VetoAssessment


def apply_trade_veto(baseline_action: str, assessment: VetoAssessment) -> str:
    """A veto can only remove an entry; it cannot create or enlarge one."""
    if baseline_action not in {"buy", "sell", "hold"}:
        raise ValueError("Invalid baseline action")
    if baseline_action == "buy" and assessment.decision == "reject":
        return "hold"
    return baseline_action


def validate_research_proposal(
    proposal: TradeProposal,
    *,
    eligible_assets: set[str],
    max_allocation: float,
    owned_assets: set[str] | None = None,
):
    if proposal.asset not in eligible_assets:
        raise ValueError("Asset ineligible")
    if proposal.allocation > max_allocation:
        raise ValueError("Allocation exceeds existing risk limit")
    if proposal.action == "sell" and proposal.asset not in (owned_assets or set()):
        raise ValueError("Uncovered selling prohibited")
    return {
        "asset": proposal.asset,
        "action": proposal.action,
        "allocation": proposal.allocation,
        "research_only": True,
        "order_submitted": False,
    }


def paired_veto_statistics(opportunities: list[dict]) -> dict:
    vetoed = [x for x in opportunities if x.get("veto") == "reject"]
    false_veto = [x for x in vetoed if float(x.get("baseline_pnl", 0)) > 0]
    avoided = -sum(min(0.0, float(x.get("baseline_pnl", 0))) for x in vetoed)
    missed = sum(max(0.0, float(x.get("baseline_pnl", 0))) for x in vetoed)
    return {
        "opportunities": len(opportunities),
        "vetoes": len(vetoed),
        "veto_rate": len(vetoed) / len(opportunities) if opportunities else None,
        "false_veto_rate": len(false_veto) / len(vetoed) if vetoed else None,
        "avoided_loss_usd": avoided,
        "missed_profit_usd": missed,
        "net_veto_value_usd": avoided - missed,
    }


def feature_vector(feature: SentimentFeature) -> dict[str, float]:
    return {
        "news_sentiment": feature.sentiment,
        "news_relevance": feature.relevance,
        "news_novelty": feature.novelty,
        "news_severity": feature.severity,
        "news_directional_uncertainty": feature.directional_uncertainty,
    }
