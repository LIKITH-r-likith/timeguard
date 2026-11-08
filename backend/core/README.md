# backend/core (Person 1)

The deterministic brain of TimeGuard. Plain Python, no AI, no network.

```python
from backend.core.api import detect, validate, pay_impact, risk_tier, load_policy

policy = load_policy(timecard.jurisdiction)      # PolicyPack or None (unknown jurisdiction)
exceptions = detect(timecard, policy)            # list[ExceptionRecord]
result = validate(proposal, timecard, policy)    # ValidationResult with the 7 named checks
impact = pay_impact(before_card, after_card, policy)
tier = risk_tier(exception, proposal, impact)    # LOW / MEDIUM / HIGH
```

- Exception ids are stable: `exc_<timecard_id>_<TYPE>_<YYYY-MM-DD>`. validate() finds the target exception by this id.
- `validate()` applies the proposal to a copy and never changes the real timecard.
- Policy numbers are mock values. Clause lookup is by suffix (`OT-DAILY-01`), so new packs need no code.
- Tests: `python -m pytest backend/core -q`. Golden cases: `python evals/golden/generate_golden.py`.
