"""Scoring agent — evaluates parsed submission text against a rubric.

Uses Groq's API (openai/gpt-oss-120b) to score a submission across
four criteria: problem_fit, technical_depth, feasibility, innovation.
Each criterion is scored 1-10 with a justification string.

This is the v0.3.0 single-agent implementation — one Groq call scores
all four criteria at once. The four-agent split comes in v0.5.0.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from groq import APIConnectionError, Groq, RateLimitError

from agents.parsing.extractor import normalize_unicode_dashes

AGENT_VERSION = "v0.3.0"
# llama-3.3-70b-versatile was deprecated/removed from Groq's free tier;
# openai/gpt-oss-120b is the roadmap's listed alternative and is available.
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0

# Hardcoded rubric: 4 criteria, each scored 1-10.
RUBRIC: dict[str, Any] = {
    "criteria": [
        {
            "name": "problem_fit",
            "description": (
                "How well does the solution address a real, significant problem? "
                "Is the problem clearly identified and compelling?"
            ),
        },
        {
            "name": "technical_depth",
            "description": (
                "How sophisticated is the technical implementation? Does it "
                "demonstrate solid engineering, appropriate tech choices, and "
                "depth of execution?"
            ),
        },
        {
            "name": "feasibility",
            "description": (
                "Is the solution realistic and achievable within the constraints "
                "of a hackathon? Could it be built and deployed as described?"
            ),
        },
        {
            "name": "innovation",
            "description": (
                "How novel and creative is the solution? Does it offer a fresh "
                "approach or meaningful improvement over existing solutions?"
            ),
        },
    ],
    "score_range": {"min": 1, "max": 10},
}

CRITERIA_NAMES = [c["name"] for c in RUBRIC["criteria"]]


@dataclass
class CriterionScore:
    """A single criterion's score and justification."""

    criterion: str
    score: int
    justification: str


@dataclass
class ScoringResult:
    """The complete scoring result for one submission."""

    submission_id: str
    scores: list[CriterionScore]
    agent_version: str = AGENT_VERSION


def _build_system_prompt() -> str:
    """Build the system prompt that describes the rubric and output format."""
    criteria_desc = "\n".join(
        f"  - {c['name']}: {c['description']}" for c in RUBRIC["criteria"]
    )
    return f"""You are an expert hackathon evaluator. Score the submission text provided by the user against the following rubric.

Rubric (score each criterion 1-10, where 1 is very poor and 10 is excellent):
{criteria_desc}

Respond with ONLY valid JSON in this exact format:
{{
    "problem_fit": {{"score": <int 1-10>, "justification": "<string>"}},
    "technical_depth": {{"score": <int 1-10>, "justification": "<string>"}},
    "feasibility": {{"score": <int 1-10>, "justification": "<string>"}},
    "innovation": {{"score": <int 1-10>, "justification": "<string>"}}
}}

Do not include any text outside the JSON. Each justification must be non-empty and reference specific content from the submission."""


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


def _build_user_message(parsed_text: str) -> str:
    """Build the user message containing the parsed submission text."""
    return f"""Here is the parsed text from the hackathon submission:

---BEGIN SUBMISSION TEXT---
{parsed_text}
---END SUBMISSION TEXT---

Score this submission against the rubric and return valid JSON."""


def _get_groq_client(api_key: str) -> Groq:
    """Create a Groq client.

    Separated into its own function so tests can mock it.
    """
    return Groq(api_key=api_key)


def _call_groq(
    client: Groq,
    system_prompt: str,
    user_message: str,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Call the Groq API with retry/backoff for rate limits.

    Retries on ``RateLimitError`` (HTTP 429) and ``APIConnectionError``
    (network issues) with exponential backoff. Other errors propagate
    immediately.

    Returns the raw response content string.
    """
    backoff = INITIAL_BACKOFF
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return response.choices[0].message.content
        except (RateLimitError, APIConnectionError) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise
        except Exception:
            # Non-retryable errors (auth, bad request, etc.) propagate.
            raise

    # Should never reach here, but just in case.
    raise last_error  # type: ignore[misc]


def _parse_scores(json_str: str) -> list[CriterionScore]:
    """Parse and validate the JSON response from Groq.

    Raises ``ValueError`` if the JSON is malformed or missing criteria.
    Raises ``TypeError`` if the response structure is not as expected.
    """
    data = json.loads(json_str)

    if not isinstance(data, dict):
        raise TypeError("Response is not a JSON object")

    scores: list[CriterionScore] = []
    for name in CRITERIA_NAMES:
        if name not in data:
            raise ValueError(f"Missing criterion '{name}' in response")
        entry = data[name]
        if not isinstance(entry, dict):
            raise TypeError(f"Criterion '{name}' is not a dict")
        if "score" not in entry or "justification" not in entry:
            raise ValueError(f"Criterion '{name}' missing score or justification")
        score = int(entry["score"])
        if score < 1 or score > 10:
            raise ValueError(f"Score for '{name}' is {score}, must be 1-10")
        justification = normalize_unicode_dashes(str(entry["justification"]).strip())
        if not justification:
            raise ValueError(f"Justification for '{name}' is empty")
        scores.append(
            CriterionScore(criterion=name, score=score, justification=justification)
        )

    return scores


def score_submission(
    submission_id: str,
    parsed_text: str,
    groq_api_key: str | None = None,
) -> ScoringResult:
    """Score a parsed submission using the Groq API.

    Args:
        submission_id: The UUID of the submission being scored.
        parsed_text: The raw extracted text from the parsing agent.
        groq_api_key: Optional API key. If not provided, reads from
            the ``GROQ_API_KEY`` environment variable.

    Returns:
        A :class:`ScoringResult` with 4 :class:`CriterionScore` objects.

    Raises:
        ValueError: If the Groq API key is not configured.
        RuntimeError: If scoring fails after all retries (malformed JSON).
        RateLimitError: If Groq rate-limits after all retries.
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Groq API key is not configured. Set GROQ_API_KEY in your .env file."
        )

    client = _get_groq_client(api_key)
    system_prompt = _build_system_prompt()
    user_message = _build_user_message(parsed_text)

    # Try to get valid JSON from Groq, with retry on malformed output.
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw_response = _call_groq(client, system_prompt, user_message)
            scores = _parse_scores(raw_response)
            return ScoringResult(
                submission_id=submission_id,
                scores=scores,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                # Re-prompt with a correction message.
                user_message = (
                    "Your previous response was not valid JSON or was "
                    "missing required fields. Please respond with ONLY "
                    "valid JSON in the exact format specified. "
                    f"Here is the submission text again:\n\n{parsed_text}"
                )
                time.sleep(INITIAL_BACKOFF)
            else:
                raise RuntimeError(
                    f"Failed to get valid JSON from Groq after "
                    f"{MAX_RETRIES + 1} attempts: {exc}"
                ) from exc

    raise last_error  # type: ignore[misc]
