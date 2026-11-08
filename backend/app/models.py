"""SQLAlchemy 2 database models for TimeGuard."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.core.models import (
    ExceptionStatus,
    ExceptionType,
    ProposalAction,
    PunchType,
    RiskTier,
    Role,
)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    manager_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=Role.EMPLOYEE.value, nullable=False)


class TimecardModel(Base):
    __tablename__ = "timecards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(64), ForeignKey("employees.id"), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    punches: Mapped[list[PunchModel]] = relationship(
        "PunchModel", back_populates="timecard", cascade="all, delete-orphan", order_by="PunchModel.at"
    )
    shifts: Mapped[list[ShiftModel]] = relationship(
        "ShiftModel", back_populates="timecard", cascade="all, delete-orphan", order_by="ShiftModel.start"
    )
    leaves: Mapped[list[LeaveModel]] = relationship(
        "LeaveModel", back_populates="timecard", cascade="all, delete-orphan", order_by="LeaveModel.start"
    )
    exceptions: Mapped[list[ExceptionModel]] = relationship(
        "ExceptionModel", back_populates="timecard", cascade="all, delete-orphan"
    )


class ShiftModel(Base):
    __tablename__ = "shifts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timecard_id: Mapped[str] = mapped_column(String(64), ForeignKey("timecards.id"), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start: Mapped[str] = mapped_column(String(64), nullable=False)  # ISO-8601 with tz
    end: Mapped[str] = mapped_column(String(64), nullable=False)    # ISO-8601 with tz
    scheduled_break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    timecard: Mapped[TimecardModel] = relationship("TimecardModel", back_populates="shifts")


class PunchModel(Base):
    __tablename__ = "punches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timecard_id: Mapped[str] = mapped_column(String(64), ForeignKey("timecards.id"), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # PunchType
    at: Mapped[str] = mapped_column(String(64), nullable=False)    # ISO-8601 with tz

    timecard: Mapped[TimecardModel] = relationship("TimecardModel", back_populates="punches")


class LeaveModel(Base):
    __tablename__ = "leaves"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timecard_id: Mapped[str] = mapped_column(String(64), ForeignKey("timecards.id"), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start: Mapped[str] = mapped_column(String(64), nullable=False)  # ISO-8601 with tz
    end: Mapped[str] = mapped_column(String(64), nullable=False)    # ISO-8601 with tz
    kind: Mapped[str] = mapped_column(String(32), default="PAID", nullable=False)

    timecard: Mapped[TimecardModel] = relationship("TimecardModel", back_populates="leaves")


class ExceptionModel(Base):
    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # ExceptionType
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timecard_id: Mapped[str] = mapped_column(String(64), ForeignKey("timecards.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    policy_clauses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ExceptionStatus.OPEN.value, nullable=False)
    risk: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # RiskTier

    timecard: Mapped[TimecardModel] = relationship("TimecardModel", back_populates="exceptions")
    proposals: Mapped[list[ProposalModel]] = relationship(
        "ProposalModel", back_populates="exception", cascade="all, delete-orphan"
    )


class ProposalModel(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exception_id: Mapped[str] = mapped_column(String(128), ForeignKey("exceptions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # PENDING_CONFIRMATION, PENDING_APPROVAL, etc.
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # Full ResolutionResult dict
    confirmed_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    exception: Mapped[ExceptionModel] = relationship("ExceptionModel", back_populates="proposals")


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(64), ForeignKey("proposals.id"), nullable=False)
    decider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decider_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # APPROVED or REJECTED
    at: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[str] = mapped_column(String(64), nullable=False)  # ISO-8601 with tz
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RunModel(Base):
    __tablename__ = "runs"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exception_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
