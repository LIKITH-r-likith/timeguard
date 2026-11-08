"""Offline simulation runner: python -m backend.agent.simulate

Runs each case from evals/golden/example_cases.jsonl and golden_cases.jsonl,
resolving all detected exceptions offline and printing:
  - case_id
  - exception_id and type
  - proposed action
  - attempts
  - validation result
  - fallback usage
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.agent.api import resolve
from backend.agent.context import InMemoryContextProvider
from backend.agent.llm import LLMResponse, MockLLM
from backend.core.models import ProposalAction


def _build_offline_mock(case: dict, exc_id: str, ctx: InMemoryContextProvider) -> MockLLM:
    """Create a deterministic MockLLM response suited for offline simulation of the case."""
    expected = case.get("expected", {})
    allowed = expected.get("allowed_actions", [])
    must_escalate = expected.get("must_escalate", False)

    if must_escalate:
        action = "ESCALATE_TO_HR"
    elif allowed:
        action = allowed[0]
    else:
        action = "ESCALATE_TO_HR"

    changes: list = []
    evidence: list = []
    clauses: list = []

    if action == "ADD_PUNCH":
        shift = ctx.timecard.shifts[0] if ctx.timecard.shifts else None
        at = shift.end.isoformat() if shift else "2026-11-03T17:00:00+05:30"
        changes = [{"op": "add_punch", "type": "OUT", "at": at}]
        if ctx.timecard.punches:
            evidence.append({"kind": "punch", "id": ctx.timecard.punches[0].id})
        if shift:
            evidence.append({"kind": "shift", "id": shift.id})
        if ctx.policy:
            for c in ctx.policy.clauses:
                if "MISS" in c.id:
                    clauses.append(c.id)
                    break

    elif action == "FLAG_OVERTIME_FOR_APPROVAL":
        if ctx.timecard.punches:
            evidence.append({"kind": "punch", "id": ctx.timecard.punches[0].id})
        if ctx.policy:
            for c in ctx.policy.clauses:
                if "OT" in c.id:
                    clauses.append(c.id)
                    break

    proposal_dict = {
        "exception_id": exc_id,
        "action": action,
        "changes": changes,
        "rationale": f"Offline simulation resolution proposing {action}.",
        "evidence": evidence,
        "policy_clauses": clauses,
        "confidence": 0.9 if not must_escalate else 0.2,
        "needs_employee_confirmation": action == "REQUEST_EMPLOYEE_CONFIRMATION",
    }
    return MockLLM([LLMResponse(text=json.dumps(proposal_dict))])


def run_simulation() -> None:
    root = Path(__file__).resolve().parents[2]
    golden_files = [
        root / "evals" / "golden" / "example_cases.jsonl",
        root / "evals" / "golden" / "golden_cases.jsonl",
    ]

    total_cases = 0
    total_exceptions = 0
    passed_validations = 0

    print("=" * 78)
    print("TimeGuard Offline Agent Simulation")
    print("=" * 78)

    for gfile in golden_files:
        if not gfile.exists():
            continue
        print(f"\n--- Loading {gfile.name} ---")
        lines = [l.strip() for l in gfile.read_text("utf-8").splitlines() if l.strip()]

        for line in lines:
            case = json.loads(line)
            case_id = case.get("case_id", "unknown")
            desc = case.get("description", "")
            total_cases += 1

            ctx = InMemoryContextProvider(case)
            if not ctx.exceptions:
                print(f"[{case_id:6s}] CLEAN: 0 exceptions | {desc[:45]}")
                continue

            for exc in ctx.exceptions:
                total_exceptions += 1
                mock_llm = _build_offline_mock(case, exc.id, ctx)
                result = resolve(exc.id, ctx, llm=mock_llm)

                val_status = "PASS" if result.validation.passed else "FAIL"
                if result.validation.passed:
                    passed_validations += 1

                fb_status = " (fallback)" if result.used_fallback else ""
                print(
                    f"[{case_id:6s}] {exc.type.value:23s} -> "
                    f"Action: {result.proposal.action.value:28s} | "
                    f"Attempts: {result.attempts} | Val: {val_status}{fb_status}"
                )

    print("\n" + "=" * 78)
    print(
        f"Simulation Summary: {total_cases} cases | "
        f"{total_exceptions} exceptions | "
        f"{passed_validations}/{total_exceptions} validated successfully"
    )
    print("=" * 78)


if __name__ == "__main__":
    run_simulation()
