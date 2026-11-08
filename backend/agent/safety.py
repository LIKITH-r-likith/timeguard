"""Safety detector: scans employee notes for instruction-like text.

If detected, the harness forces ESCALATE_TO_HR regardless of model output and
records the finding in the trace.
"""

from __future__ import annotations

import re

# Case-insensitive patterns that suggest prompt injection.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\b", re.I),
    re.compile(r"\bdisregard\b", re.I),
    re.compile(r"\bapprove\b", re.I),
    re.compile(r"\bapproved\b", re.I),
    re.compile(r"\b(system|assistant|admin)\s*:", re.I),
    re.compile(r"\boverride\b", re.I),
    re.compile(r"\bbypass\b", re.I),
    re.compile(r"\bdo\s+not\s+follow\b", re.I),
    re.compile(r"\bforget\s+(your|all)\b", re.I),
]


def scan_notes(notes: list[str]) -> list[str]:
    """Return a list of matched pattern descriptions.  Empty means clean."""
    hits: list[str] = []
    for note in notes:
        for pat in _PATTERNS:
            if pat.search(note):
                hits.append(f"Pattern '{pat.pattern}' matched in note: {note!r}")
    return hits


def is_injection(notes: list[str]) -> bool:
    """Convenience: True if any injection pattern fires."""
    return len(scan_notes(notes)) > 0
