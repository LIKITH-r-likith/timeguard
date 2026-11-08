"""pay_impact(): what a proposed timecard change does to paid minutes and cost."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from backend.core.models import PayImpact, PolicyPack, Timecard
from backend.core.policy import get_param
from backend.core.sessions import build_sessions

# MOCK values for the demo, not real payroll data.
MOCK_HOURLY_RATE = 500.0  # INR per hour
OVERTIME_MULTIPLIER = 1.5


def split_minutes(timecard: Timecard, policy: Optional[PolicyPack] = None) -> tuple[int, int]:
    """Return (regular_minutes, overtime_minutes) for the whole timecard."""
    daily_after = get_param(policy, "OT-DAILY-01", "daily_ot_after_hours", 8) * 60
    weekly_after = get_param(policy, "OT-WEEKLY-01", "weekly_ot_after_hours", 40) * 60
    per_day: dict = defaultdict(int)
    for s in build_sessions(timecard.punches):
        per_day[s.work_date] += s.worked_minutes()
    regular = overtime = 0
    for minutes in per_day.values():
        daily_ot = max(0, minutes - int(daily_after))
        overtime += daily_ot
        regular += minutes - daily_ot
    if regular > weekly_after:  # weekly rule moves the extra regular minutes to overtime
        overtime += int(regular - weekly_after)
        regular = int(weekly_after)
    return regular, overtime


def pay_impact(before: Timecard, after: Timecard, policy: Optional[PolicyPack] = None) -> PayImpact:
    reg_b, ot_b = split_minutes(before, policy)
    reg_a, ot_a = split_minutes(after, policy)
    d_reg, d_ot = reg_a - reg_b, ot_a - ot_b
    cost = d_reg / 60 * MOCK_HOURLY_RATE + d_ot / 60 * MOCK_HOURLY_RATE * OVERTIME_MULTIPLIER
    return PayImpact(
        regular_minutes_delta=d_reg,
        overtime_minutes_delta=d_ot,
        estimated_cost_delta=round(cost, 2),
        currency="INR",
    )
