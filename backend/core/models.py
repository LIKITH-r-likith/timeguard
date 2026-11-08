"""
TimeGuard shared contract: enums and data models.

Owner: Person 1. Every other component (agent, API, frontend types) codes
against this file. Enums are FROZEN at hour 3. Changing an enum value or a
field name afterwards needs all four people to agree in the team chat.

Conventions
- Timestamps are ISO-8601 with a UTC offset (e.g. 2026-11-03T17:02:00+05:30).
- IDs are strings.
- Errors use {code, message, details} (see ErrorResponse).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# Enums (frozen at hour 3)
# --------------------------------------------------------------------------
class ExceptionType(str, Enum):
    MISSED_PUNCH = "MISSED_PUNCH"
    OVERTIME_RISK = "OVERTIME_RISK"
    MEAL_BREAK_VIOLATION = "MEAL_BREAK_VIOLATION"  # missing or short meal break
    SCHEDULE_LEAVE_CONFLICT = "SCHEDULE_LEAVE_CONFLICT"
    REST_PERIOD_BREACH = "REST_PERIOD_BREACH"


class ProposalAction(str, Enum):
    ADD_PUNCH = "ADD_PUNCH"
    ADJUST_PUNCH = "ADJUST_PUNCH"
    INSERT_BREAK = "INSERT_BREAK"
    REQUEST_EMPLOYEE_CONFIRMATION = "REQUEST_EMPLOYEE_CONFIRMATION"
    FLAG_OVERTIME_FOR_APPROVAL = "FLAG_OVERTIME_FOR_APPROVAL"
    ESCALATE_TO_HR = "ESCALATE_TO_HR"


class RiskTier(str, Enum):
    LOW = "LOW"        # employee confirmation + manager approval
    MEDIUM = "MEDIUM"  # manager approval
    HIGH = "HIGH"      # HR approval required


class Role(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HR = "HR"


class PunchType(str, Enum):
    IN = "IN"
    OUT = "OUT"
    BREAK_START = "BREAK_START"
    BREAK_END = "BREAK_END"


class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    PROPOSED = "PROPOSED"
    AWAITING_EMPLOYEE = "AWAITING_EMPLOYEE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _require_offset(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return v


# --------------------------------------------------------------------------
# Timecard data (one normalized schema for rules, agent, API and UI)
# --------------------------------------------------------------------------
class Punch(BaseModel):
    id: str
    employee_id: str
    type: PunchType
    at: datetime

    _tz = field_validator("at")(_require_offset)


class Shift(BaseModel):
    id: str
    employee_id: str
    start: datetime
    end: datetime
    scheduled_break_minutes: int = 0

    _tz_start = field_validator("start")(_require_offset)
    _tz_end = field_validator("end")(_require_offset)


class Leave(BaseModel):
    id: str
    employee_id: str
    start: datetime
    end: datetime
    kind: str = "PAID"  # PAID, UNPAID, SICK ...

    _tz_start = field_validator("start")(_require_offset)
    _tz_end = field_validator("end")(_require_offset)


class Timecard(BaseModel):
    id: str
    employee_id: str
    # Free string such as "CA" or "KA" matching a policy pack. Not an enum, so a
    # new pack needs no code change and an unknown value reaches detect()/agent
    # (the "unknown jurisdiction" adversarial case) instead of failing at parse.
    jurisdiction: str
    period_start: date
    period_end: date
    locked: bool = False  # a locked pay period can never be changed
    shifts: list[Shift] = Field(default_factory=list)
    punches: list[Punch] = Field(default_factory=list)
    leaves: list[Leave] = Field(default_factory=list)
    # Free-text notes from the employee. UNTRUSTED: treat as data, never as
    # instructions (prompt-injection defence).
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Policy packs (loaded from versioned YAML in data/policies/)
# --------------------------------------------------------------------------
class PolicyClause(BaseModel):
    id: str  # e.g. "CA-OT-DAILY-01"
    title: str
    text: str
    # Numeric parameters the rules read, e.g. {"daily_ot_after_hours": 8}
    params: dict[str, float] = Field(default_factory=dict)


class PolicyPack(BaseModel):
    jurisdiction: str
    version: str
    disclaimer: str = "Illustrative mock values, not legal advice."
    clauses: list[PolicyClause]


# --------------------------------------------------------------------------
# Exceptions found by detect()
# --------------------------------------------------------------------------
class ExceptionRecord(BaseModel):
    id: str  # e.g. "exc_0142"
    type: ExceptionType
    employee_id: str
    timecard_id: str
    work_date: date
    detail: str  # human-readable description of what is wrong
    policy_clauses: list[str] = Field(default_factory=list)
    status: ExceptionStatus = ExceptionStatus.OPEN
    risk: Optional[RiskTier] = None


# --------------------------------------------------------------------------
# The Proposal: the single object that travels from model -> validator ->
# database -> screen.
# --------------------------------------------------------------------------
class EvidenceRef(BaseModel):
    kind: Literal["punch", "shift", "leave", "history"]
    id: str


class Change(BaseModel):
    op: Literal["add_punch", "adjust_punch", "insert_break"]
    type: Optional[PunchType] = None  # for add_punch
    at: Optional[datetime] = None  # new time for add/adjust
    punch_id: Optional[str] = None  # for adjust_punch
    break_start: Optional[datetime] = None  # for insert_break
    break_end: Optional[datetime] = None  # for insert_break


class Proposal(BaseModel):
    exception_id: str
    action: ProposalAction
    changes: list[Change] = Field(default_factory=list)
    rationale: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    policy_clauses: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_employee_confirmation: bool = False


# --------------------------------------------------------------------------
# Validation, pay impact, resolution
# --------------------------------------------------------------------------
class PayImpact(BaseModel):
    regular_minutes_delta: int = 0
    overtime_minutes_delta: int = 0
    estimated_cost_delta: float = 0.0
    currency: str = "INR"


class CheckResult(BaseModel):
    name: str  # e.g. "target_exception_cleared"
    passed: bool
    detail: str = ""


class ValidationResult(BaseModel):
    passed: bool
    checks: list[CheckResult]
    pay_impact: Optional[PayImpact] = None


class ResolutionResult(BaseModel):
    proposal: Proposal
    validation: ValidationResult
    attempts: int  # 1 = first try passed, 2 = after one repair
    used_fallback: bool  # True if the safe deterministic default was used
    trace_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)