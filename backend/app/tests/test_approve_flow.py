"""Tests for proposal approval flow, safety checks, and timecard mutation guarantees."""

from __future__ import annotations

import json
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.agent.llm import LLMResponse, MockLLM
import backend.agent.api as agent_api
from backend.app.models import PunchModel, TimecardModel


def test_only_approve_modifies_punches(client: TestClient, db_session):
    # Count punches before
    init_punches = len(db_session.execute(select(PunchModel)).scalars().all())

    # 1. POST /scan
    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    assert len(db_session.execute(select(PunchModel)).scalars().all()) == init_punches

    # 2. POST /exceptions/{id}/resolve
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    mp_exc = next(e for e in list_resp if e["type"] == "MISSED_PUNCH")
    exc_id = mp_exc["id"]

    res_resp = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"})
    prop = res_resp.json()
    assert len(db_session.execute(select(PunchModel)).scalars().all()) == init_punches

    # 3. POST /proposals/{id}/reject
    client.post(f"/proposals/{prop['id']}/reject", headers={"X-Role": "HR"})
    assert len(db_session.execute(select(PunchModel)).scalars().all()) == init_punches

    # 4. Resolve again and approve
    res_resp2 = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"})
    prop2 = res_resp2.json()
    client.post(f"/proposals/{prop2['id']}/approve", headers={"X-Role": "HR"})

    # NOW punches have changed
    final_punches = len(db_session.execute(select(PunchModel)).scalars().all())
    assert final_punches > init_punches


def test_approve_blocked_on_locked_timecard(client: TestClient, db_session):
    # Scan
    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    exc = list_resp[0]

    # Lock the timecard in DB
    tc = db_session.execute(select(TimecardModel).where(TimecardModel.id == exc["timecard_id"])).scalar_one()
    tc.locked = True
    db_session.commit()

    prop = client.post(f"/exceptions/{exc['id']}/resolve", headers={"X-Role": "MANAGER"}).json()
    appr = client.post(f"/proposals/{prop['id']}/approve", headers={"X-Role": "HR"})
    assert appr.status_code == 409
    assert "locked" in appr.json()["message"].lower()


def test_employee_confirmation_workflow(client: TestClient, monkeypatch):
    # Mock LLM proposal requiring employee confirmation
    orig_resolve = agent_api.resolve

    def mock_needs_confirmation(exception_id, ctx, llm=None):
        exc = ctx.get_exception(exception_id)
        timecard = ctx.get_timecard(exc.timecard_id)
        proposal_dict = {
            "exception_id": exc.id,
            "action": "REQUEST_EMPLOYEE_CONFIRMATION",
            "changes": [],
            "rationale": "Needs confirmation test",
            "evidence": [{"kind": "punch", "id": timecard.punches[0].id}],
            "policy_clauses": [c for c in exc.policy_clauses if "MISS" in c] or ["CA-MISS-01"],
            "confidence": 0.8,
            "needs_employee_confirmation": True,
        }
        return orig_resolve(exception_id, ctx, llm=MockLLM([LLMResponse(text=json.dumps(proposal_dict))]))

    monkeypatch.setattr(agent_api, "resolve", mock_needs_confirmation)

    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    exc = list_resp[0]

    prop = client.post(f"/exceptions/{exc['id']}/resolve", headers={"X-Role": "MANAGER"}).json()
    prop_id = prop["id"]
    assert prop["status"] == "PENDING_CONFIRMATION"

    # Attempting to approve prior to confirmation fails with 409
    appr_fail = client.post(f"/proposals/{prop_id}/approve", headers={"X-Role": "HR"})
    assert appr_fail.status_code == 409
    assert appr_fail.json()["code"] == "CONFLICT"

    # Employee confirms
    conf = client.post(
        f"/proposals/{prop_id}/confirm",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": exc["employee_id"]},
    )
    assert conf.status_code == 200
    assert conf.json()["status"] == "PENDING_APPROVAL"

    # Now approval succeeds
    appr_ok = client.post(f"/proposals/{prop_id}/approve", headers={"X-Role": "HR"})
    assert appr_ok.status_code == 200
    assert appr_ok.json()["status"] == "APPROVED"
