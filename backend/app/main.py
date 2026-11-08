"""FastAPI service for TimeGuard manager console."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.audit import log_audit, verify_audit_chain
from backend.app.auth import AuthContext, get_auth_context
from backend.app.context import DbContextProvider
from backend.app.db import get_db, init_db
from backend.app.models import (
    ApprovalModel,
    AuditLogModel,
    ExceptionModel,
    PunchModel,
    ProposalModel,
    RunModel,
    TimecardModel,
)
from backend.app.schemas import (
    AuditEntry,
    AuditVerifyResult,
    DecisionRequest,
    EvalReport,
    ExceptionDetail,
    Metrics,
    ProposalRecord,
    RunStep,
    RunTrace,
    ScanRequest,
    ScanResponse,
)
from backend.app.seed import load_seed_timecards
from backend.core.api import detect, load_policy, pay_impact, risk_tier, validate
from backend.core.contract import ContextProvider
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
)

logger = logging.getLogger("timeguard")
logging.basicConfig(level=logging.INFO, format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize tables and seed initial timecards
    init_db()
    from backend.app.db import SessionLocal
    with SessionLocal() as session:
        load_seed_timecards(session)
    yield


app = FastAPI(
    title="TimeGuard API",
    version="0.1.0",
    description="TimeGuard manager console for timecard exceptions.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Middleware: Request ID and JSON logging
# --------------------------------------------------------------------------
@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = req_id
    t0 = time.monotonic()

    response = await call_next(request)
    duration_ms = int((time.monotonic() - t0) * 1000)
    response.headers["X-Request-Id"] = req_id

    log_entry = {
        "request_id": req_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }
    logger.info(json.dumps(log_entry))
    return response


# --------------------------------------------------------------------------
# Error Handlers matching OpenAPI ErrorResponse {code, message, details}
# --------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        payload = exc.detail
    else:
        payload = {
            "code": "ERROR" if exc.status_code < 500 else "INTERNAL_ERROR",
            "message": str(exc.detail),
            "details": {},
        }
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    payload = {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request parameters or payload",
        "details": {"errors": exc.errors()},
    }
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error")
    payload = {
        "code": "INTERNAL_ERROR",
        "message": "An unexpected error occurred",
        "details": {"error": str(exc)},
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.post(
    "/scan",
    response_model=ScanResponse,
    tags=["detection"],
    summary="Detect exceptions for a pay period",
)
def scan_timecards(
    payload: ScanRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can scan timecards", "details": {}},
        )

    # Find timecards in the pay period
    stmt = select(TimecardModel).where(
        TimecardModel.period_start <= payload.period_end,
        TimecardModel.period_end >= payload.period_start,
    )
    tcs = db.execute(stmt).scalars().all()

    ctx = DbContextProvider(db)
    found_records: list[ExceptionRecord] = []

    for tc_row in tcs:
        tc = ctx.get_timecard(tc_row.id)
        policy = ctx.get_policy_pack(tc.jurisdiction)
        detected = detect(tc, policy)

        for exc in detected:
            found_records.append(exc)
            existing = db.execute(select(ExceptionModel).where(ExceptionModel.id == exc.id)).scalar_one_or_none()
            if not existing:
                db_exc = ExceptionModel(
                    id=exc.id,
                    type=exc.type.value,
                    employee_id=exc.employee_id,
                    timecard_id=exc.timecard_id,
                    work_date=exc.work_date,
                    detail=exc.detail,
                    policy_clauses=exc.policy_clauses,
                    status=ExceptionStatus.OPEN.value,
                    risk=None,  # risk unknown until resolved
                )
                db.add(db_exc)
    db.commit()

    log_audit(
        session=db,
        actor=auth.actor,
        role=auth.role.value,
        action="SCAN_COMPLETED",
        entity_type="scan",
        entity_id=f"{payload.period_start}_{payload.period_end}",
        payload={"found": len(found_records)},
    )
    db.commit()

    return ScanResponse(found=len(found_records), exceptions=found_records)


@app.get(
    "/exceptions",
    response_model=list[ExceptionRecord],
    tags=["detection"],
    summary="Exception queue, filtered by status and risk",
)
def list_exceptions(
    status_filter: Optional[ExceptionStatus] = Query(None, alias="status"),
    risk_filter: Optional[RiskTier] = Query(None, alias="risk"),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can view the exception queue", "details": {}},
        )

    stmt = select(ExceptionModel)
    if status_filter:
        stmt = stmt.where(ExceptionModel.status == status_filter.value)
    if risk_filter:
        stmt = stmt.where(ExceptionModel.risk == risk_filter.value)

    rows = db.execute(stmt).scalars().all()

    # Sort: HIGH, MEDIUM, LOW, None; then work_date
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}
    sorted_rows = sorted(
        rows,
        key=lambda r: (risk_order.get(r.risk, 3), r.work_date),
    )

    return [
        ExceptionRecord(
            id=r.id,
            type=ExceptionType(r.type),
            employee_id=r.employee_id,
            timecard_id=r.timecard_id,
            work_date=r.work_date,
            detail=r.detail,
            policy_clauses=list(r.policy_clauses or []),
            status=ExceptionStatus(r.status),
            risk=RiskTier(r.risk) if r.risk else None,
        )
        for r in sorted_rows
    ]


@app.get(
    "/exceptions/{id}",
    response_model=ExceptionDetail,
    tags=["detection"],
    summary="One exception with its timecard and policy context",
)
def get_exception_detail(
    id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    ctx = DbContextProvider(db)
    try:
        exc = ctx.get_exception(id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Exception {id} not found", "details": {}},
        )

    if auth.role == Role.EMPLOYEE and auth.employee_id != exc.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Employees may only access their own exceptions", "details": {}},
        )

    timecard = ctx.get_timecard(exc.timecard_id)
    policy = ctx.get_policy_pack(timecard.jurisdiction)
    clauses: list[PolicyClause] = []
    if policy:
        wanted = set(exc.policy_clauses)
        clauses = [c for c in policy.clauses if c.id in wanted]

    # Proposal if exists
    prop_stmt = select(ProposalModel).where(ProposalModel.exception_id == id)
    prop_row = db.execute(prop_stmt).scalar_one_or_none()
    prop_record: Optional[ProposalRecord] = None
    if prop_row:
        prop_record = ProposalRecord(
            id=prop_row.id,
            exception_id=prop_row.exception_id,
            status=prop_row.status,
            risk=RiskTier(prop_row.risk),
            resolution=ResolutionResult.model_validate(prop_row.resolution),
            confirmed_at=datetime.fromisoformat(prop_row.confirmed_at) if prop_row.confirmed_at else None,
            decided_by=prop_row.decided_by,
            decided_at=datetime.fromisoformat(prop_row.decided_at) if prop_row.decided_at else None,
            decision_comment=prop_row.decision_comment,
        )

    return ExceptionDetail(
        exception=exc,
        timecard=timecard,
        policy_clauses=clauses,
        proposal=prop_record,
    )


@app.post(
    "/exceptions/{id}/resolve",
    response_model=ProposalRecord,
    tags=["proposals"],
    summary="Run the agent on an exception",
)
def resolve_exception(
    id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can resolve exceptions", "details": {}},
        )

    ctx = DbContextProvider(db)
    try:
        exc = ctx.get_exception(id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Exception {id} not found", "details": {}},
        )

    # Check if a proposal already exists
    existing = db.execute(select(ProposalModel).where(ProposalModel.exception_id == id)).scalar_one_or_none()
    if existing and existing.status == "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Exception already resolved and approved", "details": {}},
        )

    from backend.agent.api import resolve as agent_resolve
    from backend.agent.trace import get_trace

    res = agent_resolve(id, ctx)
    timecard = ctx.get_timecard(exc.timecard_id)
    policy = ctx.get_policy_pack(timecard.jurisdiction)

    # Compute risk tier
    computed_risk = risk_tier(exc, res.proposal, res.validation.pay_impact)

    # Determine proposal status and exception status
    if res.proposal.action == "ESCALATE_TO_HR":
        prop_status = "PENDING_APPROVAL"
        exc_status = ExceptionStatus.ESCALATED
        computed_risk = RiskTier.HIGH
    elif res.proposal.needs_employee_confirmation:
        prop_status = "PENDING_CONFIRMATION"
        exc_status = ExceptionStatus.AWAITING_EMPLOYEE
    else:
        prop_status = "PENDING_APPROVAL"
        exc_status = ExceptionStatus.AWAITING_APPROVAL

    # Update ExceptionModel in DB
    exc_row = db.execute(select(ExceptionModel).where(ExceptionModel.id == id)).scalar_one()
    exc_row.status = exc_status.value
    exc_row.risk = computed_risk.value

    prop_id = existing.id if existing else f"prop_{uuid.uuid4().hex[:8]}"
    if existing:
        existing.status = prop_status
        existing.risk = computed_risk.value
        existing.resolution = res.model_dump(mode="json")
    else:
        prop_row = ProposalModel(
            id=prop_id,
            exception_id=id,
            status=prop_status,
            risk=computed_risk.value,
            resolution=res.model_dump(mode="json"),
        )
        db.add(prop_row)

    # Save run trace
    trace = get_trace(res.trace_id)
    steps_data = []
    if trace:
        steps_data = [
            {
                "kind": s.kind,
                "at": s.timestamp,
                "name": s.data.get("name"),
                "input": s.data.get("arguments"),
                "output": s.data,
                "latency_ms": s.data.get("latency_ms"),
            }
            for s in trace.steps
        ]

    db.add(RunModel(
        trace_id=res.trace_id,
        exception_id=id,
        prompt_version="v1",
        steps=steps_data,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))

    log_audit(
        session=db,
        actor=auth.actor,
        role=auth.role.value,
        action="PROPOSAL_GENERATED",
        entity_type="proposal",
        entity_id=prop_id,
        payload={"exception_id": id, "action": res.proposal.action.value, "risk": computed_risk.value},
    )
    db.commit()

    return ProposalRecord(
        id=prop_id,
        exception_id=id,
        status=prop_status,
        risk=computed_risk,
        resolution=res,
    )


@app.post(
    "/proposals/{id}/confirm",
    response_model=ProposalRecord,
    tags=["proposals"],
    summary="Employee confirms a proposed punch",
)
def confirm_proposal(
    id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role != Role.EMPLOYEE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only EMPLOYEE can confirm a proposal", "details": {}},
        )

    stmt = select(ProposalModel).where(ProposalModel.id == id)
    prop = db.execute(stmt).scalar_one_or_none()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Proposal {id} not found", "details": {}},
        )

    exc = db.execute(select(ExceptionModel).where(ExceptionModel.id == prop.exception_id)).scalar_one()
    if exc.employee_id != auth.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Employees can only confirm their own proposals", "details": {}},
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    prop.confirmed_at = now_iso
    prop.status = "PENDING_APPROVAL"
    exc.status = ExceptionStatus.AWAITING_APPROVAL.value

    log_audit(
        session=db,
        actor=auth.actor,
        role=auth.role.value,
        action="PROPOSAL_CONFIRMED",
        entity_type="proposal",
        entity_id=id,
        payload={"employee_id": auth.employee_id},
    )
    db.commit()

    return ProposalRecord(
        id=prop.id,
        exception_id=prop.exception_id,
        status=prop.status,
        risk=RiskTier(prop.risk),
        resolution=ResolutionResult.model_validate(prop.resolution),
        confirmed_at=datetime.fromisoformat(now_iso),
    )


@app.post(
    "/proposals/{id}/approve",
    response_model=ProposalRecord,
    tags=["proposals"],
    summary="Approve a proposal (the only write to a timecard)",
)
def approve_proposal(
    id: str,
    payload: Optional[DecisionRequest] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    stmt = select(ProposalModel).where(ProposalModel.id == id)
    prop = db.execute(stmt).scalar_one_or_none()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Proposal {id} not found", "details": {}},
        )

    # Risk authorization check
    if prop.risk == RiskTier.HIGH.value and auth.role != Role.HR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "HIGH risk proposals require HR approval", "details": {}},
        )
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can approve proposals", "details": {}},
        )

    exc = db.execute(select(ExceptionModel).where(ExceptionModel.id == prop.exception_id)).scalar_one()
    ctx = DbContextProvider(db)
    timecard = ctx.get_timecard(exc.timecard_id)
    policy = ctx.get_policy_pack(timecard.jurisdiction)

    if timecard.locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "The pay period is locked; timecards cannot be changed", "details": {}},
        )

    if prop.status == "PENDING_CONFIRMATION":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Proposal requires employee confirmation before approval", "details": {}},
        )
    if prop.status in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": f"Proposal is already {prop.status}", "details": {}},
        )

    # RE-RUN VALIDATE() RIGHT BEFORE WRITING
    res_data = prop.resolution
    proposal = Proposal.model_validate(res_data["proposal"])
    vr = validate(proposal, timecard, policy)
    if not vr.passed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Validation failed prior to timecard write", "details": {"checks": [c.model_dump() for c in vr.checks]}},
        )

    # THE ONLY CODE PATH THAT WRITES PUNCHES TO TIMECARD
    n = 0
    for ch in proposal.changes:
        if ch.op == "add_punch":
            n += 1
            new_id = f"p_add_{prop.id}_{n}"
            db.add(PunchModel(
                id=new_id,
                timecard_id=timecard.id,
                employee_id=timecard.employee_id,
                type=ch.type.value if ch.type else PunchType.OUT.value,
                at=ch.at.isoformat(),
            ))
        elif ch.op == "adjust_punch":
            stmt_p = select(PunchModel).where(PunchModel.id == ch.punch_id)
            punch = db.execute(stmt_p).scalar_one_or_none()
            if punch:
                punch.at = ch.at.isoformat()
        elif ch.op == "insert_break":
            n += 1
            db.add(PunchModel(
                id=f"p_brk_{prop.id}_{n}a",
                timecard_id=timecard.id,
                employee_id=timecard.employee_id,
                type=PunchType.BREAK_START.value,
                at=ch.break_start.isoformat(),
            ))
            db.add(PunchModel(
                id=f"p_brk_{prop.id}_{n}b",
                timecard_id=timecard.id,
                employee_id=timecard.employee_id,
                type=PunchType.BREAK_END.value,
                at=ch.break_end.isoformat(),
            ))

    now_iso = datetime.now(timezone.utc).isoformat()
    comment = payload.comment if payload else None

    prop.status = "APPROVED"
    prop.decided_by = auth.actor
    prop.decided_at = now_iso
    prop.decision_comment = comment

    exc.status = ExceptionStatus.RESOLVED.value

    db.add(ApprovalModel(
        id=f"appr_{uuid.uuid4().hex[:8]}",
        proposal_id=prop.id,
        decider_id=auth.actor,
        decider_role=auth.role.value,
        action="APPROVED",
        at=now_iso,
        comment=comment,
    ))

    log_audit(
        session=db,
        actor=auth.actor,
        role=auth.role.value,
        action="PROPOSAL_APPROVED",
        entity_type="proposal",
        entity_id=id,
        payload={"comment": comment, "changes": [c.model_dump(mode="json") for c in proposal.changes]},
    )
    db.commit()

    return ProposalRecord(
        id=prop.id,
        exception_id=prop.exception_id,
        status=prop.status,
        risk=RiskTier(prop.risk),
        resolution=ResolutionResult.model_validate(prop.resolution),
        confirmed_at=datetime.fromisoformat(prop.confirmed_at) if prop.confirmed_at else None,
        decided_by=prop.decided_by,
        decided_at=datetime.fromisoformat(now_iso),
        decision_comment=comment,
    )


@app.post(
    "/proposals/{id}/reject",
    response_model=ProposalRecord,
    tags=["proposals"],
    summary="Reject a proposal",
)
def reject_proposal(
    id: str,
    payload: Optional[DecisionRequest] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    stmt = select(ProposalModel).where(ProposalModel.id == id)
    prop = db.execute(stmt).scalar_one_or_none()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Proposal {id} not found", "details": {}},
        )

    if prop.risk == RiskTier.HIGH.value and auth.role != Role.HR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "HIGH risk proposals require HR action", "details": {}},
        )
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can reject proposals", "details": {}},
        )

    exc = db.execute(select(ExceptionModel).where(ExceptionModel.id == prop.exception_id)).scalar_one()

    now_iso = datetime.now(timezone.utc).isoformat()
    comment = payload.comment if payload else None

    prop.status = "REJECTED"
    prop.decided_by = auth.actor
    prop.decided_at = now_iso
    prop.decision_comment = comment

    exc.status = ExceptionStatus.REJECTED.value

    db.add(ApprovalModel(
        id=f"appr_{uuid.uuid4().hex[:8]}",
        proposal_id=prop.id,
        decider_id=auth.actor,
        decider_role=auth.role.value,
        action="REJECTED",
        at=now_iso,
        comment=comment,
    ))

    # Timecard is UNCHANGED
    log_audit(
        session=db,
        actor=auth.actor,
        role=auth.role.value,
        action="PROPOSAL_REJECTED",
        entity_type="proposal",
        entity_id=id,
        payload={"comment": comment},
    )
    db.commit()

    return ProposalRecord(
        id=prop.id,
        exception_id=prop.exception_id,
        status=prop.status,
        risk=RiskTier(prop.risk),
        resolution=ResolutionResult.model_validate(prop.resolution),
        confirmed_at=datetime.fromisoformat(prop.confirmed_at) if prop.confirmed_at else None,
        decided_by=prop.decided_by,
        decided_at=datetime.fromisoformat(now_iso),
        decision_comment=comment,
    )


@app.get(
    "/audit",
    response_model=list[AuditEntry],
    tags=["audit"],
    summary="Append-only audit log",
)
def list_audit(
    entity_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can view the audit log", "details": {}},
        )

    stmt = select(AuditLogModel).order_by(AuditLogModel.seq.asc())
    if entity_id:
        stmt = stmt.where(AuditLogModel.entity_id == entity_id)

    rows = db.execute(stmt).scalars().all()
    return [
        AuditEntry(
            seq=r.seq,
            at=datetime.fromisoformat(r.at),
            actor=r.actor,
            role=Role(r.role),
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            payload=r.payload,
            prev_hash=r.prev_hash,
            hash=r.hash,
        )
        for r in rows
    ]


@app.get(
    "/audit/verify",
    response_model=AuditVerifyResult,
    tags=["audit"],
    summary="Verify the audit hash chain",
)
def verify_audit(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can verify the audit chain", "details": {}},
        )

    res = verify_audit_chain(db)
    return AuditVerifyResult(**res)


@app.get(
    "/runs/{trace_id}",
    response_model=RunTrace,
    tags=["observability"],
    summary="Full trace of one agent run",
)
def get_run_trace(
    trace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if auth.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only MANAGER or HR can view agent traces", "details": {}},
        )

    stmt = select(RunModel).where(RunModel.trace_id == trace_id)
    run = db.execute(stmt).scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Trace {trace_id} not found", "details": {}},
        )

    steps = [
        RunStep(
            kind=s["kind"],
            at=datetime.fromisoformat(s["at"]) if isinstance(s.get("at"), str) else datetime.now(timezone.utc),
            name=s.get("name"),
            input=s.get("input"),
            output=s.get("output"),
            latency_ms=s.get("latency_ms"),
        )
        for s in run.steps
    ]

    return RunTrace(
        trace_id=run.trace_id,
        exception_id=run.exception_id,
        prompt_version=run.prompt_version,
        steps=steps,
    )


@app.get(
    "/metrics",
    response_model=Metrics,
    tags=["observability"],
    summary="Operational metrics",
)
def get_metrics(db: Session = Depends(get_db)):
    # Calculate metrics from DB records
    total_exc = db.execute(select(ExceptionModel)).scalars().all()
    total_props = db.execute(select(ProposalModel)).scalars().all()

    first_pass_count = 0
    repair_count = 0
    fallback_count = 0
    latencies = []
    total_in = 0
    total_out = 0

    for p in total_props:
        res = p.resolution or {}
        attempts = res.get("attempts", 1)
        used_fb = res.get("used_fallback", False)
        lat = res.get("latency_ms", 0)
        tin = res.get("input_tokens", 0)
        tout = res.get("output_tokens", 0)

        latencies.append(lat)
        total_in += tin
        total_out += tout

        if attempts == 1 and not used_fb:
            first_pass_count += 1
        elif attempts == 2 and not used_fb:
            repair_count += 1
        if used_fb:
            fallback_count += 1

    n_props = len(total_props) or 1
    return Metrics(
        exceptions_found=len(total_exc),
        validator_first_pass_rate=round(first_pass_count / n_props, 3),
        validator_pass_after_repair_rate=round((first_pass_count + repair_count) / n_props, 3),
        repair_rate=round(repair_count / n_props, 3),
        fallback_rate=round(fallback_count / n_props, 3),
        avg_latency_ms=round(sum(latencies) / n_props, 1) if latencies else 0.0,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
    )


@app.get(
    "/evals/latest",
    response_model=EvalReport,
    tags=["observability"],
    summary="Latest eval report",
)
def get_latest_eval():
    report_path = Path(__file__).resolve().parents[2] / "evals" / "reports" / "latest.json"
    if not report_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "No eval report found in evals/reports/latest.json", "details": {}},
        )

    try:
        data = json.loads(report_path.read_text("utf-8"))
        return EvalReport.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"Failed to read eval report: {exc}", "details": {}},
        )
