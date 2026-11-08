"""Policy loading. Reads the YAML packs in data/policies/ (Person 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from backend.core.models import PolicyClause, PolicyPack

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"


def load_policy(jurisdiction: str, policy_dir: Optional[Path] = None) -> Optional[PolicyPack]:
    """Return the policy pack for a jurisdiction such as "CA", or None if unknown.

    The match uses the `jurisdiction:` field inside each YAML file and ignores
    upper/lower case, so Ca.yaml and CA.yaml both work on Mac and on Linux.
    """
    folder = policy_dir or POLICY_DIR
    wanted = (jurisdiction or "").strip().upper()
    if not wanted or not folder.exists():
        return None
    for path in sorted(folder.glob("*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and str(data.get("jurisdiction", "")).upper() == wanted:
            return PolicyPack.model_validate(data)
    return None


def find_clause(policy: Optional[PolicyPack], suffix: str) -> Optional[PolicyClause]:
    """Find a clause by its topic suffix, e.g. "OT-DAILY-01" finds "CA-OT-DAILY-01".

    Rules look clauses up by suffix, so every jurisdiction works without code changes.
    """
    if policy is None:
        return None
    tail = "-" + suffix.upper()
    for clause in policy.clauses:
        if clause.id.upper().endswith(tail):
            return clause
    return None


def get_param(policy: Optional[PolicyPack], suffix: str, name: str, default: float) -> float:
    clause = find_clause(policy, suffix)
    if clause is None:
        return default
    return clause.params.get(name, default)
