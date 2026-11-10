# TimeGuard Evaluation & Ablation Report

- **Generated At**: `2026-11-10T09:47:29.229811+00:00`
- **Model**: `openai/gpt-oss-120b`
- **Prompt Version**: `v1`
- **Mode**: `replay`
- **Evaluated Exceptions**: `44`

## Detection Performance (Rules Engine)

| Metric | Ratio | Percentage |
|---|---|---|
| **Detection Recall** | `44 of 44` | `100.0%` |
| **Detection Precision** | `44 of 44` | `100.0%` |
| **Detection F1** | `44 of 44` | `100.0%` |

## Core Safety & Quality Metrics (With Harness)

| Metric | Ratio | Percentage | Benchmark Target |
|---|---|---|---|
| **First-Attempt Pass Rate** | `44 of 44` | `100.0%` | &ge; 70% |
| **Pass Rate After 1 Repair** | `44 of 44` | `100.0%` | &ge; 95% |
| **Correct Action Rate** | `44 of 44` | `100.0%` | &ge; 90% |
| **Hallucinated Evidence Rate** | `0 of 44` | `0.0%` | 0.0% |
| **Escalation Correctness** | `6 of 6` | `100.0%` | 100.0% |
| **Prompt Injection Resistance** | `4 of 4` | `100.0%` | 100.0% |
| **Unsafe Proposals Reaching Manager** | `0 of 44` | `0.0%` | **0.0% (Zero)** |

## Key Judge Evidence: Ablation Comparison

> [!IMPORTANT]
> **The Harness Difference**: Demonstrating how the deterministic validator, repair loop, and safety layer eliminate hallucinations, prevent prompt injection, and guarantee zero unsafe proposals reach the manager queue.

| Evaluation Metric | TimeGuard (With Harness) | Baseline (LLM Alone) | Impact / Delta |
|---|---|---|---|
| **Pass Rate (Validation)** | **`44 of 44` (100.0%)** | `44 of 44` (100.0%) | +0.0% |
| **Unsafe Proposals Reaching Manager** | **`0 of 44` (0.0%)** | `4 of 44` (9.1%) | **-4 unsafe proposals prevented** |
| **Prompt Injection Resistance** | **`4 of 4` (100.0%)** | `0 of 4` (0.0%) | +100.0% |
| **Hallucinated Evidence Rate** | **`0 of 44` (0.0%)** | `0 of 44` (0.0%) | -0.0% |
| **Human-in-the-Loop Gate** | **Enforced (Read-Only LLM)** | Direct / Unvalidated | Guaranteed Safety |

## What "LLM alone" Means

The **Baseline (LLM Alone)** benchmark evaluates raw foundation model capability against the same real-world timecard exceptions:
- **Same Model**: The identical model is used (`openai/gpt-oss-120b`).
- **Same Tools**: The model is provided the exact same 5 read-only contract tools (`get_timecard`, `get_schedule`, `get_leave`, `get_history`, `search_policy`).
- **System Prompt**: It receives the standard versioned system prompt (`prompts/v1/system.md`).
- **What is Removed**:
  1. **Safety Gate**: The pre-LLM adversarial scanner (`backend.agent.safety.is_injection`) is disabled, allowing untrusted employee notes to pass directly to the LLM.
  2. **Deterministic Validator**: Proposals are not checked by `backend.core.api.validate()`; unvalidated raw outputs go straight toward decision.
  3. **Repair Loop**: When a proposal violates policy or structure, no validator feedback is provided and no self-correction repair attempt occurs.
  4. **Locked-Period Rule**: The deterministic guard in `backend.agent.loop` that automatically escalates timecards in locked pay periods is bypassed.

> [!NOTE]
> The 51 evaluation cases (yielding 44 detected exception records across California and Kansas jurisdictions) constitute a development set used for benchmarking. All reported results reflect one recorded run executed under live API conditions and preserved for deterministic replay verification.

*All policy numbers, pay rates, and figures are mock values for demonstration purposes. Not legal advice.*