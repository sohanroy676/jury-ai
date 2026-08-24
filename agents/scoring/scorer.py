"""Scoring orchestration — fans the four specialist agents out in parallel.

v0.5.0: the single multi-criteria prompt is replaced by four independent,
narrowly-scoped agents (problem_fit.py, technical_depth.py, feasibility.py,
innovation.py). They run concurrently against ONE shared AsyncGroq client;
each agent owns its prompt, rate-limit backoff, and malformed-response
recovery (see base.py).

This module is also the package's stable facade: the public names that
backend routes and tests import (CriterionScore, ScoringResult,
AGENT_VERSION, RUBRIC, CRITERIA_NAMES, score_submission,
build_scoring_text) are defined or re-exported here so existing import
paths keep working unchanged.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agents.scoring.base import (
    AGENT_VERSION,
    CRITERIA_NAMES,
    RUBRIC,
    CriterionScore,
    ScoringResult,
    SpecialistAgent,
    _get_async_groq_client,
)
from agents.scoring.feasibility import FeasibilityAgent
from agents.scoring.innovation import InnovationAgent
from agents.scoring.problem_fit import ProblemFitAgent
from agents.scoring.technical_depth import TechnicalDepthAgent

# Facade surface: these re-exports are the package's stable import path
# (backend routes/tests import from agents.scoring.scorer).
__all__ = [
    "AGENT_VERSION",
    "CRITERIA_NAMES",
    "RUBRIC",
    "CriterionScore",
    "FeasibilityAgent",
    "InnovationAgent",
    "ProblemFitAgent",
    "ScoringResult",
    "SpecialistAgent",
    "TechnicalDepthAgent",
    "build_scoring_text",
    "build_specialist_agents",
    "score_submission",
]


def build_specialist_agents() -> list[SpecialistAgent]:
    """Return fresh instances of the four scoring specialists."""
    return [
        ProblemFitAgent(),
        TechnicalDepthAgent(),
        FeasibilityAgent(),
        InnovationAgent(),
    ]


async def score_submission(
    submission_id: str,
    parsed_text: str,
    groq_api_key: str | None = None,
) -> ScoringResult:
    """Score a parsed submission with the four specialists in parallel.

    All four agents run concurrently via ``asyncio.gather`` against one
    shared client — four simultaneous requests sit far below Groq's ~30
    RPM free-tier limit, so no artificial staggering is applied; each
    agent's own backoff handles transient 429s.

    Fail-closed: if ANY agent fails after its retries, the whole run
    raises and no partial scores are returned — composite ranking
    (v0.6.0) needs all four criteria.

    Args:
        submission_id: The UUID of the submission being scored.
        parsed_text: The scoring-ready text (raw extracted text with
            image descriptions merged in — see :func:`build_scoring_text`).
        groq_api_key: Optional API key. If not provided, reads from
            the ``GROQ_API_KEY`` environment variable.

    Returns:
        A :class:`ScoringResult` with 4 :class:`CriterionScore` objects,
        ordered canonically by ``CRITERIA_NAMES`` regardless of task
        completion order.

    Raises:
        ValueError: If the Groq API key is not configured.
        RuntimeError: If an agent fails to produce valid JSON after all
            retries.
        RateLimitError: If Groq rate-limits an agent beyond all retries
            (a ``groq.GroqError`` subclass).
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Groq API key is not configured. Set GROQ_API_KEY in your .env file."
        )

    client = _get_async_groq_client(api_key)
    results = await asyncio.gather(
        *(agent.score(client, parsed_text) for agent in build_specialist_agents()),
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        # Deterministic surface: the first failure in canonical agent order.
        raise failures[0]

    by_criterion = {score.criterion: score for score in results}
    return ScoringResult(
        submission_id=submission_id,
        scores=[by_criterion[name] for name in CRITERIA_NAMES],
    )


def build_scoring_text(
    raw_text: str, image_descriptions: list[dict[str, Any]] | None
) -> str:
    """Combine raw text and image descriptions into the scoring input.

    v0.3.5: image descriptions are appended as a delimited section so
    the scoring prompts themselves need no changes. When there are no
    descriptions (no images, or understanding skipped/failed), the raw
    text is returned unchanged.
    """
    if not image_descriptions:
        return raw_text

    lines = [raw_text, "", "---IMAGE DESCRIPTIONS---"]
    for entry in image_descriptions:
        page = entry.get("page", "?")
        classification = entry.get("classification") or "image"
        description = entry.get("description")
        if description:
            lines.append(f"[Page/slide {page}] ({classification}): {description}")
        else:
            lines.append(
                f"[Page/slide {page}] ({classification}): "
                "(image present but not yet described - pending human review)"
            )
    return chr(10).join(lines)
