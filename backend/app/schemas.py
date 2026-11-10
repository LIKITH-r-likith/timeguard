"""API-level Pydantic schemas mirroring contracts/openapi.yaml."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

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
