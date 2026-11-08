"""Pytest configuration for TimeGuard.

Loads environment variables from .env if present and guarantees
that tests run with LLM_MODE=mock so no network calls are made.
"""

from pathlib import Path
import os
import pytest
from dotenv import load_dotenv

# Load .env at repo root
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Enforce mock LLM for all tests
os.environ["LLM_MODE"] = "mock"


@pytest.fixture(autouse=True)
def force_mock_llm(monkeypatch):
    """Ensure LLM_MODE remains mock throughout test runs."""
    monkeypatch.setenv("LLM_MODE", "mock")
