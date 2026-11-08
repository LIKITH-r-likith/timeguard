"""Role-based authorization tests for TimeGuard API."""

from __future__ import annotations

import json
from fastapi.testclient import TestClient

from backend.agent.llm import LLMResponse, MockLLM
import backend.agent.api as agent_api


def test_missing_x_role_header(client: TestClient):
    resp = client.post("/scan", json={"period_start": "2026-11-02", "period_end": "2026-11-08"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_invalid_x_role_header(client: TestClient):
    resp = client.post(
        "/scan",
        headers={"X-Role": "ADMINISTRATOR"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_employee_role_without_id_header(client: TestClient):
    resp = client.get("/exceptions/exc_1", headers={"X-Role": "EMPLOYEE"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_employee_cannot_scan_or_list_queue(client: TestClient):
    resp_scan = client.post(
        "/scan",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e01"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    assert resp_scan.status_code == 403

    resp_list = client.get(
        "/exceptions",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e01"},
    )
    assert resp_list.status_code == 403


def test_employee_can_only_view_own_exception(client: TestClient):
    # Scan as manager
    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    e01_exc = next(e for e in list_resp if e["employee_id"] == "e01")

    # e01 can view own exception
    resp_ok = client.get(
        f"/exceptions/{e01_exc['id']}",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e01"},
    )
    assert resp_ok.status_code == 200

    # e02 cannot view e01's exception
    resp_bad = client.get(
        f"/exceptions/{e01_exc['id']}",
        headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e02"},
    )
    assert resp_bad.status_code == 403
    assert resp_bad.json()["code"] == "FORBIDDEN"


def test_manager_cannot_approve_high_risk(client: TestClient, monkeypatch):
    # Setup mock to return an escalation proposal which is marked HIGH risk
    orig_resolve = agent_api.resolve

    def mock_resolve_high(exception_id, ctx, llm=None):
        exc = ctx.get_exception(exception_id)
        proposal_dict = {
            "exception_id": exc.id,
            "action": "ESCALATE_TO_HR",
            "changes": [],
            "rationale": "High risk test",
            "confidence": 0.2,
        }
        return orig_resolve(exception_id, ctx, llm=MockLLM([LLMResponse(text=json.dumps(proposal_dict))]))

    monkeypatch.setattr(agent_api, "resolve", mock_resolve_high)

    client.post(
        "/scan",
        headers={"X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    exc_id = list_resp[0]["id"]

    prop = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"}).json()
    prop_id = prop["id"]
    assert prop["risk"] == "HIGH"

    # Manager attempts to approve HIGH risk -> 403
    mgr_appr = client.post(
        f"/proposals/{prop_id}/approve",
        headers={"X-Role": "MANAGER"},
        json={"comment": "Manager trying to approve"},
    )
    assert mgr_appr.status_code == 403
    assert mgr_appr.json()["code"] == "FORBIDDEN"

    # HR can approve HIGH risk -> 200
    hr_appr = client.post(
        f"/proposals/{prop_id}/approve",
        headers={"X-Role": "HR"},
        json={"comment": "HR approving"},
    )
    assert hr_appr.status_code == 200


def test_employee_confirmations_endpoint(client: TestClient, monkeypatch):
    """Test GET /employees/{id}/confirmations permissions and data."""
    orig_resolve = agent_api.resolve

    def mock_resolve_need_conf(exception_id, ctx, llm=None):
        exc = ctx.get_exception(exception_id)
        proposal_dict = {
            "exception_id": exc.id,
            "action": "ADD_PUNCH",
            "changes": [{"op": "add_punch", "type": "OUT", "at": "2026-11-03T17:00:00+05:30"}],
            "rationale": "Needs confirmation",
            "evidence": [{"kind": "punch", "id": "p_88"}],
            "policy_clauses": ["CA-MISS-01"],
            "confidence": 0.95,
            "needs_employee_confirmation": True,
        }
        return orig_resolve(exception_id, ctx, llm=MockLLM([LLMResponse(text=json.dumps(proposal_dict))]))

    monkeypatch.setattr(agent_api, "resolve", mock_resolve_need_conf)

    client.post("/scan", headers={"X-Role": "MANAGER"}, json={"period_start": "2026-11-02", "period_end": "2026-11-08"})
    list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"}).json()
    e01_exc = next(e for e in list_resp if e["employee_id"] == "e01")

    # Resolve it so it moves to AWAITING_EMPLOYEE
    client.post(f"/exceptions/{e01_exc['id']}/resolve", headers={"X-Role": "MANAGER"})

    # 1. e01 can view own confirmations
    resp_e01 = client.get("/employees/e01/confirmations", headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e01"})
    assert resp_e01.status_code == 200
    confs = resp_e01.json()
    assert len(confs) >= 1
    assert confs[0]["exception"]["employee_id"] == "e01"
    assert confs[0]["proposal"]["status"] == "PENDING_CONFIRMATION"

    # 2. e02 cannot view e01's confirmations (403)
    resp_e02 = client.get("/employees/e01/confirmations", headers={"X-Role": "EMPLOYEE", "X-Employee-Id": "e02"})
    assert resp_e02.status_code == 403
    assert resp_e02.json()["code"] == "FORBIDDEN"

    # 3. Manager can view e01's confirmations
    resp_mgr = client.get("/employees/e01/confirmations", headers={"X-Role": "MANAGER"})
    assert resp_mgr.status_code == 200

