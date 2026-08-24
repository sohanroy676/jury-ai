"""Scoring package — four specialist agents + parallel orchestration.

v0.5.0: each criterion has its own narrow agent module; scorer.py fans
them out concurrently via asyncio.gather.
"""

from agents.scoring.base import (
    AGENT_VERSION,
    CRITERIA_NAMES,
    RUBRIC,
    CriterionScore,
    ScoringResult,
)
from agents.scoring.feasibility import FeasibilityAgent
from agents.scoring.innovation import InnovationAgent
from agents.scoring.problem_fit import ProblemFitAgent
from agents.scoring.scorer import score_submission
from agents.scoring.technical_depth import TechnicalDepthAgent

__all__ = [
    "AGENT_VERSION",
    "CRITERIA_NAMES",
    "RUBRIC",
    "CriterionScore",
    "FeasibilityAgent",
    "InnovationAgent",
    "ProblemFitAgent",
    "ScoringResult",
    "TechnicalDepthAgent",
    "score_submission",
]
