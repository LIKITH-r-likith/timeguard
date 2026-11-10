"""Test policy retrieval reproducibility: fastembed is never called unless TIMEGUARD_EMBEDDINGS=1."""

from __future__ import annotations

import sys
import types
from pathlib import Path
import pytest

from backend.agent.context import InMemoryContextProvider
from backend.agent.retrieval import search
import backend.agent.retrieval as ret_mod


_CASE = {
    "timecard": {
        "id": "tc_repro_test",
        "employee_id": "e_repro",
        "jurisdiction": "CA",
        "period_start": "2026-11-02",
        "period_end": "2026-11-08",
        "locked": False,
        "shifts": [
            {
                "id": "s_repro_1",
                "employee_id": "e_repro",
                "start": "2026-11-03T09:00:00+05:30",
                "end": "2026-11-03T17:00:00+05:30",
                "scheduled_break_minutes": 30,
            }
        ],
        "punches": [
            {"id": "p_repro_1", "employee_id": "e_repro", "type": "IN", "at": "2026-11-03T09:00:00+05:30"},
        ],
        "leaves": [],
        "notes": [],
    }
}


def test_retrieval_uses_keyword_and_never_calls_fastembed_when_env_unset(monkeypatch):
    """When TIMEGUARD_EMBEDDINGS is unset, retrieval must use keyword path and never invoke fastembed."""
    monkeypatch.delenv("TIMEGUARD_EMBEDDINGS", raising=False)

    fastembed_touched = False

    class FakeTextEmbedding:
        def __init__(self, *args, **kwargs):
            nonlocal fastembed_touched
            fastembed_touched = True
            raise AssertionError("FakeTextEmbedding.__init__ must never be called when TIMEGUARD_EMBEDDINGS is unset!")

        def embed(self, *args, **kwargs):
            nonlocal fastembed_touched
            fastembed_touched = True
            raise AssertionError("FakeTextEmbedding.embed must never be called when TIMEGUARD_EMBEDDINGS is unset!")

    # Inject a fake fastembed module into sys.modules so it is definitely "importable"
    fake_mod = types.ModuleType("fastembed")
    fake_mod.TextEmbedding = FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fake_mod)

    # Reset any cached embedder in retrieval module
    monkeypatch.setattr(ret_mod, "_EMBEDDER", None)
    monkeypatch.setattr(ret_mod, "_EMBED_AVAILABLE", False)

    ctx = InMemoryContextProvider(_CASE)
    result = search(ctx, "missed punch clock out", "CA", top_k=3, force_keyword=False)

    assert not fastembed_touched, "fastembed was touched despite TIMEGUARD_EMBEDDINGS being unset"
    assert result.found, "Deterministic keyword search should successfully find policy clauses"
    assert any("MISS" in hit.id for hit in result.clauses)


def test_retrieval_uses_fastembed_only_when_env_set(monkeypatch):
    """When TIMEGUARD_EMBEDDINGS=1 is explicitly set, retrieval uses the embedding path."""
    monkeypatch.setenv("TIMEGUARD_EMBEDDINGS", "1")

    called = False

    class MockEmbedding:
        def embed(self, texts):
            nonlocal called
            called = True
            # Return identical vectors so score=1.0
            return [[1.0, 0.0] for _ in texts]

    fake_mod = types.ModuleType("fastembed")
    fake_mod.TextEmbedding = lambda model_name: MockEmbedding()
    monkeypatch.setitem(sys.modules, "fastembed", fake_mod)

    monkeypatch.setattr(ret_mod, "_EMBEDDER", None)
    monkeypatch.setattr(ret_mod, "_EMBED_AVAILABLE", False)

    ctx = InMemoryContextProvider(_CASE)
    result = search(ctx, "missed punch clock out", "CA", top_k=3, force_keyword=False)

    assert called, "fastembed embed() should be called when TIMEGUARD_EMBEDDINGS=1"
    assert result.found
