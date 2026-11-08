"""Deterministic fallback when the LLM fails twice.

Always safe: no data-changing actions, just routing or confirmation requests.
"""

from __future__ import annotations

from backend.core.models import (
    ExceptionRecord,
    ExceptionType,
    Proposal,
    ProposalAction,
)


_FALLBACK_MAP: dict[ExceptionType, ProposalAction] = {
    ExceptionType.MISSED_PUNCH: ProposalAction.REQUEST_EMPLOYEE_CONFIRMATION,
    ExceptionType.MEAL_BREAK_VIOLATION: ProposalAction.REQUEST_EMPLOYEE_CONFIRMATION,
    ExceptionType.OVERTIME_RISK: ProposalAction.FLAG_OVERTIME_FOR_APPROVAL,
}


def fallback_proposal(exception: ExceptionRecord) -> Proposal:
    """Return the safe deterministic proposal for a given exception type."""
    action = _FALLBACK_MAP.get(exception.type, ProposalAction.ESCALATE_TO_HR)
    return Proposal(
        exception_id=exception.id,
        action=action,
        rationale=(
            f"Automatic fallback: LLM proposals failed validation twice. "
            f"Routing {exception.type.value} via {action.value}."
        ),
        confidence=0.0,
        needs_employee_confirmation=action == ProposalAction.REQUEST_EMPLOYEE_CONFIRMATION,
    )
