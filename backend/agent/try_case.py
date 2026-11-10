"""CLI runner to try a custom case with the live LLM.

Usage:
    python -m backend.agent.try_case [CASE_FILE] [--mock]
    make try CASE=evals/golden/try_example.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env without overriding environment
load_dotenv(override=False)

from backend.agent.api import resolve
from backend.agent.context import InMemoryContextProvider
from backend.agent.llm import GroqClient, MockLLM, ReplayLLM, get_llm
from backend.agent.loop import get_client_badge
from backend.agent.trace import get_trace
from backend.core.api import detect, load_policy
from backend.core.contract import VALIDATION_CHECK_ORDER
from backend.core.models import ExceptionRecord, Timecard


def load_case_file(path: Path) -> dict[str, Any]:
    """Load case dict from JSON or JSONL file."""
    if not path.exists():
        raise FileNotFoundError(f"Case file not found: {path}")

    text = path.read_text("utf-8").strip()
    if not text:
        raise ValueError(f"Case file is empty: {path}")

    # Try parsing full JSON object
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try first non-empty line (JSONL)
        for line in text.splitlines():
            line = line.strip()
            if line:
                return json.loads(line)
        raise ValueError(f"Could not parse valid JSON from {path}")


def run_try_case(
    case_path: Path,
    mock: bool = False,
    model_name: Optional[str] = None,
) -> int:
    """Run agent on the specified case file and print details."""
    case = load_case_file(case_path)
    timecard_dict = case.get("timecard")
    if not timecard_dict:
        print(f"ERROR: Case file {case_path} is missing 'timecard' object.", file=sys.stderr)
        return 1

    timecard = Timecard.model_validate(timecard_dict)
    policy = load_policy(timecard.jurisdiction)
    detected_exceptions = detect(timecard, policy)

    case_id = case.get("case_id", case_path.stem)
    description = case.get("description", "Custom trial case")
    notes = timecard.notes

    print("=" * 78)
    print(f"TIMEGUARD TRIAL RUN: {case_id}")
    print("=" * 78)
    print(f"File:         {case_path}")
    print(f"Description:  {description}")
    print(f"Employee ID:  {timecard.employee_id}")
    print(f"Jurisdiction: {timecard.jurisdiction}")
    print(f"Pay Period:   {timecard.period_start} to {timecard.period_end} (locked: {timecard.locked})")
    if notes:
        print(f"Notes ({len(notes)}):   {notes}")
    else:
        print("Notes:        (none)")
    print(f"Exceptions:   {len(detected_exceptions)} detected by rules engine")
    print("=" * 78)

    if not detected_exceptions:
        print("\n[OK] Rules engine detected no exceptions on this timecard.")
        print("Punches and shifts are fully compliant with policy.")
        return 0

    # Configure client
    if mock or os.environ.get("LLM_MODE") == "mock":
        llm = MockLLM()
        client_label = "Mock model"
    else:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print(
                "\nERROR: GROQ_API_KEY environment variable is missing.\n"
                "To run live with Groq:\n"
                "  1. Set your key in .env (GROQ_API_KEY=gsk_...)\n"
                "  2. Or export GROQ_API_KEY=gsk_... in your terminal\n"
                "  3. Or run with --mock for offline dry-run testing\n",
                file=sys.stderr,
            )
            return 1

        selected_model = model_name or os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
        llm = GroqClient(model=selected_model)
        client_label = f"Live model: {selected_model}"

    ctx = InMemoryContextProvider(case)

    for idx, exc in enumerate(detected_exceptions, 1):
        print(f"\n>>> EXCEPTION {idx}/{len(detected_exceptions)}: {exc.id}")
        print(f"    Type:      {exc.type.value}")
        print(f"    Work Date: {exc.work_date}")
        print(f"    Detail:    {exc.detail}")
        print(f"    Clauses:   {exc.policy_clauses}")
        print(f"    Client:    {client_label}")
        print("-" * 78)

        t_start = time.monotonic()
        resolution = resolve(exc.id, ctx, llm=llm)
        t_duration = time.monotonic() - t_start

        trace = get_trace(resolution.trace_id)
        proposal = resolution.proposal
        validation = resolution.validation

        # 1. Print Tool Calls
        tool_calls = []
        token_input = 0
        token_output = 0
        total_latency_ms = int(t_duration * 1000)

        if trace:
            for s in trace.steps:
                if s.kind == "tool_call":
                    tool_calls.append(s.data)
                elif s.kind in ("llm_response", "attempt_1"):
                    token_input += s.data.get("input_tokens", 0)
                    token_output += s.data.get("output_tokens", 0)
                    if s.data.get("latency_ms"):
                        total_latency_ms = s.data.get("latency_ms")

        print("\n[1] TOOL CALLS EXECUTED BY AGENT:")
        if tool_calls:
            for s_idx, tc in enumerate(tool_calls, 1):
                name = tc.get("name", "unknown")
                args = tc.get("arguments", {})
                res_len = tc.get("result_len", 0)
                print(f"    Step {s_idx}: {name}({json.dumps(args)}) -> {res_len} bytes")
        else:
            print("    (No tools called - safety detector or deterministic guard intervened)")

        # 2. Print Generated Proposal
        print("\n[2] GENERATED PROPOSAL:")
        print(f"    Action:             {proposal.action.value}")
        print(f"    Confidence:         {proposal.confidence:.2f}")
        print(f"    Needs Confirmation: {proposal.needs_employee_confirmation}")
        print(f"    Rationale:          {proposal.rationale}")
        if proposal.changes:
            print("    Changes proposed:")
            for ch in proposal.changes:
                print(f"      - op: {ch.op}, type: {ch.type}, at: {ch.at}, punch_id: {ch.punch_id}")
        else:
            print("    Changes proposed:   []")

        if proposal.evidence:
            print("    Evidence cited:")
            for ev in proposal.evidence:
                print(f"      - {ev.kind}: {ev.id}")

        if proposal.policy_clauses:
            print(f"    Policy clauses:     {proposal.policy_clauses}")

        # 3. Print the 7 Validator Checks
        print("\n[3] DETERMINISTIC VALIDATOR CHECKS (7 CHECKS):")
        check_dict = {c.name: c for c in validation.checks}
        for check_enum in VALIDATION_CHECK_ORDER:
            c_name = check_enum.value
            c_res = check_dict.get(c_name)
            if c_res:
                tag = "[PASS]" if c_res.passed else "[FAIL]"
                print(f"    {tag} {c_name:<26} : {c_res.detail}")
            else:
                print(f"    [SKIP] {c_name:<26} : (not evaluated)")

        val_status = "PASSED" if validation.passed else "FAILED"
        print(f"\n    Validation Result:  {val_status}")
        if validation.pay_impact:
            pi = validation.pay_impact
            print(f"    Pay Impact:         cost delta {pi.estimated_cost_delta:+.2f} {pi.currency} ({pi.regular_minutes_delta:+d} min reg, {pi.overtime_minutes_delta:+d} min ot)")

        # 4. Token Counts and Latency
        print("\n[4] EXECUTION TELEMETRY:")
        print(f"    Client Badge:       {client_label}")
        print(f"    Attempts:           {resolution.attempts}")
        print(f"    Used Fallback:      {resolution.used_fallback}")
        print(f"    Input Tokens:       {token_input}")
        print(f"    Output Tokens:      {token_output}")
        print(f"    Total Tokens:       {token_input + token_output}")
        print(f"    Latency:            {total_latency_ms} ms ({total_latency_ms / 1000:.2f} s)")
        print(f"    Trace ID:           {resolution.trace_id}")
        print("=" * 78)

    return 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="TimeGuard live case trial tool")
    parser.add_argument("case", nargs="?", default="evals/golden/try_example.json", help="Path to JSON case file")
    parser.add_argument("--mock", action="store_true", help="Run with mock LLM (no API key required)")
    parser.add_argument("--model", type=str, default=None, help="Groq model override")

    args = parser.parse_args()
    case_path = Path(args.case)
    sys.exit(run_try_case(case_path, mock=args.mock, model_name=args.model))


if __name__ == "__main__":
    main()
