"""Person 1's public interface. Others import ONLY from here:

    from backend.core.api import detect, validate, pay_impact, risk_tier, load_policy

Signatures follow the team contract. Do not rename them.
"""

from backend.core.pay import pay_impact
from backend.core.policy import load_policy
from backend.core.risk import risk_tier
from backend.core.rules import detect, exception_id
from backend.core.validator import validate

__all__ = ["detect", "validate", "pay_impact", "risk_tier", "load_policy", "exception_id"]
