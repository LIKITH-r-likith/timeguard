# TimeGuard Evaluation & Ablation Report

- **Generated At**: `2026-11-10T01:30:22.487766+00:00`
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
| **First-Attempt Pass Rate** | `43 of 44` | `97.7%` | &ge; 70% |
| **Pass Rate After 1 Repair** | `44 of 44` | `100.0%` | &ge; 95% |
| **Correct Action Rate** | `44 of 44` | `100.0%` | &ge; 90% |
| **Hallucinated Evidence Rate** | `0 of 44` | `0.0%` | 0.0% |
| **Escalation Correctness** | `6 of 6` | `100.0%` | 100.0% |
| **Prompt Injection Resistance** | `3 of 3` | `100.0%` | 100.0% |
| **Unsafe Proposals Reaching Manager** | `0 of 44` | `0.0%` | **0.0% (Zero)** |

## Key Judge Evidence: Ablation Comparison

> [!IMPORTANT]
> **The Harness Difference**: Demonstrating how the deterministic validator, repair loop, and safety layer eliminate hallucinations, prevent prompt injection, and guarantee zero unsafe proposals reach the manager queue.

| Evaluation Metric | TimeGuard (With Harness) | Baseline (LLM Alone) | Impact / Delta |
|---|---|---|---|
| **Pass Rate (Validation)** | **`44 of 44` (100.0%)** | `43 of 44` (97.7%) | +2.3% |
| **Unsafe Proposals Reaching Manager** | **`0 of 44` (0.0%)** | `7 of 44` (15.9%) | **-7 unsafe proposals prevented** |
| **Prompt Injection Resistance** | **`3 of 3` (100.0%)** | `0 of 4` (0.0%) | +100.0% |
| **Hallucinated Evidence Rate** | **`0 of 44` (0.0%)** | `0 of 44` (0.0%) | -0.0% |
| **Human-in-the-Loop Gate** | **Enforced (Read-Only LLM)** | Direct / Unvalidated | Guaranteed Safety |

*All policy numbers, pay rates, and figures are mock values for demonstration purposes. Not legal advice.*