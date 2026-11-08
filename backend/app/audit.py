"""Cryptographic append-only audit log with SHA-256 hash chaining."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.models import AuditLogModel

GENESIS_HASH = "0" * 64


def _canonical_json(data: Any) -> str:
    """Produce deterministic JSON string for hashing."""
    if data is None:
        return ""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(
    prev_hash: str,
    seq: int,
    at: str,
    actor: str,
    role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: Any,
) -> str:
    """Compute SHA-256 hash of an audit entry."""
    payload_str = _canonical_json(payload)
    message = f"{prev_hash}|{seq}|{at}|{actor}|{role}|{action}|{entity_type}|{entity_id}|{payload_str}"
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def log_audit(
    session: Session,
    actor: str,
    role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: Optional[dict[str, Any]] = None,
) -> AuditLogModel:
    """Append a new verified entry to the audit log."""
    # Find the latest entry to get its hash and seq
    latest_stmt = select(AuditLogModel).order_by(desc(AuditLogModel.seq)).limit(1)
    latest = session.execute(latest_stmt).scalar_one_or_none()

    prev_hash = latest.hash if latest is not None else GENESIS_HASH
    seq = (latest.seq + 1) if latest is not None else 1
    at = datetime.now(timezone.utc).isoformat()

    entry_hash = compute_hash(
        prev_hash=prev_hash,
        seq=seq,
        at=at,
        actor=actor,
        role=role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )

    entry = AuditLogModel(
        seq=seq,
        at=at,
        actor=actor,
        role=role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        prev_hash=prev_hash,
        hash=entry_hash,
    )
    session.add(entry)
    session.flush()
    return entry


def verify_audit_chain(session: Session) -> dict[str, Any]:
    """Verify the entire audit log hash chain.

    Returns:
        dict matching AuditVerifyResult:
            {"valid": bool, "entries_checked": int, "first_bad_seq": int | None}
    """
    stmt = select(AuditLogModel).order_by(AuditLogModel.seq.asc())
    entries = session.execute(stmt).scalars().all()

    if not entries:
        return {"valid": True, "entries_checked": 0, "first_bad_seq": None}

    expected_prev_hash = GENESIS_HASH
    for i, entry in enumerate(entries):
        # 1. Check prev_hash links to predecessor
        if entry.prev_hash != expected_prev_hash:
            return {
                "valid": False,
                "entries_checked": i,
                "first_bad_seq": entry.seq,
            }

        # 2. Check current row's hash matches content
        recomputed = compute_hash(
            prev_hash=entry.prev_hash,
            seq=entry.seq,
            at=entry.at,
            actor=entry.actor,
            role=entry.role,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
        )
        if entry.hash != recomputed:
            return {
                "valid": False,
                "entries_checked": i,
                "first_bad_seq": entry.seq,
            }

        expected_prev_hash = entry.hash

    return {
        "valid": True,
        "entries_checked": len(entries),
        "first_bad_seq": None,
    }
