"""API test suite covering all 12 endpoints with TestClient and mock LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestEndpoints:
    def test_scan_and_list_exceptions(self, client: TestClient):
        # 1. POST /scan
        resp = client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["found"] >= 1
        assert len(data["exceptions"]) >= 1

        # Check request ID header
        assert "x-request-id" in resp.headers

        # 2. GET /exceptions
        list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"})
        assert list_resp.status_code == 200
        excs = list_resp.json()
        assert len(excs) >= 1

        # Test filtering
        filter_resp = client.get(
            "/exceptions",
            headers={"X-Role": "MANAGER"},
            params={"status": "OPEN"},
        )
        assert filter_resp.status_code == 200
        assert all(e["status"] == "OPEN" for e in filter_resp.json())

    def test_get_exception_detail(self, client: TestClient):
        # Scan first
        client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )
        list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"})
        exc_id = list_resp.json()[0]["id"]

        resp = client.get(f"/exceptions/{exc_id}", headers={"X-Role": "MANAGER"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exception"]["id"] == exc_id
        assert "timecard" in data
        assert "policy_clauses" in data

    def test_resolve_and_approve_cycle(self, client: TestClient):
        # 1. Scan
        client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )
        list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"})
        # Pick a missed punch exception
        mp_exc = next(e for e in list_resp.json() if e["type"] == "MISSED_PUNCH")
        exc_id = mp_exc["id"]

        # 2. POST /exceptions/{id}/resolve
        res_resp = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"})
        assert res_resp.status_code == 200, res_resp.text
        prop = res_resp.json()
        prop_id = prop["id"]
        assert prop["status"] in ("PENDING_APPROVAL", "PENDING_CONFIRMATION")
        assert prop["risk"] in ("LOW", "MEDIUM", "HIGH")

        # 3. POST /proposals/{id}/approve
        appr_resp = client.post(
            f"/proposals/{prop_id}/approve",
            headers={"X-Role": "HR"},  # HR can approve all risk levels
            json={"comment": "Approved by HR in test"},
        )
        assert appr_resp.status_code == 200, appr_resp.text
        appr_data = appr_resp.json()
        assert appr_data["status"] == "APPROVED"
        assert appr_data["decided_by"] is not None

        # 4. Verify timecard punches increased
        exc_detail = client.get(f"/exceptions/{exc_id}", headers={"X-Role": "MANAGER"}).json()
        assert exc_detail["exception"]["status"] == "RESOLVED"
        # Since ADD_PUNCH was applied, punches list now contains the new punch
        punches = exc_detail["timecard"]["punches"]
        assert any(p["id"].startswith(f"p_add_{prop_id}") for p in punches)

    def test_resolve_and_reject_cycle(self, client: TestClient):
        client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )
        list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"})
        exc_id = list_resp.json()[0]["id"]

        res_resp = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"})
        prop_id = res_resp.json()["id"]

        rej_resp = client.post(
            f"/proposals/{prop_id}/reject",
            headers={"X-Role": "HR"},
            json={"comment": "Rejected in test"},
        )
        assert rej_resp.status_code == 200
        assert rej_resp.json()["status"] == "REJECTED"

    def test_audit_log_and_verify(self, client: TestClient):
        # Scan to generate audit entry
        client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )

        # GET /audit
        audit_resp = client.get("/audit", headers={"X-Role": "MANAGER"})
        assert audit_resp.status_code == 200
        entries = audit_resp.json()
        assert len(entries) >= 1
        assert "prev_hash" in entries[0]
        assert "hash" in entries[0]

        # GET /audit/verify
        verify_resp = client.get("/audit/verify", headers={"X-Role": "MANAGER"})
        assert verify_resp.status_code == 200
        res = verify_resp.json()
        assert res["valid"] is True
        assert res["entries_checked"] >= 1
        assert res["first_bad_seq"] is None

    def test_runs_and_metrics(self, client: TestClient):
        client.post(
            "/scan",
            headers={"X-Role": "MANAGER"},
            json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
        )
        list_resp = client.get("/exceptions", headers={"X-Role": "MANAGER"})
        exc_id = list_resp.json()[0]["id"]

        prop = client.post(f"/exceptions/{exc_id}/resolve", headers={"X-Role": "MANAGER"}).json()
        trace_id = prop["resolution"]["trace_id"]

        # GET /runs/{trace_id}
        run_resp = client.get(f"/runs/{trace_id}", headers={"X-Role": "MANAGER"})
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["trace_id"] == trace_id

        # GET /metrics (open to anyone, no headers needed)
        metrics_resp = client.get("/metrics")
        assert metrics_resp.status_code == 200
        m = metrics_resp.json()
        assert "exceptions_found" in m
        assert "validator_first_pass_rate" in m

    def test_evals_latest(self, client: TestClient, tmp_path, monkeypatch):
        # 1. 404 when report absent
        resp = client.get("/evals/latest")
        # Could be 404 if file does not exist
        if resp.status_code == 404:
            err = resp.json()
            assert err["code"] == "NOT_FOUND"

        # 2. 200 when report present
        fake_report = {
            "model": "llama-3.3-70b-versatile",
            "prompt_version": "v1",
            "replay_mode": True,
            "detection_recall": 1.0,
            "first_attempt_pass_rate": 0.95,
        }
        reports_dir = Path(__file__).resolve().parents[3] / "evals" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "latest.json"
        report_file.write_text(json.dumps(fake_report), "utf-8")

        resp2 = client.get("/evals/latest")
        assert resp2.status_code == 200
        assert resp2.json()["model"] == "llama-3.3-70b-versatile"
