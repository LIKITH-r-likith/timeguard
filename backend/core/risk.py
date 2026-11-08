"""risk_tier(): decides who must approve a proposal. All thresholds are MOCK values."""

from __future__ import annotations

from backend.core.models import (
    ExceptionRecord,
    ExceptionType,
    PayImpact,
    Proposal,
    ProposalAction,
    RiskTier,
)

MEDIUM_COST_INR = 5000.0
HIGH_COST_INR = 20000.0
LOW_CONFIDENCE = 0.5  # below this -> HR
MEDIUM_CONFIDENCE = 0.7  # below this -> manager

HIGH_TYPES = {ExceptionType.SCHEDULE_LEAVE_CONFLICT, ExceptionType.REST_PERIOD_BREACH}
MEDIUM_TYPES = {ExceptionType.OVERTIME_RISK, ExceptionType.MEAL_BREAK_VIOLATION}


def risk_tier(exc: ExceptionRecord, proposal: Proposal, impact: PayImpact) -> RiskTier:
    cost = abs(impact.estimated_cost_delta)
    if (
        proposal.action == ProposalAction.ESCALATE_TO_HR
        or exc.type in HIGH_TYPES
        or cost >= HIGH_COST_INR
        or proposal.confidence < LOW_CONFIDENCE
    ):
        return RiskTier.HIGH
    if (
        proposal.action == ProposalAction.FLAG_OVERTIME_FOR_APPROVAL
        or exc.type in MEDIUM_TYPES
        or cost >= MEDIUM_COST_INR
        or proposal.confidence < MEDIUM_CONFIDENCE
    ):
        return RiskTier.MEDIUM
    return RiskTier.LOW
