"""API-level Pydantic schemas mirroring contracts/openapi.yaml."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.core.models import (
    ErrorResponse,
    ExceptionRecord,
    ExceptionStatus,
    ExceptionType,
    PolicyClause,
    Proposal,
    PunchType,
    ResolutionResult,
    RiskTier,
    Role,
    Timecard,
    ValidationResult,
)


class ScanRequest(BaseModel):
    period_start: date
    period_end: date


class ScanResponse(BaseModel):
    found: int
    exceptions: list[ExceptionRecord]


class DecisionRequest(BaseModel):
    comment: Optional[str] = None


ProposalStatus = Literal[
    "PENDING_CONFIRMATION",
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
]


class ProposalRecord(BaseModel):
    id: str
    exception_id: str
    status: ProposalStatus
    risk: RiskTier
    resolution: ResolutionResult
    confirmed_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_comment: Optional[str] = None
    model: Optional[str] = None


class ExceptionDetail(BaseModel):
    exception: ExceptionRecord
    timecard: Timecard
    policy_clauses: list[PolicyClause]
    proposal: Optional[ProposalRecord] = None


class AuditEntry(BaseModel):
    seq: int
    at: datetime
    actor: str
    role: Role
    action: str
    entity_type: str
    entity_id: str
    payload: Optional[dict[str, Any]] = Field(default_factory=dict)
    prev_hash: str
    hash: str


class AuditVerifyResult(BaseModel):
    valid: bool
    entries_checked: int
    first_bad_seq: Optional[int] = None


class RunStep(BaseModel):
    kind: str
    at: datetime
    name: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None
    latency_ms: Optional[int] = None


class RunTrace(BaseModel):
    trace_id: str
    exception_id: str
    prompt_version: Optional[str] = "v1"
    model: Optional[str] = None
    steps: list[RunStep] = Field(default_factory=list)


class Metrics(BaseModel):
    exceptions_found: int = 0
    validator_first_pass_rate: float = 0.0
    validator_pass_after_repair_rate: float = 0.0
    repair_rate: float = 0.0
    fallback_rate: float = 0.0
    avg_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class EvalReport(BaseModel):
    generated_at: Optional[datetime] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    replay_mode: Optional[bool] = None
    detection_recall: Optional[float] = None
    detection_precision: Optional[float] = None
    first_attempt_pass_rate: Optional[float] = None
    pass_rate_after_repair: Optional[float] = None
    correct_action_rate: Optional[float] = None
    hallucinated_evidence_rate: Optional[float] = None
    escalation_correctness: Optional[float] = None
    injection_resistance: Optional[float] = None
    denominators: Optional[dict[str, str]] = None
    ablation: Optional[dict[str, Any]] = None


# ---------------- Sandbox Scenarios ----------------
class ScenarioPunchInput(BaseModel):
    id: Optional[str] = None
    type: PunchType
    at: datetime

    @field_validator("at")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone offset (e.g. +05:30, Z)")
        return v


class ScenarioShiftInput(BaseModel):
    id: Optional[str] = None
    start: datetime
    end: datetime
    scheduled_break_minutes: int = 0

    @field_validator("start", "end")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone offset (e.g. +05:30, Z)")
        return v


class ScenarioLeaveInput(BaseModel):
    id: Optional[str] = None
    start: datetime
    end: datetime
    kind: str = "PAID"

    @field_validator("start", "end")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone offset (e.g. +05:30, Z)")
        return v


class ScenarioTimecardInput(BaseModel):
    id: Optional[str] = None
    employee_id: Optional[str] = None
    jurisdiction: str
    period_start: date
    period_end: date
    locked: bool = False
    shifts: list[ScenarioShiftInput] = Field(default_factory=list)
    punches: list[ScenarioPunchInput] = Field(default_factory=list, max_length=20)
    notes: list[str] = Field(default_factory=list)
    leaves: list[ScenarioLeaveInput] = Field(default_factory=list)

    @field_validator("notes")
    @classmethod
    def check_notes(cls, v: list[str]) -> list[str]:
        for n in v:
            if len(n) > 500:
                raise ValueError("Employee note must not exceed 500 characters")
        return v


class ScenarioRequest(BaseModel):
    case_id: Optional[str] = None
    description: Optional[str] = None
    timecard: Optional[ScenarioTimecardInput] = None
    employee_id: Optional[str] = None
    jurisdiction: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    locked: Optional[bool] = None
    shifts: Optional[list[ScenarioShiftInput]] = None
    punches: Optional[list[ScenarioPunchInput]] = Field(default=None, max_length=20)
    notes: Optional[list[str]] = None

    @field_validator("notes")
    @classmethod
    def check_notes(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            for n in v:
                if len(n) > 500:
                    raise ValueError("Employee note must not exceed 500 characters")
        return v


class ScenarioResponse(BaseModel):
    timecard_id: str
    employee_id: str
    exceptions_detected: int
    exception_ids: list[str]
