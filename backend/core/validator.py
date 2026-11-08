"""validate(): the teacher. Checks that an AI proposal is really safe and correct.

The proposal is applied to a COPY of the timecard. The real timecard is never changed.
"""

from __future__ import annotations

from typing import Optional

from backend.core.contract import VALIDATION_CHECK_ORDER, ValidationCheck
from backend.core.models import (
    ExceptionRecord,
    ExceptionType,
    PolicyPack,
    Proposal,
    ProposalAction,
    Punch,
    PunchType,
    Timecard,
    ValidationResult,
    CheckResult,
)
from backend.core.pay import pay_impact
from backend.core.policy import get_param
from backend.core.rules import detect

DATA_ACTIONS = {ProposalAction.ADD_PUNCH, ProposalAction.ADJUST_PUNCH, ProposalAction.INSERT_BREAK}
FIXABLE_TYPES = {ExceptionType.MISSED_PUNCH, ExceptionType.MEAL_BREAK_VIOLATION}
EXPECTED_OP = {
    ProposalAction.ADD_PUNCH: "add_punch",
    ProposalAction.ADJUST_PUNCH: "adjust_punch",
    ProposalAction.INSERT_BREAK: "insert_break",
}

Result = tuple[bool, str]


def apply_proposal(timecard: Timecard, proposal: Proposal) -> Timecard:
    """Return a patched COPY of the timecard."""
    card = timecard.model_copy(deep=True)
    n = 0
    for ch in proposal.changes:
        if ch.op == "add_punch":
            n += 1
            card.punches.append(Punch(id=f"new_{n}", employee_id=card.employee_id, type=ch.type, at=ch.at))
        elif ch.op == "adjust_punch":
            for p in card.punches:
                if p.id == ch.punch_id:
                    p.at = ch.at
        elif ch.op == "insert_break":
            n += 1
            card.punches.append(Punch(id=f"new_{n}a", employee_id=card.employee_id,
                                      type=PunchType.BREAK_START, at=ch.break_start))
            card.punches.append(Punch(id=f"new_{n}b", employee_id=card.employee_id,
                                      type=PunchType.BREAK_END, at=ch.break_end))
    return card


def _times(proposal: Proposal) -> list:
    out = []
    for ch in proposal.changes:
        out += [t for t in (ch.at, ch.break_start, ch.break_end) if t is not None]
    return out


def _check_changes(proposal: Proposal, timecard: Timecard) -> Result:
    action = proposal.action
    if action not in DATA_ACTIONS:
        if proposal.changes:
            return False, f"{action.value} must not contain timecard changes."
        return True, "No timecard changes, as expected for this action."
    if not proposal.changes:
        return False, f"{action.value} needs at least one change."
    wanted = EXPECTED_OP[action]
    punch_ids = {p.id for p in timecard.punches}
    for ch in proposal.changes:
        if ch.op != wanted:
            return False, f"{action.value} must use op '{wanted}', found '{ch.op}'."
        if ch.op == "add_punch" and (ch.type is None or ch.at is None):
            return False, "add_punch needs type and at."
        if ch.op == "adjust_punch":
            if ch.punch_id is None or ch.at is None:
                return False, "adjust_punch needs punch_id and at."
            if ch.punch_id not in punch_ids:
                return False, f"Punch {ch.punch_id} does not exist on this timecard."
        if ch.op == "insert_break":
            if ch.break_start is None or ch.break_end is None:
                return False, "insert_break needs break_start and break_end."
            if ch.break_end <= ch.break_start:
                return False, "Break must end after it starts."
    if any(t.tzinfo is None or t.utcoffset() is None for t in _times(proposal)):
        return False, "Every timestamp must include a UTC offset."
    return True, f"{len(proposal.changes)} change(s) match {action.value}."


def _check_target(proposal, target, patched, policy) -> Result:
    action = proposal.action
    if target is None:
        return False, f"Exception {proposal.exception_id} was not found on this timecard."
    if action == ProposalAction.ESCALATE_TO_HR:
        return True, "Escalating to HR is always allowed."
    if action == ProposalAction.REQUEST_EMPLOYEE_CONFIRMATION:
        if target.type in FIXABLE_TYPES:
            return True, "Employee confirmation is a valid next step."
        return False, f"Employee confirmation does not resolve {target.type.value}."
    if action == ProposalAction.FLAG_OVERTIME_FOR_APPROVAL:
        if target.type == ExceptionType.OVERTIME_RISK:
            return True, "Overtime is routed for approval."
        return False, f"Flagging overtime does not resolve {target.type.value}."
    # Data-changing actions
    if target.type not in FIXABLE_TYPES:
        return False, (f"{target.type.value} cannot be fixed by editing punches. "
                       "Route it for approval or escalate.")
    if patched is None:
        return False, "Could not apply the changes."
    left = [e for e in detect(patched, policy) if e.type == target.type and e.work_date == target.work_date]
    if left:
        return False, f"{target.type.value} is still present after the change."
    return True, f"{target.type.value} on {target.work_date} is cleared."


def _check_no_new(original: list[ExceptionRecord], patched: Optional[Timecard], policy) -> Result:
    if patched is None:
        return False, "Could not apply the changes."
    before = {(e.type, e.work_date) for e in original}
    new = [(e.type.value, e.work_date.isoformat()) for e in detect(patched, policy)
           if (e.type, e.work_date) not in before]
    if new:
        return False, "The change creates new exception(s): " + ", ".join(f"{t} on {d}" for t, d in new)
    return True, "No new exceptions."


def _check_evidence(proposal, timecard, known_history_ids) -> Result:
    have = {
        "punch": {p.id for p in timecard.punches},
        "shift": {s.id for s in timecard.shifts},
        "leave": {x.id for x in timecard.leaves},
    }
    if proposal.action in DATA_ACTIONS and not proposal.evidence:
        return False, "A timecard change must cite at least one piece of evidence."
    missing = []
    for ref in proposal.evidence:
        if ref.kind == "history":
            if known_history_ids is not None and ref.id not in known_history_ids:
                missing.append(f"history:{ref.id}")
        elif ref.id not in have[ref.kind]:
            missing.append(f"{ref.kind}:{ref.id}")
    if missing:
        return False, "Evidence not found: " + ", ".join(missing)
    return True, f"{len(proposal.evidence)} evidence reference(s) exist."


def _check_clauses(proposal, policy) -> Result:
    if proposal.action in DATA_ACTIONS and not proposal.policy_clauses:
        return False, "A timecard change must cite at least one policy clause."
    known = {c.id.upper() for c in policy.clauses} if policy else set()
    missing = [c for c in proposal.policy_clauses if c.upper() not in known]
    if missing:
        return False, "Policy clause(s) not found: " + ", ".join(missing)
    return True, f"{len(proposal.policy_clauses)} policy clause(s) exist."


def _check_window(proposal, timecard, policy) -> Result:
    if proposal.action not in DATA_ACTIONS:
        return True, "No punch changes."
    if any(t.tzinfo is None for t in _times(proposal)):
        return False, "Every timestamp must include a UTC offset."
    window = get_param(policy, "MISS-01", "max_punch_add_window_minutes", 30)
    shifts = [s for s in timecard.shifts if s.employee_id == timecard.employee_id]
    if not shifts:
        return False, "No scheduled shift to compare the punch against."
    for ch in proposal.changes:
        if ch.op in ("add_punch", "adjust_punch"):
            gap = min(abs((ch.at - b).total_seconds()) / 60 for s in shifts for b in (s.start, s.end))
            if gap > window:
                return False, f"Punch at {ch.at:%H:%M} is {gap:.0f} min from the shift boundary (max {window:g})."
        else:
            inside = any(s.start <= ch.break_start and ch.break_end <= s.end for s in shifts)
            if not inside:
                return False, "Break is outside the scheduled shift."
    return True, f"All punches are within {window:g} min of the shift boundary."


def _check_locked(proposal, timecard) -> Result:
    if proposal.action in DATA_ACTIONS and timecard.locked:
        return False, "The pay period is locked; it cannot be changed."
    return True, "Pay period is not locked." if not timecard.locked else "Locked, but nothing is being changed."


def validate(
    proposal: Proposal,
    timecard: Timecard,
    policy: Optional[PolicyPack] = None,
    exception: Optional[ExceptionRecord] = None,
    known_history_ids: Optional[set[str]] = None,
) -> ValidationResult:
    """Run the seven checks. Extra keyword arguments are optional; callers may ignore them."""
    original = detect(timecard, policy)
    target = exception or next((e for e in original if e.id == proposal.exception_id), None)

    changes_ok = _check_changes(proposal, timecard)
    patched: Optional[Timecard] = None
    if changes_ok[0]:
        try:
            patched = apply_proposal(timecard, proposal)
        except Exception:  # bad data in the proposal must never crash the validator
            patched = None
            changes_ok = (False, "The changes could not be applied.")

    results: dict[ValidationCheck, Result] = {
        ValidationCheck.CHANGES_MATCH_ACTION: changes_ok,
        ValidationCheck.TARGET_EXCEPTION_CLEARED: _check_target(proposal, target, patched, policy),
        ValidationCheck.NO_NEW_EXCEPTIONS: _check_no_new(original, patched, policy),
        ValidationCheck.EVIDENCE_EXISTS: _check_evidence(proposal, timecard, known_history_ids),
        ValidationCheck.CLAUSES_EXIST: _check_clauses(proposal, policy),
        ValidationCheck.PUNCH_WITHIN_WINDOW: _check_window(proposal, timecard, policy),
        ValidationCheck.PERIOD_NOT_LOCKED: _check_locked(proposal, timecard),
    }
    checks = [CheckResult(name=c.value, passed=results[c][0], detail=results[c][1])
              for c in VALIDATION_CHECK_ORDER]
    impact = pay_impact(timecard, patched, policy) if patched is not None else None
    return ValidationResult(passed=all(c.passed for c in checks), checks=checks, pay_impact=impact)
