"""Safety detector: scans employee notes and text fields for prompt injection.

If detected, the harness forces ESCALATE_TO_HR regardless of model output and
records the finding in the trace.
"""

from __future__ import annotations

import re

# Case-insensitive patterns that suggest prompt injection, tampering, or jailbreaks.
_PATTERNS: list[re.Pattern[str]] = [
    # Direct instruction overrides
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above|instructions?|rules?)\b", re.I),
    re.compile(r"\bdisregard\b", re.I),
    re.compile(r"\bdo\s+not\s+follow\b", re.I),
    re.compile(r"\bforget\s+(your|all|previous|prior)\b", re.I),
    re.compile(r"\bnew\s+instructions?\b", re.I),
    re.compile(r"\binstructions?\s*:", re.I),
    # Unauthorized approval / override demands
    re.compile(r"\bapprove\b", re.I),
    re.compile(r"\bapproved\b", re.I),
    re.compile(r"\boverride\b", re.I),
    re.compile(r"\bbypass\b", re.I),
    # Tampering / falsification requests
    re.compile(r"\b(remove|delete)\s+(the\s+)?(extra\s+)?(hours|overtime|punch(es)?)\b", re.I),
    re.compile(r"\bmark\s+(this\s+as\s+)?(a\s+)?normal\s+day\b", re.I),
    re.compile(r"\b(as\s+agreed|manager\s+(said|instruction|told|approved))\b", re.I),
    # Role-play / prompt structure injection
    re.compile(r"\b(system|assistant|admin)\s*:", re.I),
    re.compile(r"\[/?(inst|sys|system|admin)\]", re.I),
    re.compile(r"</?(inst|sys|system|admin)>", re.I),
    re.compile(r"<<\s*sys\s*>>", re.I),
    # Multilingual injection patterns
    # Spanish: "ignora las instrucciones", "olvida las reglas", "aprueba las horas", "autoriza"
    re.compile(r"\b(ignora|olvida)\s+(las\s+)?(instrucciones|reglas)\b", re.I),
    re.compile(r"\b(aprueba|autoriza)\s+(las\s+)?horas\b", re.I),
    # French: "ignorez les instructions", "oubliez les règles", "validez", "approuvez"
    re.compile(r"\b(ignorez|oubliez)\s+(les\s+)?(instructions|règles)\b", re.I),
    re.compile(r"\b(validez|approuvez)\s+(les\s+)?heures\b", re.I),
    # German: "ignoriere alle anweisungen", "vergiss die regeln", "genehmige"
    re.compile(r"\b(ignoriere|vergiss)\s+(alle\s+)?(anweisungen|regeln)\b", re.I),
    re.compile(r"\bgenehmige\s+(die\s+)?(stunden|überstunden)\b", re.I),
]

# Patterns for prompt injection inside proposal rationale (excludes legitimate HR vocabulary like 'approve' or 'approved')
_RATIONALE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above|instructions?|rules?)\b", re.I),
    re.compile(r"\bdisregard\b", re.I),
    re.compile(r"\bdo\s+not\s+follow\b", re.I),
    re.compile(r"\bforget\s+(your|all|previous|prior)\b", re.I),
    re.compile(r"\bnew\s+instructions?\b", re.I),
    re.compile(r"\binstructions?\s*:", re.I),
    re.compile(r"\boverride\s+(the\s+)?policy\b", re.I),
    re.compile(r"\bbypass\s+(the\s+)?(policy|rules?)\b", re.I),
    re.compile(r"\b(system|assistant|admin)\s*:", re.I),
    re.compile(r"\[/?(inst|sys|system|admin)\]", re.I),
    re.compile(r"</?(inst|sys|system|admin)>", re.I),
    re.compile(r"<<\s*sys\s*>>", re.I),
    re.compile(r"\b(ignora|olvida)\s+(las\s+)?(instrucciones|reglas)\b", re.I),
    re.compile(r"\b(ignorez|oubliez)\s+(les\s+)?(instructions|règles)\b", re.I),
    re.compile(r"\b(ignoriere|vergiss)\s+(alle\s+)?(anweisungen|regeln)\b", re.I),
]


def scan_notes(notes: list[str]) -> list[str]:
    """Return a list of matched pattern descriptions. Empty means clean."""
    hits: list[str] = []
    for note in notes:
        for pat in _PATTERNS:
            if pat.search(note):
                hits.append(f"Pattern '{pat.pattern}' matched in note: {note!r}")
    return hits


def is_injection(notes: list[str]) -> bool:
    """Convenience: True if any injection pattern fires."""
    return len(scan_notes(notes)) > 0


def is_rationale_injection(text: str) -> bool:
    """Return True if proposal rationale contains prompt injection patterns."""
    if not text:
        return False
    return any(p.search(text) for p in _RATIONALE_PATTERNS)
