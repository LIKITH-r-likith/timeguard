"""Seed data loader for TimeGuard database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    Employee,
    LeaveModel,
    PunchModel,
    ShiftModel,
    TimecardModel,
)
from backend.core.models import Role

DEMO_EMPLOYEES = [
    {"id": "e01", "name": "Alice Employee", "email": "alice@timeguard.demo", "manager_id": "m01", "role": Role.EMPLOYEE.value},
    {"id": "e02", "name": "Bob Worker", "email": "bob@timeguard.demo", "manager_id": "m01", "role": Role.EMPLOYEE.value},
    {"id": "e03", "name": "Charlie Staff", "email": "charlie@timeguard.demo", "manager_id": "m01", "role": Role.EMPLOYEE.value},
    {"id": "m01", "name": "Mary Manager", "email": "mary@timeguard.demo", "manager_id": None, "role": Role.MANAGER.value},
    {"id": "hr01", "name": "Helen HR", "email": "helen@timeguard.demo", "manager_id": None, "role": Role.HR.value},
]


def load_seed_timecards(session: Session, cases_file: Optional[Path] = None) -> int:
    """Populate database from golden cases JSONL."""
    if cases_file is None:
        root = Path(__file__).resolve().parents[2]
        cases_file = root / "evals" / "golden" / "example_cases.jsonl"

    if not cases_file.exists():
        return 0

    # 1. Ensure employees exist
    for emp_data in DEMO_EMPLOYEES:
        emp_id = emp_data["id"]
        existing = session.execute(select(Employee).where(Employee.id == emp_id)).scalar_one_or_none()
        if not existing:
            session.add(Employee(**emp_data))
    session.flush()

    count = 0
    lines = [l.strip() for l in cases_file.read_text("utf-8").splitlines() if l.strip()]
    for line in lines:
        data = json.loads(line)
        tc_dict = data.get("timecard", {})
        tc_id = tc_dict.get("id")
        if not tc_id:
            continue

        existing_tc = session.execute(select(TimecardModel).where(TimecardModel.id == tc_id)).scalar_one_or_none()
        if existing_tc:
            continue

        emp_id = tc_dict.get("employee_id")
        # Ensure employee row exists
        existing_emp = session.execute(select(Employee).where(Employee.id == emp_id)).scalar_one_or_none()
        if not existing_emp:
            session.add(Employee(
                id=emp_id,
                name=f"Employee {emp_id}",
                email=f"{emp_id}@timeguard.demo",
                manager_id="m01",
                role=Role.EMPLOYEE.value,
            ))
            session.flush()

        timecard = TimecardModel(
            id=tc_id,
            employee_id=emp_id,
            jurisdiction=tc_dict.get("jurisdiction", "CA"),
            period_start=date_from_iso(tc_dict.get("period_start")),
            period_end=date_from_iso(tc_dict.get("period_end")),
            locked=tc_dict.get("locked", False),
            notes=tc_dict.get("notes", []),
        )
        session.add(timecard)
        session.flush()

        for s in tc_dict.get("shifts", []):
            session.add(ShiftModel(
                id=s["id"],
                timecard_id=tc_id,
                employee_id=s["employee_id"],
                start=s["start"],
                end=s["end"],
                scheduled_break_minutes=s.get("scheduled_break_minutes", 0),
            ))

        for p in tc_dict.get("punches", []):
            session.add(PunchModel(
                id=p["id"],
                timecard_id=tc_id,
                employee_id=p["employee_id"],
                type=p["type"],
                at=p["at"],
            ))

        for l in tc_dict.get("leaves", []):
            session.add(LeaveModel(
                id=l["id"],
                timecard_id=tc_id,
                employee_id=l["employee_id"],
                start=l["start"],
                end=l["end"],
                kind=l.get("kind", "PAID"),
            ))

        count += 1

    session.commit()
    return count


def date_from_iso(d_str: str):
    from datetime import date
    return date.fromisoformat(d_str)


if __name__ == "__main__":
    from data.seed.seed import main
    main()

