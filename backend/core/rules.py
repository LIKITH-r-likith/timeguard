"""detect(): the inspector. Finds timecard exceptions with plain rules, no AI."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from backend.core.models import ExceptionRecord, ExceptionType, PolicyPack, Timecard
from backend.core.policy import find_clause, get_param
from backend.core.sessions import build_sessions


def exception_id(timecard_id: str, etype: ExceptionType, work_date: date) -> str:
    """Stable id. The same timecard problem always gets the same id, so
    validate() can find the exception again from proposal.exception_id."""
    return f"exc_{timecard_id}_{etype.value}_{work_date.isoformat()}"


def detect(timecard: Timecard, policy: Optional[PolicyPack] = None) -> list[ExceptionRecord]:
    found: dict[tuple[ExceptionType, date], dict] = {}

    def add(etype: ExceptionType, work_date: date, detail: str, suffixes: list[str]) -> None:
        clauses = [c.id for s in suffixes if (c := find_clause(policy, s)) is not None]
        entry = found.setdefault((etype, work_date), {"details": [], "clauses": []})
        entry["details"].append(detail)
        for cid in clauses:
            if cid not in entry["clauses"]:
                entry["clauses"].append(cid)

    sessions = build_sessions(timecard.punches)

    # 1. Missed punches (no policy needed)
    for s in sessions:
        if s.start is None:
            add(ExceptionType.MISSED_PUNCH, s.work_date,
                f"Clock-out at {s.end.at:%H:%M} has no clock-in before it.", ["MISS-01"])
        elif s.end is None:
            add(ExceptionType.MISSED_PUNCH, s.work_date,
                f"Clocked in at {s.start.at:%H:%M} but never clocked out.", ["MISS-01"])
        if s.unclosed_break_at is not None:
            add(ExceptionType.MISSED_PUNCH, s.work_date,
                f"Break started at {s.unclosed_break_at:%H:%M} but never ended.", ["MISS-01"])

    # 2. Schedule vs leave conflict (no policy needed)
    for s in sessions:
        first = (s.start or s.end).at
        last = (s.end or s.start).at
        for leave in timecard.leaves:
            if first < leave.end and last >= leave.start:
                add(ExceptionType.SCHEDULE_LEAVE_CONFLICT, s.work_date,
                    f"Worked time overlaps {leave.kind} leave {leave.id}.", ["LEAVE-01"])

    # 3. Meal break
    meal_after = find_clause(policy, "MEAL-01")
    if meal_after is not None:
        after_h = get_param(policy, "MEAL-01", "meal_required_after_hours", 5)
        min_meal = get_param(policy, "MEAL-01", "min_meal_minutes", 30)
        for s in sessions:
            if s.closed and s.span_minutes() > after_h * 60 and s.break_minutes() < min_meal:
                add(ExceptionType.MEAL_BREAK_VIOLATION, s.work_date,
                    f"Shift of {s.span_minutes() / 60:.1f} h has {s.break_minutes()} min of meal break "
                    f"(needs {min_meal:g}).", ["MEAL-01"])

    # 4. Rest between shifts
    if find_clause(policy, "REST-01") is not None:
        min_rest = get_param(policy, "REST-01", "min_rest_hours_between_shifts", 8)
        for prev, nxt in zip(sessions, sessions[1:]):
            if prev.end is not None and nxt.start is not None:
                gap = (nxt.start.at - prev.end.at).total_seconds() / 3600
                if gap < min_rest:
                    add(ExceptionType.REST_PERIOD_BREACH, nxt.work_date,
                        f"Only {gap:.1f} h of rest before this shift (needs {min_rest:g}).", ["REST-01"])

    # 5. Overtime (daily, then weekly)
    if find_clause(policy, "OT-DAILY-01") is not None:
        daily_after = get_param(policy, "OT-DAILY-01", "daily_ot_after_hours", 8)
        daily_max = get_param(policy, "OT-DAILY-01", "max_daily_hours", 12)
        per_day: dict[date, int] = defaultdict(int)
        for s in sessions:
            per_day[s.work_date] += s.worked_minutes()
        for day, minutes in sorted(per_day.items()):
            if minutes > daily_after * 60:
                extra = f" This is above the {daily_max:g} h daily maximum." if minutes > daily_max * 60 else ""
                add(ExceptionType.OVERTIME_RISK, day,
                    f"Worked {minutes / 60:.1f} h; overtime starts after {daily_after:g} h.{extra}",
                    ["OT-DAILY-01"])
        if find_clause(policy, "OT-WEEKLY-01") is not None:
            weekly_after = get_param(policy, "OT-WEEKLY-01", "weekly_ot_after_hours", 40)
            total = 0
            for day, minutes in sorted(per_day.items()):
                total += minutes
                if total > weekly_after * 60:
                    if (ExceptionType.OVERTIME_RISK, day) not in found:
                        add(ExceptionType.OVERTIME_RISK, day,
                            f"Weekly hours reach {total / 60:.1f} h; weekly overtime starts after "
                            f"{weekly_after:g} h.", ["OT-WEEKLY-01"])
                    break

    records = [
        ExceptionRecord(
            id=exception_id(timecard.id, etype, day),
            type=etype,
            employee_id=timecard.employee_id,
            timecard_id=timecard.id,
            work_date=day,
            detail=" ".join(v["details"]),
            policy_clauses=v["clauses"],
        )
        for (etype, day), v in found.items()
    ]
    records.sort(key=lambda r: (r.work_date, r.type.value))
    return records
