"""Gemini vision descriptions for diagram-like images (v0.3.6).

Optional alternative to the default Groq/qwen describer. Selected via
``VISION_PROVIDER=gemini`` in `.env`; the default stays ``groq`` and
the qwen code path is untouched. Scoring/text stages always use Groq
regardless of this setting.

Talks to Google's documented REST endpoint through the project's
pinned ``httpx`` instead of the ``google-genai`` SDK: that SDK
requires ``httpx>=0.28``, which conflicts with ``supabase==2.9.0``'s
``httpx<0.28`` constraint — so no new dependency is introduced.

Retry policy mirrors the Groq describer: only HTTP 429 and transport
(connection/timeout) errors are retried, exponential backoff (1s
doubling, max 3 retries). Persistent rate limiting raises
``VisionRateLimitError`` so the pipeline's circuit breaker behaves
identically for both providers. All other errors propagate
immediately.

Gemini does not emit qwen-style reasoning blocks, but they are
stripped defensively anyway so stored text stays clean even if
provider behavior changes.
"""

from __future__ import annotations

import base64
import os
import time

import httpx

from agents.parsing.extractor import normalize_unicode_dashes
from agents.parsing.images.describe import (
    INITIAL_BACKOFF,
    MAX_RETRIES,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    VisionRateLimitError,
    _image_mime,
    _strip_think_blocks,
)

DESCRIBER_VERSION = "v0.3.6-gemini"
DEFAULT_GEMINI_VISION_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Mirrors the Groq retry policy exactly: quota exhaustion plus
# network-level failures. Every other HTTP status propagates at once.
_RETRYABLE_STATUS_CODES = frozenset({429})


def _get_http_client() -> httpx.Client:
    """Create an httpx client.

    Separated into its own function so tests can mock it.
    """
    return httpx.Client(timeout=60.0)


def _rate_limit_error(response: httpx.Response) -> VisionRateLimitError:
    """Build the circuit-breaker signal from a 429 response."""
    return VisionRateLimitError(f"Gemini rate limit hit (HTTP {response.status_code})")


def _extract_text(response: httpx.Response) -> str:
    """Join the first candidate's text parts into one description.

    Blocked or truncated responses (safety filter, empty candidates)
    surface as empty text so the caller treats them like any other
    unusable description.
    """
    data = response.json()
    candidates = data.get("candidates") or []
    texts: list[str] = []
    if candidates:
        content = candidates[0].get("content") or {}
        texts = [part.get("text", "") for part in (content.get("parts") or [])]
    return _strip_think_blocks("".join(texts))


def describe_image_gemini(
    image_bytes: bytes,
    api_key: str | None = None,
    model: str | None = None,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Return a plain-text structural description of the image via Gemini.

    Args:
        image_bytes: Raw image bytes.
        api_key: Optional API key. If not provided, reads from the
            ``GEMINI_API_KEY`` environment variable.
        model: Optional vision model override. If not provided, reads
            from ``GEMINI_VISION_MODEL`` (default ``gemini-2.5-flash``).
        max_retries: Number of retries for rate-limit/connection errors.

    Returns:
        The ASCII-normalized description text.

    Raises:
        ValueError: If the API key is missing or the model returns an
            empty description.
        VisionRateLimitError: If rate-limited after all retries.
        httpx.HTTPStatusError: For non-retryable HTTP error statuses.
        httpx.TransportError: If the connection fails after all retries.
    """
    key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise ValueError(
            "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
        )
    model = model or os.getenv("GEMINI_VISION_MODEL", DEFAULT_GEMINI_VISION_MODEL)

    b64 = base64.b64encode(image_bytes).decode()
    mime = _image_mime(image_bytes)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Describe this image."},
                    {"inlineData": {"mimeType": mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": MAX_TOKENS},
    }
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"

    client = _get_http_client()
    backoff = INITIAL_BACKOFF
    try:
        for attempt in range(max_retries + 1):
            try:
                response = client.post(
                    url,
                    json=payload,
                    headers={"x-goog-api-key": key},
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    raise _rate_limit_error(response)
                response.raise_for_status()
                description = _extract_text(response)
                if not description:
                    raise ValueError("Vision model returned an empty description")
                return normalize_unicode_dashes(description)
            except VisionRateLimitError:
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    raise
            except httpx.TransportError:
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    raise
    finally:
        client.close()
