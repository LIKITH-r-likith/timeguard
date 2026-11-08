"""Audit log integrity and tamper detection tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import AuditLogModel


def test_audit_verify_detects_tampered_payload(client: TestClient, db_session):
    # Perform several actions to populate audit log
    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    exc_id = list_resp[0]["id"]
    client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"})

    # Verify chain is initially valid
    initial_verify = client.get("/audit/verify", headers={"X-Role": "MANAGER"}).json()
    assert initial_verify["valid"] is True
    assert initial_verify["entries_checked"] >= 2
    assert initial_verify["first_bad_seq"] is None

    # Tamper with row 2 in the database directly
    row = db_session.execute(select(AuditLogModel).where(AuditLogModel.seq == 2)).scalar_one()
    tampered_seq = row.seq
    row.action = "TAMPERED_ACTION"
    db_session.commit()

    # Verify detects the tampering immediately at row 2
    tampered_verify = client.get("/audit/verify", headers={"X-Role": "MANAGER"}).json()
    assert tampered_verify["valid"] is False
    assert tampered_verify["first_bad_seq"] == tampered_seq


def test_audit_verify_detects_tampered_prev_hash(client: TestClient, db_session):
    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    client.post(f"/exceptions/{list_resp[0]['id']}/resolve", headers={"X-Role": "MANAGER"})

    # Tamper with prev_hash of row 2
    row = db_session.execute(select(AuditLogModel).where(AuditLogModel.seq == 2)).scalar_one()
    row.prev_hash = "f" * 64
    db_session.commit()

    tampered_verify = client.get("/audit/verify", headers={"X-Role": "MANAGER"}).json()
    assert tampered_verify["valid"] is False
    assert tampered_verify["first_bad_seq"] == 2
