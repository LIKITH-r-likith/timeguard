"""Agent harness: the tool-call loop, proposal parsing, validation, and repair.

This is the heart of the agent. It:
1. Checks notes for injection (safety.py)
2. Runs the LLM in a tool-call loop (at most MAX_TOOL_STEPS)
3. Parses the Proposal JSON
4. Validates via backend.core.api.validate()
5. On failure: one repair attempt, then fallback
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.agent import safety
from backend.agent.fallback import fallback_proposal
from backend.agent.llm import LLMClient, LLMResponse
from backend.agent.tools import execute_tool
from backend.agent.trace import Trace, store_trace
from backend.core.api import validate
from backend.core.contract import (
    ContextProvider,
    MAX_TOOL_STEPS,
    TOOL_SPECS,
    SearchPolicyResult,
)
from backend.core.models import (
    CheckResult,
    ExceptionRecord,
    Proposal,
    ProposalAction,
    ResolutionResult,
    Timecard,
    ValidationResult,
)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "v1"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text("utf-8")


def _build_system_message(exc: ExceptionRecord, timecard: Timecard) -> str:
    template = _load_prompt("system.md")
    return template.format(
        exception_id=exc.id,
        exception_type=exc.type.value,
        exception_detail=exc.detail,
        employee_id=exc.employee_id,
        timecard_id=exc.timecard_id,
        jurisdiction=timecard.jurisdiction,
        work_date=exc.work_date.isoformat(),
    )


def _build_repair_message(checks: list[CheckResult]) -> str:
    template = _load_prompt("repair.md")
    failures = "\n".join(
        f"- **{c.name}**: {c.detail}" for c in checks if not c.passed
    )
    return template.format(failures=failures)


def _parse_proposal(text: str) -> Optional[Proposal]:
    """Try to extract a Proposal JSON from the LLM text output."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        return Proposal.model_validate(data)
    except Exception:
        return None


def _escalate_proposal(exception: ExceptionRecord, rationale: str) -> Proposal:
    """Build an ESCALATE_TO_HR proposal."""
    return Proposal(
        exception_id=exception.id,
        action=ProposalAction.ESCALATE_TO_HR,
        rationale=rationale,
        confidence=0.0,
    )


@dataclass
class ToolLoopResult:
    response: LLMResponse
    policy_not_found: bool = False


def _run_tool_loop(
    llm: LLMClient,
    messages: list[dict],
    ctx: ContextProvider,
    trace: Trace,
) -> ToolLoopResult:
    """Call the LLM in a loop, executing tool calls until it returns text."""
    total_input = 0
    total_output = 0
    total_latency = 0
    steps = 0
    policy_not_found = False

    while steps < MAX_TOOL_STEPS:
        resp = llm.complete(messages, tools=TOOL_SPECS)
        total_input += resp.input_tokens
        total_output += resp.output_tokens
        total_latency += resp.latency_ms

        if not resp.tool_calls:
            # Model is done calling tools; it gave us text
            resp.input_tokens = total_input
            resp.output_tokens = total_output
            resp.latency_ms = total_latency
            trace.add("llm_response", {"text": resp.text})
            return ToolLoopResult(response=resp, policy_not_found=policy_not_found)

        # Execute each tool call
        for tc in resp.tool_calls:
            tool_result = execute_tool(tc["name"], tc["arguments"], ctx)
            trace.add("tool_call", {
                "name": tc["name"],
                "arguments": tc["arguments"],
                "result_len": len(tool_result),
            })
            if tc["name"] == "search_policy":
                try:
                    parsed_res = json.loads(tool_result)
                    if parsed_res.get("found") is False:
                        policy_not_found = True
                except Exception:
                    pass

            # Add assistant message with tool call, then tool result
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.get("id", f"call_{steps}"),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{steps}"),
                "content": tool_result,
            })
            steps += 1

            if policy_not_found:
                resp.input_tokens = total_input
                resp.output_tokens = total_output
                resp.latency_ms = total_latency
                return ToolLoopResult(response=resp, policy_not_found=True)

            if steps >= MAX_TOOL_STEPS:
                break

    # Hit tool step limit — ask the model for its final answer
    messages.append({
        "role": "user",
        "content": "You have reached the tool call limit. Please output your proposal JSON now.",
    })
    resp = llm.complete(messages, tools=None)
    total_input += resp.input_tokens
    total_output += resp.output_tokens
    total_latency += resp.latency_ms
    resp.input_tokens = total_input
    resp.output_tokens = total_output
    resp.latency_ms = total_latency
    trace.add("llm_response", {"text": resp.text, "tool_limit_reached": True})
    return ToolLoopResult(response=resp, policy_not_found=policy_not_found)


def resolve_loop(
    exception_id: str,
    ctx: ContextProvider,
    llm: LLMClient,
) -> ResolutionResult:
    """Main resolution loop.  Returns a ResolutionResult (always)."""
    t0 = time.monotonic()
    trace = Trace()

    # 1. Load exception and timecard
    exc = ctx.get_exception(exception_id)
    timecard = ctx.get_timecard(exc.timecard_id)
    policy = ctx.get_policy_pack(timecard.jurisdiction)

    # 2. Safety check: scan employee notes for injection
    injection_hits = safety.scan_notes(timecard.notes)
    if injection_hits:
        trace.add("safety_flag", {"hits": injection_hits})
        proposal = _escalate_proposal(exc, "Safety: injection detected in employee notes.")
        vr = validate(proposal, timecard, policy)
        store_trace(trace)
        return ResolutionResult(
            proposal=proposal,
            validation=vr,
            attempts=1,
            used_fallback=False,
            trace_id=trace.trace_id,
        )

    # 3. Build the system message
    system_msg = _build_system_message(exc, timecard)
    messages: list[dict] = [{"role": "system", "content": system_msg}]

    # 4. First attempt: tool loop + parse + validate
    loop_res = _run_tool_loop(llm, messages, ctx, trace)
    resp = loop_res.response

    if loop_res.policy_not_found:
        trace.add("policy_not_found", {"reason": "search_policy returned found=False"})
        proposal = _escalate_proposal(exc, "Policy search found no matching clauses. Escalating to HR.")
        vr = validate(proposal, timecard, policy, exception=exc)
        store_trace(trace)
        latency = int((time.monotonic() - t0) * 1000)
        return ResolutionResult(
            proposal=proposal,
            validation=vr,
            attempts=1,
            used_fallback=False,
            trace_id=trace.trace_id,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            latency_ms=latency,
        )

    proposal = _parse_proposal(resp.text)

    if proposal is not None:
        vr = validate(proposal, timecard, policy, exception=exc)
        trace.add("validation", {
            "attempt": 1,
            "passed": vr.passed,
            "checks": [c.model_dump() for c in vr.checks],
        })
        if vr.passed:
            latency = int((time.monotonic() - t0) * 1000)
            store_trace(trace)
            return ResolutionResult(
                proposal=proposal,
                validation=vr,
                attempts=1,
                used_fallback=False,
                trace_id=trace.trace_id,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                latency_ms=latency,
            )
        failed_checks = vr.checks
    else:
        trace.add("validation", {"attempt": 1, "passed": False, "error": "JSON parse failure"})
        failed_checks = [CheckResult(name="json_parse", passed=False, detail="Could not parse proposal JSON.")]

    # 5. Repair attempt
    repair_msg = _build_repair_message(failed_checks)
    messages.append({"role": "user", "content": repair_msg})
    loop_res2 = _run_tool_loop(llm, messages, ctx, trace)
    resp2 = loop_res2.response

    total_input = resp.input_tokens + resp2.input_tokens
    total_output = resp.output_tokens + resp2.output_tokens

    if loop_res2.policy_not_found:
        trace.add("policy_not_found", {"reason": "search_policy returned found=False on repair"})
        proposal = _escalate_proposal(exc, "Policy search found no matching clauses. Escalating to HR.")
        vr = validate(proposal, timecard, policy, exception=exc)
        store_trace(trace)
        latency = int((time.monotonic() - t0) * 1000)
        return ResolutionResult(
            proposal=proposal,
            validation=vr,
            attempts=2,
            used_fallback=False,
            trace_id=trace.trace_id,
            input_tokens=total_input,
            output_tokens=total_output,
            latency_ms=latency,
        )

    proposal2 = _parse_proposal(resp2.text)

    if proposal2 is not None:
        vr2 = validate(proposal2, timecard, policy, exception=exc)
        trace.add("validation", {
            "attempt": 2,
            "passed": vr2.passed,
            "checks": [c.model_dump() for c in vr2.checks],
        })
        if vr2.passed:
            latency = int((time.monotonic() - t0) * 1000)
            store_trace(trace)
            return ResolutionResult(
                proposal=proposal2,
                validation=vr2,
                attempts=2,
                used_fallback=False,
                trace_id=trace.trace_id,
                input_tokens=total_input,
                output_tokens=total_output,
                latency_ms=latency,
            )

    # 6. Both attempts failed — use deterministic fallback
    trace.add("fallback", {"reason": "Two LLM attempts failed validation"})
    fb = fallback_proposal(exc)
    fb_vr = validate(fb, timecard, policy, exception=exc)
    latency = int((time.monotonic() - t0) * 1000)
    store_trace(trace)
    return ResolutionResult(
        proposal=fb,
        validation=fb_vr,
        attempts=2,
        used_fallback=True,
        trace_id=trace.trace_id,
        input_tokens=total_input,
        output_tokens=total_output,
        latency_ms=latency,
    )
