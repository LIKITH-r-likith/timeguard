"""Small builders so tests read like plain English."""

from datetime import datetime

from backend.core.models import Leave, Punch, Shift, Timecard

TZ = "+05:30"


def t(day: str, hhmm: str) -> datetime:
    """t("2026-11-03", "09:00") -> aware datetime in India time."""
    return datetime.fromisoformat(f"{day}T{hhmm}:00{TZ}")


def card(punches, shifts=None, leaves=None, jurisdiction="CA", locked=False, notes=None, cid="tc1"):
    ps = [Punch(id=f"p{i}", employee_id="e1", type=ty, at=at) for i, (ty, at) in enumerate(punches, 1)]
    return Timecard(
        id=cid, employee_id="e1", jurisdiction=jurisdiction,
        period_start="2026-11-02", period_end="2026-11-08", locked=locked,
        shifts=shifts if shifts is not None else [Shift(id="s1", employee_id="e1", start=t("2026-11-03", "09:00"),
                                                         end=t("2026-11-03", "17:00"), scheduled_break_minutes=30)],
        punches=ps, leaves=leaves or [], notes=notes or [],
    )


def day(d, in_="09:00", out="17:00", brk=("13:00", "13:30")):
    """Punch tuples for one normal working day."""
    from backend.core.models import PunchType as P
    rows = [(P.IN, t(d, in_))]
    if brk:
        rows += [(P.BREAK_START, t(d, brk[0])), (P.BREAK_END, t(d, brk[1]))]
    if out:
        rows.append((P.OUT, t(d, out)))
    return rows
