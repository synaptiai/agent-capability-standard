"""
OASF compatibility adapters for the Grounded Agency SDK.

Provides translation between OASF skill codes and Grounded Agency capabilities,
enabling systems built on OASF to leverage Grounded Agency's safety guarantees.
"""

from __future__ import annotations

from .oasf import OASFAdapter, OASFMapping, OASFSkillResult, UnknownSkillError

__all__ = [
    "OASFAdapter",
    "OASFMapping",
    "OASFSkillResult",
    "UnknownSkillError",
]
