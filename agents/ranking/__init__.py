"""Ranking package — weighted composites, ordering, shortlisting (v0.6.0)."""

from agents.ranking.engine import (
    COMPOSITE_DECIMALS,
    DEFAULT_WEIGHTS,
    SUM_TOLERANCE,
    TIE_BREAK_CRITERION,
    TIE_EPSILON,
    RankedSubmission,
    WeightValidationError,
    build_ranking,
    compute_composite,
    validate_weights,
)

__all__ = [
    "COMPOSITE_DECIMALS",
    "DEFAULT_WEIGHTS",
    "SUM_TOLERANCE",
    "TIE_BREAK_CRITERION",
    "TIE_EPSILON",
    "RankedSubmission",
    "WeightValidationError",
    "build_ranking",
    "compute_composite",
    "validate_weights",
]
