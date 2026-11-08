"""Pytest configuration and test fixtures for backend.app tests."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure mock LLM for all tests
os.environ["LLM_MODE"] = "mock"

import backend.agent.api as agent_api
from backend.agent.llm import LLMResponse, MockLLM
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.seed import load_seed_timecards


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a fresh, isolated database for each test."""
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    engine = create_engine(f"sqlite:///{temp_db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    load_seed_timecards(session)

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient wired to the test database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def default_agent_resolve_mock(monkeypatch):
    """Provide a deterministic MockLLM for resolve calls across all API tests."""
    orig_resolve = agent_api.resolve

    def mock_resolve_wrapper(exception_id, ctx, llm=None):
        if llm is not None:
            return orig_resolve(exception_id, ctx, llm=llm)

        exc = ctx.get_exception(exception_id)
        timecard = ctx.get_timecard(exc.timecard_id)

        if exc.type.value == "MISSED_PUNCH":
            shift = timecard.shifts[0] if timecard.shifts else None
            at = shift.end.isoformat() if shift else "2026-11-03T17:00:00+05:30"
            proposal_dict = {
                "exception_id": exc.id,
                "action": "ADD_PUNCH",
                "changes": [{"op": "add_punch", "type": "OUT", "at": at}],
                "rationale": "Automated test resolution for missed punch",
                "evidence": [{"kind": "punch", "id": timecard.punches[0].id}],
                "policy_clauses": [c for c in exc.policy_clauses if "MISS" in c] or ["CA-MISS-01"],
                "confidence": 0.95,
                "needs_employee_confirmation": False,
            }
        elif exc.type.value == "OVERTIME_RISK":
            proposal_dict = {
                "exception_id": exc.id,
                "action": "FLAG_OVERTIME_FOR_APPROVAL",
                "changes": [],
                "rationale": "Automated test resolution for overtime risk",
                "evidence": [{"kind": "punch", "id": timecard.punches[0].id}],
                "policy_clauses": [c for c in exc.policy_clauses if "OT" in c] or ["CA-OT-DAILY-01"],
                "confidence": 0.90,
                "needs_employee_confirmation": False,
            }
        else:
            proposal_dict = {
                "exception_id": exc.id,
                "action": "ESCALATE_TO_HR",
                "changes": [],
                "rationale": "Automated test resolution escalating to HR",
                "evidence": [],
                "policy_clauses": [],
                "confidence": 0.5,
                "needs_employee_confirmation": False,
            }

        custom_mock = MockLLM([LLMResponse(text=json.dumps(proposal_dict))])
        return orig_resolve(exception_id, ctx, llm=custom_mock)

    monkeypatch.setattr(agent_api, "resolve", mock_resolve_wrapper)
