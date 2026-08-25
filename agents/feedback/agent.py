"""FeedbackAgent — turns the four criterion scores into written team feedback.

v0.7.0: given a submission's four criterion scores + their per-criterion
justifications (which already cite specific submission content), the
weighted composite, and whether the team is shortlisted, this agent
produces a short structured response:

- ``strengths``  — evidence-citing bullets (what the team did well)
- ``weaknesses`` — evidence-citing bullets (where it falls short)
- ``suggestion`` — exactly ONE concrete actionable improvement
- ``verdict``    — "shortlist" | "reject" (accept/reject framing)

Tone adapts to the shortlist decision: detailed and forward-looking for
shortlisted teams, encouraging and constructive for rejected ones.

This is an independent, narrowly-scoped module like the scoring
specialists — same Groq client seam, rate-limit backoff via a ``_sleep``
indirection tests can patch, strict JSON validation with corrective
re-prompting, and Unicode-dash normalization on everything stored.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from groq import APIConnectionError, AsyncGroq, RateLimitError

from agents.parsing.extractor import normalize_unicode_dashes
from version import APP_VERSION

# Provenance persisted with every feedback row: identifies the release
# whose feedback logic produced it. Derived from the project-wide
# version — bump version.py, never this string directly.
AGENT_VERSION = f"v{APP_VERSION}"

# Same model/retry posture as the scoring specialists (single free-tier
# model across all text stages).
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0

# The only verdict values accepted from (and ever persisted for) the
# model — validated case-insensitively.
VALID_VERDICTS = ("shortlist", "reject")


@dataclass
class FeedbackResult:
    """The complete generated feedback for one submission."""

    submission_id: str
    strengths: list[str]
    weaknesses: list[str]
    suggestion: str
    verdict: str
    agent_version: str = AGENT_VERSION


def _get_async_groq_client(api_key: str) -> AsyncGroq:
    """Create an async Groq client.

    Separated into its own function so tests can mock it.
    """
    return AsyncGroq(api_key=api_key)


async def _sleep(seconds: float) -> None:
    """Indirect asyncio.sleep so tests can patch waits without touching
    the global asyncio module."""
    await asyncio.sleep(seconds)


def _clean(value: Any) -> str:
    """Strip + normalize Unicode dashes on any text destined for storage."""
    return normalize_unicode_dashes(str(value).strip())


def _format_scores(scores: list[dict[str, Any]]) -> str:
    """Render the criterion rows shown to the model."""
    lines = []
    for row in scores:
        lines.append(
            f"- {row['criterion']}: {row['score']}/10 - {row['justification']}"
        )
    return "\n".join(lines)


class FeedbackAgent:
    """Generates written team feedback from specialist scores."""

    # --- Prompts ------------------------------------------------------

    def system_prompt(self) -> str:
        """System prompt fixing the output contract and tone rules."""
        return """You are an expert hackathon judge writing the official feedback a team receives after evaluation.

You will receive the team name, their four criterion scores with per-criterion justifications written by specialist judges (these justifications cite specific content from the submission), the weighted composite score, the team's rank, and whether they were shortlisted.

Write feedback that a real evaluator could send to the team:
- "strengths": 2-4 short bullets. EACH must reference specific evidence drawn from the justifications or scores - never generic praise.
- "weaknesses": 2-3 short bullets. EACH must reference specific evidence - never generic criticism.
- "suggestion": exactly ONE concrete, actionable improvement the team could make next time.
- "verdict": "shortlist" or "reject", consistent with the shortlisted flag you are given.

Tone rules: if the team is shortlisted, be detailed, precise, and forward-looking (what would make this win). If not shortlisted, be encouraging and constructive - acknowledge genuine strengths before the gaps.

Respond with ONLY valid JSON in this exact format:
{"strengths": ["<bullet>", "..."], "weaknesses": ["<bullet>", "..."], "suggestion": "<one actionable improvement>", "verdict": "shortlist"}

Do not include any text outside the JSON. Every bullet must be non-empty and grounded in the provided justifications."""

    def user_message(
        self,
        *,
        team_name: str,
        scores: list[dict[str, Any]],
        composite_score: float,
        rank: int | None,
        total_scored: int | None,
        shortlisted: bool,
    ) -> str:
        """User message carrying the full evaluation context."""
        rank_text = (
            f"rank {rank} of {total_scored} scored submissions"
            if rank is not None
            else "an unscored pool"
        )
        shortlist_text = (
            "YES - this team IS shortlisted"
            if shortlisted
            else "NO - this team is NOT shortlisted"
        )
        return (
            f"Team name: {team_name}\n\n"
            "Criterion scores (score/10 with the specialist's justification):\n"
            f"{_format_scores(scores)}\n\n"
            f"Weighted composite score: {composite_score}\n"
            f"Standing: {rank_text}\n"
            f"Shortlisted: {shortlist_text}\n\n"
            "Write this team's feedback and return valid JSON."
        )

    # --- Response validation ------------------------------------------

    def parse_feedback(self, json_str: str, submission_id: str) -> FeedbackResult:
        """Parse and validate the JSON response into a FeedbackResult.

        Raises ``json.JSONDecodeError`` if the text is not JSON at all,
        ``TypeError`` if a value has the wrong type, and ``ValueError``
        for missing/empty/invalid content. All three are retryable by
        :meth:`generate`.
        """
        data = json.loads(json_str)

        if not isinstance(data, dict):
            raise TypeError("Response is not a JSON object")

        missing = [
            key
            for key in ("strengths", "weaknesses", "suggestion", "verdict")
            if key not in data
        ]
        if missing:
            raise ValueError(f"Missing required field(s): {missing}")

        bullets: dict[str, list[str]] = {}
        for key in ("strengths", "weaknesses"):
            raw_list = data[key]
            if not isinstance(raw_list, list):
                raise TypeError(f"'{key}' must be a list of strings")
            cleaned = [_clean(item) for item in raw_list]
            if not cleaned or any(not item for item in cleaned):
                raise ValueError(f"'{key}' must contain non-empty strings")
            bullets[key] = cleaned

        raw_suggestion = data["suggestion"]
        # bool is an int subclass in Python - guard it like the scorers do.
        if isinstance(raw_suggestion, bool) or not isinstance(raw_suggestion, str):
            raise TypeError("'suggestion' must be a string")
        suggestion = _clean(raw_suggestion)
        if not suggestion:
            raise ValueError("'suggestion' must be non-empty")

        raw_verdict = data["verdict"]
        if not isinstance(raw_verdict, str):
            raise TypeError("'verdict' must be a string")
        verdict = _clean(raw_verdict).lower()
        if verdict not in VALID_VERDICTS:
            raise ValueError(
                f"'verdict' must be one of {list(VALID_VERDICTS)}, got {raw_verdict!r}"
            )

        return FeedbackResult(
            submission_id=submission_id,
            strengths=bullets["strengths"],
            weaknesses=bullets["weaknesses"],
            suggestion=suggestion,
            verdict=verdict,
        )

    # --- Groq interaction ---------------------------------------------

    async def _call_groq(
        self,
        client: AsyncGroq,
        system_prompt: str,
        user_message: str,
        max_retries: int = MAX_RETRIES,
    ) -> str:
        """Call the Groq API with retry/backoff for rate limits.

        Retries on ``RateLimitError`` (HTTP 429) and
        ``APIConnectionError`` (network issues) with exponential backoff.
        Other errors propagate immediately. Returns the raw content.
        """
        backoff = INITIAL_BACKOFF
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.chat.completions.create(
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
                    await _sleep(backoff)
                    backoff *= 2
                else:
                    raise
            except Exception:
                # Non-retryable errors (auth, bad request, etc.) propagate.
                raise

        # Should never reach here, but just in case.
        raise last_error  # type: ignore[misc]

    async def generate(
        self,
        client: AsyncGroq,
        *,
        submission_id: str,
        team_name: str,
        scores: list[dict[str, Any]],
        composite_score: float,
        shortlisted: bool,
        rank: int | None = None,
        total_scored: int | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> FeedbackResult:
        """Run this agent end-to-end: call Groq, validate, recover.

        Malformed responses are retried with a corrective re-prompt
        (mirroring the scoring agents); rate limits are retried inside
        :meth:`_call_groq`. Raises ``RuntimeError`` when valid output
        never arrives.
        """
        system_prompt = self.system_prompt()
        user_message = self.user_message(
            team_name=team_name,
            scores=scores,
            composite_score=composite_score,
            rank=rank,
            total_scored=total_scored,
            shortlisted=shortlisted,
        )

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_response = await self._call_groq(
                    client, system_prompt, user_message
                )
                return self.parse_feedback(raw_response, submission_id)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                last_error = exc
                if attempt < max_retries:
                    # Re-prompt with a correction message.
                    user_message = (
                        "Your previous response was not valid JSON or was "
                        "missing/invalid required fields. Please respond "
                        "with ONLY valid JSON in the exact format specified: "
                        '{"strengths": [...], "weaknesses": [...], '
                        '"suggestion": "...", "verdict": "shortlist"}. '
                        'The verdict must be "shortlist" or "reject". '
                        f"Here is the evaluation context again:\n\n{user_message}"
                    )
                    await _sleep(INITIAL_BACKOFF)
                else:
                    raise RuntimeError(
                        f"Failed to get valid feedback JSON from Groq after "
                        f"{max_retries + 1} attempts for submission "
                        f"'{submission_id}': {exc}"
                    ) from exc

        raise last_error  # type: ignore[misc]


async def generate_feedback(
    *,
    submission_id: str,
    team_name: str,
    scores: list[dict[str, Any]],
    composite_score: float,
    shortlisted: bool,
    rank: int | None = None,
    total_scored: int | None = None,
    groq_api_key: str | None = None,
) -> FeedbackResult:
    """Generate feedback for one scored submission.

    Args:
        submission_id: The UUID of the submission being reviewed.
        team_name: The team's name (used in the prompt).
        scores: The four score rows (``criterion``, ``score``,
            ``justification``), ideally in canonical CRITERIA_NAMES order.
        composite_score: Weighted composite from the ranking engine.
        shortlisted: Whether the team made the current shortlist cutoff.
        rank: The team's leaderboard rank (1-based), when known.
        total_scored: How many submissions were ranked in total.
        groq_api_key: Optional API key. If not provided, reads from
            the ``GROQ_API_KEY`` environment variable.

    Returns:
        A :class:`FeedbackResult`.

    Raises:
        ValueError: If the Groq API key is not configured.
        RuntimeError: If valid JSON never arrives after all retries.
        RateLimitError: If Groq rate-limits beyond all retries (a
            ``groq.GroqError`` subclass).
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Groq API key is not configured. Set GROQ_API_KEY in your .env file."
        )

    client = _get_async_groq_client(api_key)
    return await FeedbackAgent().generate(
        client,
        submission_id=submission_id,
        team_name=team_name,
        scores=scores,
        composite_score=composite_score,
        shortlisted=shortlisted,
        rank=rank,
        total_scored=total_scored,
    )
