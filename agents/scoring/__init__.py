"""Scoring agent — evaluates parsed submission text against a rubric."""

from agents.scoring.scorer import (
    AGENT_VERSION,
    RUBRIC,
    CriterionScore,
    ScoringResult,
    score_submission,
)

__all__ = [
    "AGENT_VERSION",
    "RUBRIC",
    "CriterionScore",
    "ScoringResult",
    "score_submission",
]
