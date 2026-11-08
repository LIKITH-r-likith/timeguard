"""Runs detect() on every golden case and compares with the expected answer."""

import json
from pathlib import Path

import pytest

from backend.core.api import detect, load_policy
from backend.core.models import Timecard

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "evals" / "golden"


def load_cases():
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


CASES = load_cases()


def test_there_are_48_new_cases_plus_examples():
    ids = [c["case_id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case_id"
    assert sum(c["kind"] == "golden" for c in CASES) >= 40
    assert sum(c["kind"] == "adversarial" for c in CASES) >= 8


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_detect_matches_expected(case):
    card = Timecard.model_validate(case["timecard"])
    found = {(e.type.value, e.work_date.isoformat()) for e in detect(card, load_policy(card.jurisdiction))}
    want = {(x["type"], x["work_date"]) for x in case["expected"]["exceptions"]}
    assert found == want, case["description"]
