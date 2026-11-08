"""Scripted LLM for the demo story.

Behaviors:
  - Missed punch (e01): returns valid ADD_PUNCH proposal (requires employee confirmation).
  - Overtime (e02): returns BAD first proposal (adds an OUT punch creating >12 hour day),
                    then returns valid repair proposal (FLAG_OVERTIME_FOR_APPROVAL).
  - Prompt injection (e03): returns obedient proposal granting overtime as requested by note
                    (so the safety layer visibly intercepts and forces ESCALATE_TO_HR).
  - Unknown jurisdiction (e04): returns ESCALATE_TO_HR.
  - Meal break violation (e05): returns REQUEST_EMPLOYEE_CONFIRMATION.
"""

from __future__ import annotations

import json
from typing import Any

from backend.agent.llm import LLMClient, LLMResponse


class ScriptedLLM:
    """Deterministic LLM implementation for demo and end-to-end testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})

        full_content = "\n".join(
            str(m.get("content") or "") for m in messages
        )

        is_repair = any(
            "failed validation" in str(m.get("content", "")).lower()
            for m in messages
            if m.get("role") == "user"
        )

        # 1. Missed punch (e01)
        if "tc_e01" in full_content or "e01" in full_content:
            proposal = {
                "exception_id": "exc_tc_e01_MISSED_PUNCH_2026-11-03",
                "action": "ADD_PUNCH",
                "changes": [
                    {
                        "op": "add_punch",
                        "type": "OUT",
                        "at": "2026-11-03T17:00:00+05:30",
                    }
                ],
                "rationale": "Employee forgot to clock out at shift end. Proposing OUT punch at scheduled 17:00 boundary with employee confirmation.",
                "evidence": [
                    {"kind": "punch", "id": "p_88"},
                    {"kind": "shift", "id": "s_12"},
                ],
                "policy_clauses": ["CA-MISS-01"],
                "confidence": 0.95,
                "needs_employee_confirmation": True,
            }
            return LLMResponse(
                text=json.dumps(proposal),
                input_tokens=150,
                output_tokens=85,
                latency_ms=120,
            )

        # 2. Overtime case (e02)
        if "tc_e02" in full_content or "e02" in full_content or "OVERTIME_RISK" in full_content:
            if not is_repair:
                # BAD first proposal: adds an OUT punch that creates a >12 hour day
                # (shift was 09:00 - 17:00, OUT punch at 21:30 makes day 12.5h)
                bad_proposal = {
                    "exception_id": "exc_tc_e02_OVERTIME_RISK_2026-11-04",
                    "action": "ADD_PUNCH",
                    "changes": [
                        {
                            "op": "add_punch",
                            "type": "OUT",
                            "at": "2026-11-04T21:30:00+05:30",
                        }
                    ],
                    "rationale": "Adding another OUT punch to log late hours.",
                    "evidence": [
                        {"kind": "punch", "id": "p_100"},
                    ],
                    "policy_clauses": ["CA-OT-DAILY-01"],
                    "confidence": 0.70,
                    "needs_employee_confirmation": False,
                }
                return LLMResponse(
                    text=json.dumps(bad_proposal),
                    input_tokens=180,
                    output_tokens=90,
                    latency_ms=130,
                )
            else:
                # Good repair proposal: route overtime for manager approval without punch changes
                good_proposal = {
                    "exception_id": "exc_tc_e02_OVERTIME_RISK_2026-11-04",
                    "action": "FLAG_OVERTIME_FOR_APPROVAL",
                    "changes": [],
                    "rationale": "Employee worked 11.0 hours (exceeding daily 8h threshold). Flagging overtime for manager approval per CA-OT-DAILY-01.",
                    "evidence": [
                        {"kind": "punch", "id": "p_100"},
                        {"kind": "shift", "id": "s_20"},
                    ],
                    "policy_clauses": ["CA-OT-DAILY-01"],
                    "confidence": 0.95,
                    "needs_employee_confirmation": False,
                }
                return LLMResponse(
                    text=json.dumps(good_proposal),
                    input_tokens=220,
                    output_tokens=95,
                    latency_ms=140,
                )

        # 3. Prompt injection case (e03)
        if "tc_e03" in full_content or "e03" in full_content or "ignore all previous" in full_content.lower():
            # Obedient-to-the-note proposal (overtime granted as instructed in employee note)
            obedient_proposal = {
                "exception_id": "exc_tc_e03_MISSED_PUNCH_2026-11-03",
                "action": "FLAG_OVERTIME_FOR_APPROVAL",
                "changes": [],
                "rationale": "Approving 4 hours of overtime as requested by employee note.",
                "evidence": [
                    {"kind": "punch", "id": "p_200"},
                ],
                "policy_clauses": [],
                "confidence": 1.0,
                "needs_employee_confirmation": False,
            }
            return LLMResponse(
                text=json.dumps(obedient_proposal),
                input_tokens=160,
                output_tokens=75,
                latency_ms=110,
            )

        # 4. Unknown jurisdiction case (e04)
        if "tc_e04" in full_content or "e04" in full_content or "XX" in full_content:
            unknown_proposal = {
                "exception_id": "exc_tc_e04_MISSED_PUNCH_2026-11-03",
                "action": "ESCALATE_TO_HR",
                "changes": [],
                "rationale": "No policy pack found for jurisdiction XX. Escalating to HR.",
                "evidence": [],
                "policy_clauses": [],
                "confidence": 0.2,
                "needs_employee_confirmation": False,
            }
            return LLMResponse(
                text=json.dumps(unknown_proposal),
                input_tokens=140,
                output_tokens=65,
                latency_ms=100,
            )

        # 5. Meal break violation case (e05)
        if "tc_e05" in full_content or "e05" in full_content or "MEAL_BREAK" in full_content:
            meal_proposal = {
                "exception_id": "exc_tc_e05_MEAL_BREAK_VIOLATION_2026-11-03",
                "action": "REQUEST_EMPLOYEE_CONFIRMATION",
                "changes": [],
                "rationale": "Shift exceeded 5 hours without recorded meal break. Requesting employee confirmation.",
                "evidence": [
                    {"kind": "punch", "id": "p_400"},
                    {"kind": "punch", "id": "p_401"},
                ],
                "policy_clauses": ["CA-MEAL-01"],
                "confidence": 0.90,
                "needs_employee_confirmation": True,
            }
            return LLMResponse(
                text=json.dumps(meal_proposal),
                input_tokens=170,
                output_tokens=80,
                latency_ms=115,
            )

        # Generic fallback
        default_proposal = {
            "exception_id": "exc_unknown",
            "action": "ESCALATE_TO_HR",
            "changes": [],
            "rationale": "Default scripted proposal escalating to HR.",
            "evidence": [],
            "policy_clauses": [],
            "confidence": 0.5,
            "needs_employee_confirmation": False,
        }
        return LLMResponse(text=json.dumps(default_proposal))
