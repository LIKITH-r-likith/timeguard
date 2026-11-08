"""Turn a flat list of punches into work sessions (IN ... OUT with breaks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from backend.core.models import Punch, PunchType


@dataclass
class WorkSession:
    start: Optional[Punch]  # the IN punch, None if the clock-in is missing
    end: Optional[Punch] = None  # the OUT punch, None if the clock-out is missing
    breaks: list[tuple[datetime, datetime]] = field(default_factory=list)
    unclosed_break_at: Optional[datetime] = None  # BREAK_START with no BREAK_END

    @property
    def work_date(self) -> date:
        anchor = self.start or self.end
        return anchor.at.date()

    @property
    def closed(self) -> bool:
        return self.start is not None and self.end is not None

    def span_minutes(self) -> int:
        if not self.closed:
            return 0
        return int((self.end.at - self.start.at).total_seconds() // 60)

    def break_minutes(self) -> int:
        return sum(int((b - a).total_seconds() // 60) for a, b in self.breaks)

    def worked_minutes(self) -> int:
        if not self.closed:
            return 0
        return max(0, self.span_minutes() - self.break_minutes())


def build_sessions(punches: list[Punch]) -> list[WorkSession]:
    sessions: list[WorkSession] = []
    cur: Optional[WorkSession] = None
    open_break: Optional[datetime] = None

    def finish() -> None:
        nonlocal cur, open_break
        if cur is not None:
            cur.unclosed_break_at = open_break
            sessions.append(cur)
        cur, open_break = None, None

    for p in sorted(punches, key=lambda x: x.at):
        if p.type == PunchType.IN:
            finish()  # a new IN while one is open: the old one never clocked out
            cur = WorkSession(start=p)
        elif p.type == PunchType.OUT:
            if cur is None:
                sessions.append(WorkSession(start=None, end=p))  # OUT with no IN
            else:
                cur.end = p
                finish()
        elif p.type == PunchType.BREAK_START:
            if cur is not None and open_break is None:
                open_break = p.at
        elif p.type == PunchType.BREAK_END:
            if cur is not None and open_break is not None:
                cur.breaks.append((open_break, p.at))
                open_break = None
    finish()
    return sessions
