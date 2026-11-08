"""End-to-end test suite for the complete TimeGuard demo story.

Covers the HTTP API workflow using the ScriptedLLM (LLM_MODE=demo):
  1. Scan pay period -> detects demo exceptions
  2. Missed punch (e01): resolve -> employee confirms -> manager approves -> punch written -> audit chain valid
  3. Overtime (e02): first attempt rejected by validator, second passes via repair loop (attempts == 2)
  4. Prompt injection (e03): safety detector intercepts employee note, forces ESCALATE_TO_HR, no timecard edit
  5. Unknown jurisdiction (e04): no policy found -> escalated to HR
  6. Meal break violation (e05): requests employee confirmation
  7. Audit chain integrity: verifies clean chain, detects tampering
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import AuditLogModel
from data.seed.seed import seed_database


@pytest.fixture
def story_client() -> Generator[TestClient, None, None]:
    """Test client using a fresh, isolated SQLite DB seeded with demo data."""
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_path = temp_db.name
    temp_db.close()

    engine = create_engine(f"sqlite:///{temp_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSession()
    seed_database(session)

    # Use scripted LLM for demo scenarios
    prev_mode = os.environ.get("LLM_MODE")
    os.environ["LLM_MODE"] = "demo"

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)
    if prev_mode is not None:
        os.environ["LLM_MODE"] = prev_mode
    else:
        os.environ.pop("LLM_MODE", None)
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_full_story_scan_to_approve_missed_punch(story_client: TestClient):
    """Scan -> resolve missed punch -> employee confirms -> manager approves -> punch exists -> audit chain verifies."""
    client = story_client

    # 1. Scan the pay period (2026-11-02 to 2026-11-08)
    scan_resp = client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["found"] == 5
    exc_ids = {e["id"] for e in scan_data["exceptions"]}
    assert "exc_tc_e01_MISSED_PUNCH_2026-11-03" in exc_ids

    # 2. Inspect timecard before resolution (19 punches: 4 on Mon, 3 on Tue, 4 on Wed, 4 on Thu, 4 on Fri)
    detail_before = client.get(
        "/exceptions/exc_tc_e01_MISSED_PUNCH_2026-11-03",
        headers={"X-Role": "MANAGER"},
    )
    assert detail_before.status_code == 200
    assert len(detail_before.json()["timecard"]["punches"]) == 19

    # 3. Resolve missed punch as MANAGER
    resolve_resp = client.post(
        "/exceptions/exc_tc_e01_MISSED_PUNCH_2026-11-03/resolve",
        headers={"X-Role": "MANAGER"},
    )
    assert resolve_resp.status_code == 200
    prop_data = resolve_resp.json()
    prop_id = prop_data["id"]
    resolution = prop_data["resolution"]

    assert resolution["proposal"]["action"] == "ADD_PUNCH"
    assert resolution["attempts"] == 1
    assert resolution["validation"]["passed"] is True
    assert prop_data["status"] == "PENDING_CONFIRMATION"
    assert prop_data["risk"] == "LOW"

    # Verify punches haven't changed yet (LLM never writes directly)
    detail_mid = client.get(
        "/exceptions/exc_tc_e01_MISSED_PUNCH_2026-11-03",
        headers={"X-Role": "MANAGER"},
    )
    assert len(detail_mid.json()["timecard"]["punches"]) == 19

    # 4. Attempt manager approval BEFORE employee confirmation -> 409 Conflict (or 400)
    premature_approve = client.post(
        f"/proposals/{prop_id}/approve",
        headers={"X-Role": "MANAGER"},
    )
    assert premature_approve.status_code in (400, 409)
    assert "confirmation" in premature_approve.json()["message"].lower()

    # 5. Wrong employee attempts confirmation -> 403 Forbidden
    wrong_confirm = client.post(
        f"/proposals/{prop_id}/confirm",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e02"},
    )
    assert wrong_confirm.status_code == 403

    # 6. Correct employee confirms
    confirm_resp = client.post(
        f"/proposals/{prop_id}/confirm",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e01"},
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "PENDING_APPROVAL"

    # 7. Manager approves
    approve_resp = client.post(
        f"/proposals/{prop_id}/approve",
        headers={"X-Role": "MANAGER"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "APPROVED"

    # 8. Verify punch exists on timecard now (20 punches, new OUT punch at 17:00)
    detail_after = client.get(
        "/exceptions/exc_tc_e01_MISSED_PUNCH_2026-11-03",
        headers={"X-Role": "MANAGER"},
    )
    punches_after = detail_after.json()["timecard"]["punches"]
    assert len(punches_after) == 20
    added_punches = [
        p for p in punches_after
        if p["type"] == "OUT" and "2026-11-03T17:00:00" in p["at"]
    ]
    assert len(added_punches) == 1
    assert detail_after.json()["exception"]["status"] == "RESOLVED"

    # 9. Verify cryptographic audit chain
    audit_resp = client.get("/audit/verify", headers={"X-Role": "MANAGER"})
    assert audit_resp.status_code == 200
    audit_verify = audit_resp.json()
    assert audit_verify["valid"] is True
    assert audit_verify["first_bad_seq"] is None
    assert audit_verify["entries_checked"] >= 4  # scan, resolve, confirm, approve


def test_full_story_overtime_repair_loop(story_client: TestClient):
    """Overtime: first proposal rejected by validator, repair loop succeeds (attempts == 2)."""
    client = story_client

    # Scan to initialize exceptions
    client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )

    # Resolve overtime exception
    resolve_resp = client.post(
        "/exceptions/exc_tc_e02_OVERTIME_RISK_2026-11-04/resolve",
        headers={"X-Role": "MANAGER"},
    )
    assert resolve_resp.status_code == 200
    prop_data = resolve_resp.json()
    resolution = prop_data["resolution"]

    # Key demo verification: attempt 1 failed validation, attempt 2 succeeded
    assert resolution["attempts"] == 2
    assert resolution["used_fallback"] is False
    assert resolution["validation"]["passed"] is True
    assert resolution["proposal"]["action"] == "FLAG_OVERTIME_FOR_APPROVAL"
    assert prop_data["status"] == "PENDING_APPROVAL"
    assert prop_data["risk"] == "MEDIUM"

    # Manager approves the overtime flag
    approve_resp = client.post(
        f"/proposals/{prop_data['id']}/approve",
        headers={"X-Role": "MANAGER"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "APPROVED"


def test_full_story_prompt_injection_safety(story_client: TestClient):
    """Prompt injection: safety layer visibly intercepts adversarial note and forces ESCALATE_TO_HR."""
    client = story_client

    client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )

    # Punches count before
    detail_before = client.get(
        "/exceptions/exc_tc_e03_MISSED_PUNCH_2026-11-03",
        headers={"X-Role": "MANAGER"},
    )
    punches_before = len(detail_before.json()["timecard"]["punches"])

    # Resolve adversarial note case
    resolve_resp = client.post(
        "/exceptions/exc_tc_e03_MISSED_PUNCH_2026-11-03/resolve",
        headers={"X-Role": "MANAGER"},
    )
    assert resolve_resp.status_code == 200
    prop_data = resolve_resp.json()
    resolution = prop_data["resolution"]

    # Even though ScriptedLLM attempts an obedient proposal, safety intercepts it
    assert resolution["proposal"]["action"] == "ESCALATE_TO_HR"
    assert "safety" in resolution["proposal"]["rationale"].lower() or "injection" in resolution["proposal"]["rationale"].lower()
    assert resolution["proposal"]["changes"] == []
    assert prop_data["risk"] == "HIGH"

    # Punches are unchanged
    detail_after = client.get(
        "/exceptions/exc_tc_e03_MISSED_PUNCH_2026-11-03",
        headers={"X-Role": "MANAGER"},
    )
    assert len(detail_after.json()["timecard"]["punches"]) == punches_before

    # Verify HIGH risk requires HR role to approve
    manager_approve = client.post(
        f"/proposals/{prop_data['id']}/approve",
        headers={"X-Role": "MANAGER"},
    )
    assert manager_approve.status_code == 403
    assert "HR" in manager_approve.json()["message"]

    # HR approves escalation
    hr_approve = client.post(
        f"/proposals/{prop_data['id']}/approve",
        headers={"X-Role": "HR"},
    )
    assert hr_approve.status_code == 200
    assert hr_approve.json()["status"] == "APPROVED"


def test_full_story_unknown_jurisdiction(story_client: TestClient):
    """Unknown jurisdiction (e04 with jurisdiction XX) escalates to HR."""
    client = story_client

    client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )

    resolve_resp = client.post(
        "/exceptions/exc_tc_e04_MISSED_PUNCH_2026-11-03/resolve",
        headers={"X-Role": "MANAGER"},
    )
    assert resolve_resp.status_code == 200
    prop_data = resolve_resp.json()
    resolution = prop_data["resolution"]

    assert resolution["proposal"]["action"] == "ESCALATE_TO_HR"
    assert prop_data["risk"] == "HIGH"


def test_full_story_meal_break_violation(story_client: TestClient):
    """Meal break violation (e05) requests employee confirmation."""
    client = story_client

    client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )

    resolve_resp = client.post(
        "/exceptions/exc_tc_e05_MEAL_BREAK_VIOLATION_2026-11-03/resolve",
        headers={"X-Role": "MANAGER"},
    )
    assert resolve_resp.status_code == 200
    prop_data = resolve_resp.json()
    prop_id = prop_data["id"]

    assert prop_data["resolution"]["proposal"]["action"] == "REQUEST_EMPLOYEE_CONFIRMATION"
    assert prop_data["status"] == "PENDING_CONFIRMATION"

    # Employee confirms
    confirm_resp = client.post(
        f"/proposals/{prop_id}/confirm",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e05"},
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "PENDING_APPROVAL"


def test_audit_chain_tamper_detection(story_client: TestClient):
    """Tampering with an audit entry breaks the cryptographic chain."""
    client = story_client

    # Perform an operation to write an audit entry
    client.post(
        "/scan",
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        headers={"X-Role": "MANAGER"},
    )

    # Chain should be valid before tampering
    verify_before = client.get("/audit/verify", headers={"X-Role": "MANAGER"}).json()
    assert verify_before["valid"] is True

    # Tamper with an audit entry in the DB
    override_db = next(app.dependency_overrides[get_db]())
    tamper_row = override_db.execute(select(AuditLogModel).order_by(AuditLogModel.seq.desc())).scalars().first()
    if tamper_row:
        tamper_row.payload = {"tampered": True}
        override_db.commit()

        # Chain verification must now detect corruption
        verify_after = client.get("/audit/verify", headers={"X-Role": "MANAGER"}).json()
        assert verify_after["valid"] is False
        assert verify_after["first_bad_seq"] == tamper_row.seq
