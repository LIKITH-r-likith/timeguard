from backend.core.api import detect, load_policy, pay_impact, risk_tier, validate
from backend.core.contract import VALIDATION_CHECK_ORDER
from backend.core.models import (Change, EvidenceRef, ExceptionType as E, PayImpact, Proposal,
                                 ProposalAction as A, PunchType as P, RiskTier)
from backend.core.tests.helpers import card, day, t

CA = load_policy("CA")
EXC = "exc_tc1_MISSED_PUNCH_2026-11-03"


def missed():
    return card(day("2026-11-03", out=None))


def proposal(action=A.ADD_PUNCH, at="17:02", exc=EXC, changes=None, evidence=None, clauses=None, conf=0.85):
    if changes is None:
        changes = [Change(op="add_punch", type=P.OUT, at=t("2026-11-03", at))] if action == A.ADD_PUNCH else []
    return Proposal(
        exception_id=exc, action=action, changes=changes, rationale="test",
        evidence=[EvidenceRef(kind="punch", id="p1"), EvidenceRef(kind="shift", id="s1")] if evidence is None else evidence,
        policy_clauses=["CA-MISS-01"] if clauses is None else clauses,
        confidence=conf, needs_employee_confirmation=True)


def failed(res):
    return {c.name for c in res.checks if not c.passed}


def test_good_missed_punch_fix_passes_all_seven_checks():
    res = validate(proposal(), missed(), CA)
    assert res.passed, [c for c in res.checks if not c.passed]
    assert [c.name for c in res.checks] == [c.value for c in VALIDATION_CHECK_ORDER]
    assert res.pay_impact.regular_minutes_delta == 452  # 09:00-17:02 minus a 30 min break


def test_punch_creating_overtime_is_rejected_the_demo_moment():
    res = validate(proposal(changes=[Change(op="add_punch", type=P.OUT, at=t("2026-11-03", "21:00"))]), missed(), CA)
    assert not res.passed
    assert "no_new_exceptions" in failed(res) and "punch_within_window" in failed(res)


def test_fabricated_evidence_and_clause_are_rejected():
    res = validate(proposal(evidence=[EvidenceRef(kind="punch", id="p_999")], clauses=["CA-FAKE-99"]), missed(), CA)
    assert failed(res) == {"evidence_exists", "clauses_exist"}


def test_data_change_must_cite_evidence_and_clause():
    res = validate(proposal(evidence=[], clauses=[]), missed(), CA)
    assert failed(res) == {"evidence_exists", "clauses_exist"}


def test_wrong_exception_id_is_rejected():
    assert "target_exception_cleared" in failed(validate(proposal(exc="exc_nope"), missed(), CA))


def test_locked_period_cannot_be_changed():
    locked = card(day("2026-11-03", out=None), locked=True)
    assert "period_not_locked" in failed(validate(proposal(), locked, CA))
    esc = proposal(A.ESCALATE_TO_HR, evidence=[], clauses=[])
    assert validate(esc, locked, CA).passed


def test_naive_timestamp_does_not_crash():
    from datetime import datetime
    p = proposal(changes=[Change(op="add_punch", type=P.OUT, at=datetime(2026, 11, 3, 17, 0))])
    res = validate(p, missed(), CA)
    assert not res.passed


def test_escalate_and_confirmation_have_no_changes():
    assert validate(proposal(A.ESCALATE_TO_HR, evidence=[], clauses=[]), missed(), CA).passed
    assert validate(proposal(A.REQUEST_EMPLOYEE_CONFIRMATION), missed(), CA).passed
    bad = proposal(A.ESCALATE_TO_HR, changes=[Change(op="add_punch", type=P.OUT, at=t("2026-11-03", "17:00"))])
    assert "changes_match_action" in failed(validate(bad, missed(), CA))


def test_overtime_cannot_be_hidden_by_editing_punches():
    ot = card(day("2026-11-04", out="20:30"), shifts=[], cid="tc2")
    eid = "exc_tc2_OVERTIME_RISK_2026-11-04"
    assert eid in [e.id for e in detect(ot, CA)]
    fake = Proposal(exception_id=eid, action=A.ADJUST_PUNCH, rationale="x", confidence=0.9,
                    changes=[Change(op="adjust_punch", punch_id="p4", at=t("2026-11-04", "17:00"))],
                    evidence=[EvidenceRef(kind="punch", id="p4")], policy_clauses=["CA-OT-DAILY-01"])
    assert "target_exception_cleared" in failed(validate(fake, ot, CA))
    flag = Proposal(exception_id=eid, action=A.FLAG_OVERTIME_FOR_APPROVAL, rationale="x", confidence=0.9,
                    policy_clauses=["CA-OT-DAILY-01"])
    assert validate(flag, ot, CA).passed


def test_insert_break_fixes_missing_meal_break():
    c = card(day("2026-11-03", brk=None))
    eid = "exc_tc1_MEAL_BREAK_VIOLATION_2026-11-03"
    p = Proposal(exception_id=eid, action=A.INSERT_BREAK, rationale="x", confidence=0.8,
                 changes=[Change(op="insert_break", break_start=t("2026-11-03", "13:00"), break_end=t("2026-11-03", "13:30"))],
                 evidence=[EvidenceRef(kind="shift", id="s1")], policy_clauses=["CA-MEAL-01"])
    assert validate(p, c, CA).passed


def test_pay_impact_numbers():
    before, after = missed(), card(day("2026-11-03", out="17:00"))
    imp = pay_impact(before, after, CA)
    assert imp.regular_minutes_delta == 450 and imp.overtime_minutes_delta == 0
    assert imp.estimated_cost_delta == 3750.0


def test_risk_tiers_match_golden_examples():
    exc = detect(missed(), CA)[0]
    low = proposal()
    assert risk_tier(exc, low, pay_impact(missed(), card(day("2026-11-03")), CA)) == RiskTier.LOW
    assert risk_tier(exc, proposal(A.ESCALATE_TO_HR), PayImpact()) == RiskTier.HIGH
    ot = detect(card(day("2026-11-04", out="20:30")), CA)[0]
    flag = Proposal(exception_id=ot.id, action=A.FLAG_OVERTIME_FOR_APPROVAL, rationale="x", confidence=0.9)
    assert risk_tier(ot, flag, PayImpact()) == RiskTier.MEDIUM
    assert risk_tier(exc, proposal(conf=0.4), PayImpact()) == RiskTier.HIGH
