"""InMemoryContextProvider: built from a golden case dict.

Used by tests and evals so agent code needs no database.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from backend.core.api import detect, load_policy
from backend.core.models import (
    ExceptionRecord,
    Leave,
    PolicyPack,
    Punch,
    Shift,
    Timecard,
)


class InMemoryContextProvider:
    """ContextProvider backed by a single golden-case dict.

    Constructed from the JSON structure in evals/golden/*.jsonl:
      {"timecard": {...}, ...}
    """

    def __init__(self, case: dict) -> None:
        self.timecard = Timecard.model_validate(case["timecard"])
        self.policy = load_policy(self.timecard.jurisdiction)
        self._exceptions = detect(self.timecard, self.policy)
        self._exc_map: dict[str, ExceptionRecord] = {e.id: e for e in self._exceptions}

    # --- ContextProvider methods -------------------------------------------

    def get_exception(self, exception_id: str) -> ExceptionRecord:
        exc = self._exc_map.get(exception_id)
        if exc is None:
            raise KeyError(f"Exception not found: {exception_id}")
        return exc

    def get_timecard(self, timecard_id: str) -> Timecard:
        if timecard_id != self.timecard.id:
            raise KeyError(f"Timecard not found: {timecard_id}")
        return self.timecard

    def get_schedule(self, employee_id: str, start: date, end: date) -> list[Shift]:
        return [
            s for s in self.timecard.shifts
            if s.employee_id == employee_id
            and s.start.date() <= end
            and s.end.date() >= start
        ]

    def get_leave(self, employee_id: str, start: date, end: date) -> list[Leave]:
        return [
            l for l in self.timecard.leaves
            if l.employee_id == employee_id
            and l.start.date() <= end
            and l.end.date() >= start
        ]

    def get_history(self, employee_id: str, weeks: int = 4) -> list[Punch]:
        return [p for p in self.timecard.punches if p.employee_id == employee_id]

    def get_policy_pack(self, jurisdiction: str) -> Optional[PolicyPack]:
        if self.policy and self.policy.jurisdiction.upper() == jurisdiction.upper():
            return self.policy
        return load_policy(jurisdiction)

    # --- Convenience -------------------------------------------------------

    @property
    def exceptions(self) -> list[ExceptionRecord]:
        return list(self._exceptions)

    def first_exception_id(self) -> str:
        if not self._exceptions:
            raise ValueError("No exceptions detected in this case")
        return self._exceptions[0].id
