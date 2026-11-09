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
