"""Offline helpers for assessing claims under Regulation (EC) No 261/2004."""

from .eligibility import ClaimInputs, DisruptionType, Verdict, evaluate_claim

__all__ = ["ClaimInputs", "DisruptionType", "Verdict", "evaluate_claim"]
__version__ = "0.1.0"
