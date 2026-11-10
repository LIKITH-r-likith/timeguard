"""Tests for backend.agent.retrieval — keyword fallback and search."""

from backend.agent.context import InMemoryContextProvider
from backend.agent.retrieval import _cosine, keyword_score, search
import backend.agent.retrieval as ret_mod


class TestCosine:
    def test_orthogonal(self) -> None:
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_identical(self) -> None:
        assert round(_cosine([1.0, 2.0], [1.0, 2.0]), 4) == 1.0

    def test_zero_vector(self) -> None:
        assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


class TestEmbeddingSearch:
    def test_mocked_embedder(self, monkeypatch) -> None:
        class DummyEmbedder:
            def embed(self, texts):
                # Return vector pointing to [1.0, 0.0] for query and first clause,
                # [0.0, 1.0] for other clauses
                out = []
                for i, _ in enumerate(texts):
                    if i in (0, 1):  # query or first clause
                        out.append([1.0, 0.0])
                    else:
                        out.append([0.0, 1.0])
                return out

        monkeypatch.setenv("TIMEGUARD_EMBEDDINGS", "1")
        monkeypatch.setattr(ret_mod, "_EMBED_AVAILABLE", True)
        monkeypatch.setattr(ret_mod, "_EMBEDDER", DummyEmbedder())

        ctx = InMemoryContextProvider(_CASE)
        result = search(ctx, "missed punch", "CA", top_k=2, force_keyword=False)
        assert result.found
        assert len(result.clauses) >= 1
        assert result.clauses[0].score == 1.0

# A minimal golden case for policy search
_CASE = {
    "timecard": {
        "id": "tc_ret",
        "employee_id": "e_ret",
        "jurisdiction": "CA",
        "period_start": "2026-11-02",
        "period_end": "2026-11-08",
        "locked": False,
        "shifts": [
            {
                "id": "s_ret",
                "employee_id": "e_ret",
                "start": "2026-11-03T09:00:00+05:30",
                "end": "2026-11-03T17:00:00+05:30",
                "scheduled_break_minutes": 30,
            }
        ],
        "punches": [
            {"id": "p_ret_1", "employee_id": "e_ret", "type": "IN", "at": "2026-11-03T09:00:00+05:30"},
        ],
        "leaves": [],
        "notes": [],
    }
}


class TestKeywordScore:
    def test_exact_match(self) -> None:
        score = keyword_score("overtime daily hours", "daily overtime hours worked beyond")
        assert score > 0.3

    def test_no_overlap(self) -> None:
        score = keyword_score("banana fruit", "overtime daily hours policy")
        assert score == 0.0

    def test_partial_overlap(self) -> None:
        score = keyword_score("meal break required", "meal break of at least 30 minutes")
        assert 0.0 < score < 1.0

    def test_empty(self) -> None:
        assert keyword_score("", "some text") == 0.0
        assert keyword_score("query", "") == 0.0


class TestSearch:
    def test_search_finds_clauses(self) -> None:
        ctx = InMemoryContextProvider(_CASE)
        result = search(ctx, "missed punch correction", "CA", top_k=3, force_keyword=True)
        assert result.found
        assert any("MISS" in c.id for c in result.clauses)

    def test_search_overtime(self) -> None:
        ctx = InMemoryContextProvider(_CASE)
        result = search(ctx, "overtime daily hours", "CA", top_k=3, force_keyword=True)
        assert result.found
        assert any("OT" in c.id for c in result.clauses)

    def test_search_unknown_jurisdiction(self) -> None:
        ctx = InMemoryContextProvider(_CASE)
        result = search(ctx, "overtime", "XX", top_k=3, force_keyword=True)
        assert not result.found

    def test_search_meal_break(self) -> None:
        ctx = InMemoryContextProvider(_CASE)
        result = search(ctx, "meal break", "CA", top_k=3, force_keyword=True)
        assert result.found
        assert any("MEAL" in c.id for c in result.clauses)
