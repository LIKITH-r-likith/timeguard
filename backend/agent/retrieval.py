"""Policy search with embedding + keyword fallback.

Primary:  fastembed (BAAI/bge-small-en-v1.5) cosine similarity.
Fallback: keyword overlap scoring when embedding model cannot load.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

from backend.core.contract import (
    ContextProvider,
    PolicyHit,
    SEARCH_POLICY_MIN_SCORE,
    SearchPolicyResult,
)
from backend.core.models import PolicyClause


# ---------------------------------------------------------------------------
# Embedding support: used ONLY when TIMEGUARD_EMBEDDINGS=1.
# Default is the keyword retriever, in every mode (live, replay, mock, demo),
# with no network access or model download.
# ---------------------------------------------------------------------------
_EMBEDDER: Any = None
_EMBED_AVAILABLE = False


def _use_embeddings() -> bool:
    """Return True only if TIMEGUARD_EMBEDDINGS=1."""
    return os.environ.get("TIMEGUARD_EMBEDDINGS") == "1"


def _get_embedder() -> Any:
    """Lazily load fastembed only if TIMEGUARD_EMBEDDINGS=1."""
    global _EMBEDDER, _EMBED_AVAILABLE
    if not _use_embeddings():
        return None
    if _EMBEDDER is not None:
        return _EMBEDDER
    try:
        from fastembed import TextEmbedding  # type: ignore[import-untyped]

        _EMBEDDER = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        _EMBED_AVAILABLE = True
    except Exception:
        _EMBEDDER = None
        _EMBED_AVAILABLE = False
    return _EMBEDDER


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    embedder = _get_embedder()
    if embedder is None:
        raise RuntimeError("fastembed not available or TIMEGUARD_EMBEDDINGS != 1")
    return [list(v) for v in embedder.embed(texts)]


# ---------------------------------------------------------------------------
# Keyword fallback
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> set[str]:
    """Simple lowercase word tokenisation."""
    return {w for w in text.lower().split() if len(w) > 1}


_STOP_WORDS = {
    "policy", "policies", "california", "kansas", "ca", "ka", "rule", "rules",
    "regulation", "regulations", "law", "laws", "clause", "clauses", "for",
    "the", "in", "and", "or", "to", "of", "a", "an", "is", "on", "at", "by",
    "with", "about", "approval", "standard", "guideline", "guidelines", "please",
    "search", "lookup", "find",
}


def keyword_score(query: str, clause_text: str) -> float:
    """Recall-oriented keyword overlap: fraction of non-stop query words found in clause."""
    raw_q = _tokenize(query)
    filtered_q = {w for w in raw_q if w not in _STOP_WORDS}
    q_tokens = filtered_q if filtered_q else raw_q
    c_tokens = _tokenize(clause_text)
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    return overlap / len(q_tokens)


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------
def search(
    ctx: ContextProvider,
    query: str,
    jurisdiction: str,
    top_k: int = 3,
    *,
    force_keyword: bool = False,
) -> SearchPolicyResult:
    """Search policy clauses by semantic similarity or keyword overlap."""
    pack = ctx.get_policy_pack(jurisdiction)
    if pack is None:
        return SearchPolicyResult(found=False)

    clauses: list[PolicyClause] = pack.clauses
    if not clauses:
        return SearchPolicyResult(found=False)

    scored: list[tuple[PolicyClause, float]] = []

    if _use_embeddings() and not force_keyword:
        embedder = _get_embedder()
        if embedder is not None:
            try:
                texts = [query] + [f"{c.title}: {c.text}" for c in clauses]
                vecs = _embed_texts(texts)
                q_vec = vecs[0]
                for i, clause in enumerate(clauses):
                    sim = _cosine(q_vec, vecs[i + 1])
                    scored.append((clause, sim))
            except Exception:
                scored = []  # fall through to keyword

    if not scored:
        # Keyword fallback
        for clause in clauses:
            score = keyword_score(query, f"{clause.id} {clause.title} {clause.text}")
            scored.append((clause, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]

    hits = [
        PolicyHit(id=c.id, title=c.title, text=c.text, score=round(s, 4))
        for c, s in top
        if s >= SEARCH_POLICY_MIN_SCORE
    ]

    return SearchPolicyResult(found=len(hits) > 0, clauses=hits)
