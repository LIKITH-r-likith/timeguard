"""Test that running the full test suite leaves evals/reports/latest.json byte-for-byte unchanged."""

import os
import subprocess
import sys
from pathlib import Path


def test_full_suite_leaves_latest_json_unchanged():
    """Verify that executing the full pytest suite leaves real latest.json byte-for-byte identical."""
    # Prevent infinite recursion when this test is executed inside the subprocess run
    if os.environ.get("_INSIDE_REPORT_INTEGRITY_CHECK") == "1":
        return

    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "evals" / "reports" / "latest.json"
    assert report_path.exists(), f"Real report must exist at {report_path}"

    before_bytes = report_path.read_bytes()
    assert len(before_bytes) > 0, "evals/reports/latest.json should not be empty"

    env = os.environ.copy()
    env["_INSIDE_REPORT_INTEGRITY_CHECK"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Pytest full suite execution failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    after_bytes = report_path.read_bytes()
    assert before_bytes == after_bytes, (
        f"evals/reports/latest.json was modified during full suite run!\n"
        f"Original: {len(before_bytes)} bytes, After: {len(after_bytes)} bytes"
    )


def test_latest_md_ratios_match_latest_json():
    """Verify that all metric ratios in evals/reports/latest.md match latest.json."""
    import json
    import re

    repo_root = Path(__file__).resolve().parents[1]
    json_path = repo_root / "evals" / "reports" / "latest.json"
    md_path = repo_root / "evals" / "reports" / "latest.md"

    assert json_path.exists(), f"latest.json missing at {json_path}"
    assert md_path.exists(), f"latest.md missing at {md_path}"

    data = json.loads(json_path.read_text("utf-8"))
    md_text = md_path.read_text("utf-8")

    # 1. Denominators table matching
    metric_map = {
        "First-Attempt Pass Rate": data["denominators"]["first_attempt_pass"],
        "Pass Rate After 1 Repair": data["denominators"]["pass_after_repair"],
        "Correct Action Rate": data["denominators"]["correct_action"],
        "Hallucinated Evidence Rate": data["denominators"]["hallucinated_evidence"],
        "Escalation Correctness": data["denominators"]["escalation_correctness"],
        "Prompt Injection Resistance": data["denominators"]["injection_resistance"],
        "Unsafe Proposals Reaching Manager": data["denominators"]["unsafe_proposals_reaching_manager"],
    }

    for metric_name, expected_ratio in metric_map.items():
        pattern = re.compile(rf"\*\*{re.escape(metric_name)}\*\*\s*\|\s*`([^`]+)`")
        match = pattern.search(md_text)
        assert match is not None, f"Metric '{metric_name}' not found in latest.md"
        assert match.group(1) == expected_ratio, (
            f"Ratio mismatch for '{metric_name}': latest.md has '{match.group(1)}', latest.json has '{expected_ratio}'"
        )

    # 2. Ablation table matching
    ablation_map = {
        "Pass Rate (Validation)": (
            data["denominators"]["pass_after_repair"],
            data["ablation"]["denominators_llm_alone"]["first_attempt_pass"],
        ),
        "Unsafe Proposals Reaching Manager": (
            data["ablation"]["unsafe_with_harness_ratio"],
            data["ablation"]["unsafe_llm_alone_ratio"],
        ),
        "Prompt Injection Resistance": (
            data["denominators"]["injection_resistance"],
            data["ablation"]["denominators_llm_alone"]["injection_resistance"],
        ),
        "Hallucinated Evidence Rate": (
            data["denominators"]["hallucinated_evidence"],
            data["ablation"]["denominators_llm_alone"]["hallucinated_evidence"],
        ),
    }

    for metric_name, (harness_ratio, baseline_ratio) in ablation_map.items():
        pattern = re.compile(
            rf"\*\*{re.escape(metric_name)}\*\*\s*\|\s*\*\*`([^`]+)`[^\n|]*\|\s*`([^`]+)`"
        )
        match = pattern.search(md_text)
        assert match is not None, f"Ablation row for '{metric_name}' not found in latest.md"
        assert match.group(1) == harness_ratio, (
            f"Ablation harness mismatch for '{metric_name}': md has '{match.group(1)}', json has '{harness_ratio}'"
        )
        assert match.group(2) == baseline_ratio, (
            f"Ablation baseline mismatch for '{metric_name}': md has '{match.group(2)}', json has '{baseline_ratio}'"
        )


def test_eval_runner_replay_mode_limit(tmp_path):
    """Test eval runner in replay mode with --limit 3 writes to tmp dir with no ALERT."""
    import json

    report_json = tmp_path / "custom_report.json"
    report_md = tmp_path / "custom_report.md"

    env = os.environ.copy()
    env["EVAL_REPORT_PATH"] = str(report_json)
    env["_INSIDE_REPORT_INTEGRITY_CHECK"] = "1"

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.runner.run_eval",
            "--mode",
            "replay",
            "--limit",
            "3",
            "--output-json",
            str(report_json),
            "--output-md",
            str(report_md),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"run_eval failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ALERT" not in result.stdout
    assert "ALERT" not in result.stderr
    assert report_json.exists(), "JSON report was not created in tmp dir"
    assert report_md.exists(), "Markdown report was not created in tmp dir"

    data = json.loads(report_json.read_text("utf-8"))
    evaluated_cases = data.get("ablation", {}).get("cases")
    assert evaluated_cases is not None and evaluated_cases > 0, "Evaluated exception count must be > 0"

