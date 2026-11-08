from datetime import date

from backend.core.api import detect, load_policy
from backend.core.models import ExceptionType as E, Leave, PunchType as P
from backend.core.tests.helpers import card, day, t

CA = load_policy("CA")
KA = load_policy("KA")


def types(excs):
    return [e.type for e in excs]


def test_policy_loads_in_any_case_and_unknown_is_none():
    assert CA is not None and CA.jurisdiction == "CA"
    assert load_policy("ka").jurisdiction == "KA"
    assert load_policy("XX") is None


def test_clean_day_has_no_exceptions():
    assert detect(card(day("2026-11-03")), CA) == []


def test_missing_clock_out():
    excs = detect(card(day("2026-11-03", out=None)), CA)
    assert types(excs) == [E.MISSED_PUNCH]
    assert excs[0].work_date == date(2026, 11, 3)
    assert excs[0].policy_clauses == ["CA-MISS-01"]


def test_missing_clock_in():
    rows = [(P.OUT, t("2026-11-03", "17:00"))]
    assert types(detect(card(rows), CA)) == [E.MISSED_PUNCH]


def test_unclosed_break():
    rows = [(P.IN, t("2026-11-03", "09:00")), (P.BREAK_START, t("2026-11-03", "13:00")),
            (P.OUT, t("2026-11-03", "17:00"))]
    excs = detect(card(rows), CA)
    assert E.MISSED_PUNCH in types(excs)


def test_daily_overtime_uses_policy_threshold():
    rows = day("2026-11-04", out="20:30")  # 11h worked
    assert types(detect(card(rows), CA)) == [E.OVERTIME_RISK]
    rows = day("2026-11-04", out="18:00")  # 8.5h worked: over CA 8h, under KA 9h
    assert types(detect(card(rows), CA)) == [E.OVERTIME_RISK]
    assert detect(card(rows, jurisdiction="KA"), KA) == []


def test_weekly_overtime():
    rows = []
    for d in ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]:
        rows += day(d, out="17:30")  # 8h worked each, 40h total
    rows += day("2026-11-07", in_="09:00", out="10:00", brk=None)  # +1h -> 41h
    excs = detect(card(rows), CA)
    assert types(excs) == [E.OVERTIME_RISK]
    assert excs[0].work_date == date(2026, 11, 7)


def test_meal_break_missing_and_short():
    assert types(detect(card(day("2026-11-03", brk=None)), CA)) == [E.MEAL_BREAK_VIOLATION]
    assert types(detect(card(day("2026-11-03", brk=("13:00", "13:10"))), CA)) == [E.MEAL_BREAK_VIOLATION]


def test_short_shift_needs_no_meal_break():
    assert detect(card(day("2026-11-03", out="13:00", brk=None)), CA) == []


def test_rest_period_breach():
    rows = day("2026-11-03", in_="14:00", out="23:00") + day("2026-11-04", in_="05:00", out="12:00", brk=None)
    assert E.REST_PERIOD_BREACH in types(detect(card(rows), CA))


def test_leave_conflict():
    leave = Leave(id="l1", employee_id="e1", start=t("2026-11-03", "00:00"), end=t("2026-11-04", "00:00"))
    assert E.SCHEDULE_LEAVE_CONFLICT in types(detect(card(day("2026-11-03"), leaves=[leave]), CA))


def test_unknown_jurisdiction_still_finds_missed_punch_but_not_overtime():
    excs = detect(card(day("2026-11-03", out=None), jurisdiction="XX"), None)
    assert types(excs) == [E.MISSED_PUNCH] and excs[0].policy_clauses == []
    assert detect(card(day("2026-11-04", out="23:00"), jurisdiction="XX"), None) == []


def test_exception_ids_are_stable():
    a = detect(card(day("2026-11-03", out=None)), CA)[0].id
    b = detect(card(day("2026-11-03", out=None)), CA)[0].id
    assert a == b == "exc_tc1_MISSED_PUNCH_2026-11-03"


def test_night_shift_across_midnight_is_one_session():
    rows = [(P.IN, t("2026-11-03", "22:00")), (P.OUT, t("2026-11-04", "06:00"))]
    excs = detect(card(rows), CA)
    assert E.MISSED_PUNCH not in types(excs)
