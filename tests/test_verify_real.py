"""Tests for 'verify it is real' features: model badges, live-demo checks, and try_case runner."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.agent.demo_script import ScriptedLLM
from backend.agent.llm import GroqClient, MockLLM, ReplayLLM
from backend.agent.loop import get_client_badge
from backend.agent.try_case import load_case_file, run_try_case
from backend.app.main import app
from backend.core.models import Timecard


def test_get_client_badge():
    """Verify badge strings accurately reflect the client type."""
    assert get_client_badge(ScriptedLLM()) == "Scripted demo model"
    assert get_client_badge(MockLLM()) == "Mock model"
    assert get_client_badge(GroqClient(model="openai/gpt-oss-120b")) == "Live model: openai/gpt-oss-120b"
    assert get_client_badge(ReplayLLM(inner=GroqClient(model="llama-3.3-70b-versatile"))) == "Live model: llama-3.3-70b-versatile"


def test_try_example_file_structure():
    """Verify evals/golden/try_example.json is valid and editable."""
    example_path = Path("evals/golden/try_example.json")
    assert example_path.exists(), "evals/golden/try_example.json must exist"

    data = load_case_file(example_path)
    assert "timecard" in data
    assert "case_id" in data
    tc = Timecard.model_validate(data["timecard"])
    assert tc.employee_id == "e01"
    assert tc.jurisdiction == "CA"
    assert len(tc.punches) == 3


def test_run_try_case_mock_mode(capsys):
    """Test try_case execution in offline mock mode prints the required 4 sections."""
    example_path = Path("evals/golden/try_example.json")
    code = run_try_case(example_path, mock=True)
    assert code == 0

    captured = capsys.readouterr().out
    assert "TIMEGUARD TRIAL RUN" in captured
    assert "[1] TOOL CALLS EXECUTED BY AGENT" in captured
    assert "[2] GENERATED PROPOSAL" in captured
    assert "[3] DETERMINISTIC VALIDATOR CHECKS (7 CHECKS)" in captured
    assert "[4] EXECUTION TELEMETRY" in captured
    assert "Client Badge:       Mock model" in captured
    assert "target_exception_cleared" in captured
    assert "period_not_locked" in captured


def test_run_try_case_missing_api_key(monkeypatch):
    """Test that try_case fails cleanly when GROQ_API_KEY is not set."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODE", raising=False)

    example_path = Path("evals/golden/try_example.json")
    code = run_try_case(example_path, mock=False)
    assert code == 1


def test_proposal_and_trace_model_badge():
    """Test that resolving an exception records the model badge on both ProposalRecord and RunTrace."""
    client = TestClient(app)
    # 1. Scan demo period to detect exceptions
    scan_res = client.post(
        "/scan",
        headers={"X-Actor-Id": "m01", "X-Role": "MANAGER"},
        json={"period_start": "2026-11-02", "period_end": "2026-11-08"},
    )
    assert scan_res.status_code == 200

    # 2. Resolve an exception
    exc_id = "exc_tc_e01_MISSED_PUNCH_2026-11-03"
    res = client.post(
        f"/exceptions/{exc_id}/resolve",
        headers={"X-Actor-Id": "m01", "X-Role": "MANAGER"},
    )
    assert res.status_code == 200
    prop_data = res.json()
    assert "model" in prop_data
    assert prop_data["model"] in ("Mock model", "Scripted demo model") or "Live model" in prop_data["model"]

    # 3. Retrieve trace and verify model badge exists
    trace_id = prop_data["resolution"]["trace_id"]
    trace_res = client.get(
        f"/runs/{trace_id}",
        headers={"X-Actor-Id": "m01", "X-Role": "MANAGER"},
    )
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert "model" in trace_data
    assert trace_data["model"] == prop_data["model"]
