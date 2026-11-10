"""The five read-only agent tools, exactly matching TOOL_SPECS in contract.py.

Each tool calls the ContextProvider and returns JSON-serializable output.
Employee notes are wrapped in <untrusted_employee_note> tags.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.core.contract import ContextProvider, SearchPolicyResult


def _wrap_notes(notes: list[str]) -> list[str]:
    """Wrap each employee note in untrusted delimiters."""
    return [
        f"<untrusted_employee_note>{n}</untrusted_employee_note>"
        for n in notes
    ]


def _serialize(obj: Any) -> Any:
    """Recursively make an object JSON-serializable."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def get_timecard(ctx: ContextProvider, timecard_id: str) -> dict:
    """Retrieve timecard details with employee notes safely delimited in XML tags."""
    tc = ctx.get_timecard(timecard_id)
    data = tc.model_dump(mode="json")
    data["notes"] = _wrap_notes(tc.notes)
    return data


def get_schedule(ctx: ContextProvider, employee_id: str, start_date: str, end_date: str) -> list[dict]:
    """Retrieve scheduled shifts for an employee over a date range."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    shifts = ctx.get_schedule(employee_id, start, end)
    return _serialize(shifts)


def get_leave(ctx: ContextProvider, employee_id: str, start_date: str, end_date: str) -> list[dict]:
    """Retrieve approved leave periods for an employee over a date range."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    leaves = ctx.get_leave(employee_id, start, end)
    return _serialize(leaves)


def get_history(ctx: ContextProvider, employee_id: str, weeks: int = 4) -> list[dict]:
    """Retrieve historical punch records for an employee over the requested weeks."""
    punches = ctx.get_history(employee_id, weeks)
    return _serialize(punches)


def search_policy(
    ctx: ContextProvider,
    query: str,
    jurisdiction: str,
    top_k: int = 3,
    *,
    searcher: Any = None,
) -> dict:
    """Search policy clauses.  Uses the retrieval module if available."""
    from backend.agent.retrieval import search  # local import to avoid circular

    result: SearchPolicyResult = search(ctx, query, jurisdiction, top_k)
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Dispatch: name -> handler
# ---------------------------------------------------------------------------
_DISPATCH: dict[str, Any] = {
    "get_timecard": lambda ctx, args: get_timecard(ctx, **args),
    "get_schedule": lambda ctx, args: get_schedule(ctx, **args),
    "get_leave": lambda ctx, args: get_leave(ctx, **args),
    "get_history": lambda ctx, args: get_history(ctx, **args),
    "search_policy": lambda ctx, args: search_policy(ctx, **args),
}


def execute_tool(name: str, arguments: dict, ctx: ContextProvider) -> str:
    """Execute a tool by name and return a JSON string result."""
    handler = _DISPATCH.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = handler(ctx, arguments)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
