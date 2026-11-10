"""Database-backed ContextProvider implementation for the LLM agent and validation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    ExceptionModel,
    LeaveModel,
    PunchModel,
    ShiftModel,
    TimecardModel,
)
from backend.core.api import load_policy
from backend.core.models import (
    ExceptionRecord,
    ExceptionStatus,
    ExceptionType,
    Leave,
    PolicyPack,
    Punch,
    PunchType,
    RiskTier,
    Shift,
    Timecard,
)


class DbContextProvider:
    """Read-only ContextProvider reading from SQLite via SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_exception(self, exception_id: str) -> ExceptionRecord:
        """Fetch an exception record by ID from the database."""
        stmt = select(ExceptionModel).where(ExceptionModel.id == exception_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise KeyError(f"Exception not found: {exception_id}")
        return ExceptionRecord(
            id=row.id,
            type=ExceptionType(row.type),
            employee_id=row.employee_id,
            timecard_id=row.timecard_id,
            work_date=row.work_date,
            detail=row.detail,
            policy_clauses=list(row.policy_clauses or []),
            status=ExceptionStatus(row.status),
            risk=RiskTier(row.risk) if row.risk else None,
        )

    def get_timecard(self, timecard_id: str) -> Timecard:
        """Fetch and reconstruct a full Timecard domain model by ID."""
        stmt = select(TimecardModel).where(TimecardModel.id == timecard_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise KeyError(f"Timecard not found: {timecard_id}")

        shifts = [
            Shift(
                id=s.id,
                employee_id=s.employee_id,
                start=datetime.fromisoformat(s.start),
                end=datetime.fromisoformat(s.end),
                scheduled_break_minutes=s.scheduled_break_minutes,
            )
            for s in row.shifts
        ]

        punches = [
            Punch(
                id=p.id,
                employee_id=p.employee_id,
                type=PunchType(p.type),
                at=datetime.fromisoformat(p.at),
            )
            for p in row.punches
        ]

        leaves = [
            Leave(
                id=l.id,
                employee_id=l.employee_id,
                start=datetime.fromisoformat(l.start),
                end=datetime.fromisoformat(l.end),
                kind=l.kind,
            )
            for l in row.leaves
        ]

        return Timecard(
            id=row.id,
            employee_id=row.employee_id,
            jurisdiction=row.jurisdiction,
            period_start=row.period_start,
            period_end=row.period_end,
            locked=row.locked,
            shifts=shifts,
            punches=punches,
            leaves=leaves,
            notes=list(row.notes or []),
        )

    def get_schedule(self, employee_id: str, start: date, end: date) -> list[Shift]:
        """Fetch scheduled shifts for an employee within a date window."""
        stmt = select(ShiftModel).where(ShiftModel.employee_id == employee_id)
        rows = self.session.execute(stmt).scalars().all()
        result = []
        for s in rows:
            st = datetime.fromisoformat(s.start)
            en = datetime.fromisoformat(s.end)
            if st.date() <= end and en.date() >= start:
                result.append(
                    Shift(
                        id=s.id,
                        employee_id=s.employee_id,
                        start=st,
                        end=en,
                        scheduled_break_minutes=s.scheduled_break_minutes,
                    )
                )
        return result

    def get_leave(self, employee_id: str, start: date, end: date) -> list[Leave]:
        """Fetch approved leave periods for an employee within a date window."""
        stmt = select(LeaveModel).where(LeaveModel.employee_id == employee_id)
        rows = self.session.execute(stmt).scalars().all()
        result = []
        for l in rows:
            st = datetime.fromisoformat(l.start)
            en = datetime.fromisoformat(l.end)
            if st.date() <= end and en.date() >= start:
                result.append(
                    Leave(
                        id=l.id,
                        employee_id=l.employee_id,
                        start=st,
                        end=en,
                        kind=l.kind,
                    )
                )
        return result

    def get_history(self, employee_id: str, weeks: int = 4) -> list[Punch]:
        """Fetch historical punches for an employee spanning recent weeks."""
        stmt = select(PunchModel).where(PunchModel.employee_id == employee_id)
        rows = self.session.execute(stmt).scalars().all()
        return [
            Punch(
                id=p.id,
                employee_id=p.employee_id,
                type=PunchType(p.type),
                at=datetime.fromisoformat(p.at),
            )
            for p in rows
        ]

    def get_policy_pack(self, jurisdiction: str) -> Optional[PolicyPack]:
        """Load the policy pack corresponding to the requested jurisdiction."""
        return load_policy(jurisdiction)
