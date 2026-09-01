"""Shared plumbing for the v0.5.0 specialist scoring agents.

Each criterion is scored by its own narrow agent module
(problem_fit.py, technical_depth.py, feasibility.py,
innovation.py). This module holds everything they share --
result types, the rubric, Groq client creation, retry/backoff,
and response validation -- so no agent duplicates it.

The four agents run concurrently against ONE shared AsyncGroq
client; per-agent retries use asyncio.sleep backoff.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, ClassVar

from groq import APIConnectionError, AsyncGroq, RateLimitError

from agents.parsing.extractor import normalize_unicode_dashes
from version import APP_VERSION

AGENT_VERSION = f"v{APP_VERSION}"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0

RUBRIC: dict[str, Any] = {
    "criteria": [
        {
            "name": "problem_fit",
            "description": (
                "How well does the solution address a real, significant "
                "problem? Is the problem clearly identified and compelling?"
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

_RUBRIC_BY_NAME: dict[str, str] = {
    c["name"]: c["description"] for c in RUBRIC["criteria"]
}


@dataclass
class CriterionScore:
    """A single criterion's score, justification, and citation (v2.3.0)."""

    criterion: str
    score: int
    justification: str
    cited_excerpt: str = ""


@dataclass
class ScoringResult:
    """The complete scoring result for one submission."""

    submission_id: str
    scores: list[CriterionScore]
    agent_version: str = AGENT_VERSION


def _get_async_groq_client(api_key: str) -> AsyncGroq:
    """Create an async Groq client.

    Separated into its own function so tests can mock it. One client is
    shared by all four agents of a run (it pools HTTP connections).
    """
    return AsyncGroq(api_key=api_key)


async def _sleep(seconds: float) -> None:
    """Indirect asyncio.sleep so tests can patch waits without touching
    the global asyncio module."""
    await asyncio.sleep(seconds)


class SpecialistAgent:
    """Base class for the four specialist scoring agents."""

    criterion: ClassVar[str] = ""
    guidance: ClassVar[tuple[str, ...]] = ()

    @property
    def focus(self) -> str:
        """The criterion description from the rubric."""
        return _RUBRIC_BY_NAME[self.criterion]

    def system_prompt(self) -> str:
        """System prompt fixing the output contract."""
        guidance_block = ""
        if self.guidance:
            guidance_block = "\n\nFocus areas:\n" + "\n".join(
                f"- {line}" for line in self.guidance
            )
        return f"""You are an expert hackathon evaluator focused on ONE criterion only: {self.criterion}.

Criterion definition (score 1-10, where 1 is very poor and 10 is excellent):
{self.focus}{guidance_block}

Ignore every other aspect of the submission - other specialists cover them.

Respond with ONLY valid JSON in this exact format:
{{"{self.criterion}": {{"score": <int 1-10>, "justification": "<string>", "cited_excerpt": "<string>"}}}}

The cited_excerpt MUST be a direct quote or section/slide reference from the submission that supports the score. If no clearly relevant section exists, set cited_excerpt to an empty string and explain why in the justification. Do not fabricate citations. Do not include any text outside the JSON. The justification must be non-empty and reference specific content from the submission."""

    def user_message(self, parsed_text: str) -> str:
        """User message containing the parsed submission text."""
        return f"""Here is the parsed text from the hackathon submission:

---BEGIN SUBMISSION TEXT---
{parsed_text}
---END SUBMISSION TEXT---

Score this submission on '{self.criterion}' and return valid JSON."""

    # --- Response validation ------------------------------------------

    def parse_score(self, json_str: str) -> CriterionScore:
        """Parse and validate the JSON response for THIS criterion.

        Raises ``ValueError`` if the JSON is malformed or missing this
        agent's criterion, ``TypeError`` if the structure is wrong, and
        ``json.JSONDecodeError`` if the text is not JSON at all. All three
        are retryable by :meth:`score`.
        """
        data = json.loads(json_str)

        if not isinstance(data, dict):
            raise TypeError("Response is not a JSON object")

        if self.criterion not in data:
            raise ValueError(f"Missing criterion '{self.criterion}' in response")

        entry = data[self.criterion]
        if not isinstance(entry, dict):
            raise TypeError(f"Criterion '{self.criterion}' is not a dict")
        if "score" not in entry or "justification" not in entry:
            raise ValueError(
                f"Criterion '{self.criterion}' missing score or justification"
            )

        raw_score = entry["score"]
        if isinstance(raw_score, bool):
            raise TypeError(
                f"Score for '{self.criterion}' must be an integer, got boolean"
            )
        score = int(raw_score)
        if score < 1 or score > 10:
            raise ValueError(f"Score for '{self.criterion}' is {score}, must be 1-10")

        justification = normalize_unicode_dashes(str(entry["justification"]).strip())
        if not justification:
            raise ValueError(f"Justification for '{self.criterion}' is empty")

        # v2.3.0: cited_excerpt is optional -- agents may return empty string
        # when no clearly relevant section exists for the criterion.
        raw_citation = entry.get("cited_excerpt", "")
        cited_excerpt = (
            normalize_unicode_dashes(str(raw_citation).strip())
            if raw_citation
            else ""
        )

        return CriterionScore(
            criterion=self.criterion,
            score=score,
            justification=justification,
            cited_excerpt=cited_excerpt,
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

    async def score(
        self,
        client: AsyncGroq,
        parsed_text: str,
        max_retries: int = MAX_RETRIES,
    ) -> CriterionScore:
        """Run this agent end-to-end: call Groq, validate, recover.

        Malformed responses are retried with a corrective re-prompt
        (mirroring v0.3.0 semantics); rate limits are retried inside
        :meth:`_call_groq`. Raises ``RuntimeError`` when valid output
        never arrives.
        """
        system_prompt = self.system_prompt()
        user_message = self.user_message(parsed_text)

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_response = await self._call_groq(
                    client, system_prompt, user_message
                )
                return self.parse_score(raw_response)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                last_error = exc
                if attempt < max_retries:
                    # Re-prompt with a correction message.
                    user_message = (
                        "Your previous response was not valid JSON or was "
                        "missing required fields. Please respond with ONLY "
                        "valid JSON in the exact format specified for "
                        f"criterion '{self.criterion}' (including the "
                        "cited_excerpt field). "
                        f"Here is the submission text again:\n\n{parsed_text}"
                    )
                    await _sleep(INITIAL_BACKOFF)
                else:
                    raise RuntimeError(
                        f"Failed to get valid JSON from Groq after "
                        f"{max_retries + 1} attempts for criterion "
                        f"'{self.criterion}': {exc}"
                    ) from exc

        raise last_error  # type: ignore[misc]
