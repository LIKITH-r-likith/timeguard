"""Public entry point for the agent.

    from backend.agent.api import resolve

    result = resolve(exception_id, ctx, llm=my_llm)
"""

from __future__ import annotations

from typing import Optional

from backend.agent.llm import LLMClient, get_llm
from backend.agent.loop import resolve_loop
from backend.core.contract import ContextProvider
from backend.core.models import ResolutionResult


def resolve(
    exception_id: str,
    ctx: ContextProvider,
    llm: Optional[LLMClient] = None,
) -> ResolutionResult:
    """Resolve a timecard exception.

    Args:
        exception_id: The ID of the exception to resolve (from detect()).
        ctx:          A ContextProvider for data access.
        llm:          Optional LLM client.  If None, one is created via get_llm().

    Returns:
        ResolutionResult with the proposal, validation, attempts, trace_id, etc.
    """
    client: LLMClient = llm or get_llm()
    return resolve_loop(exception_id, ctx, client)
