"""Vision-LLM structural descriptions for diagram-like images (v0.3.5).

Uses Groq's vision-capable model. ``qwen/qwen3.6-27b`` is the default —
verified vision-capable on this account's free tier (llama-4-scout is
NOT available there; groq/compound rejects multimodal content parts).

Retry policy mirrors the scoring agent: only ``RateLimitError`` (429)
and ``APIConnectionError`` are retried, with exponential backoff
(1s doubling, max 3 retries). All other errors propagate immediately.

qwen3.6 emits a reasoning block (an opening/closing "think" tag pair)
before its final answer; those blocks are stripped so only the
description text is stored.
"""

from __future__ import annotations

import base64
import os
import re
import time

from groq import APIConnectionError, Groq, RateLimitError

from agents.parsing.extractor import normalize_unicode_dashes

DESCRIBER_VERSION = "v0.3.5"
DEFAULT_VISION_MODEL = "qwen/qwen3.6-27b"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_DESCRIPTION_WORDS = 150
# Generous budget: qwen3.6 reasons before answering, and a reasoning
# block cut off by the token limit means no usable description at all.
MAX_TOKENS = 2048

# qwen-style reasoning blocks to strip from responses. Handles BOTH a
# closed block and one cut off by the token limit (opening tag with no
# closer -> strip everything from the opening tag to the end). Built
# via concatenation because literal XML-looking tags do not survive
# being written into source files.
_THINK_TAG = "think"
_THINK_RE = re.compile(
    "<" + _THINK_TAG + r">.*?</" + _THINK_TAG + r">|<" + _THINK_TAG + r">.*\Z",
    re.DOTALL,
)

SYSTEM_PROMPT = (
    "You are a technical diagram analyst. You will be shown one image "
    "extracted from a hackathon submission. Describe its structure "
    "concisely: what the diagram, chart, or flowchart shows, its main "
    "components, how they connect, and any direction of flow or visible "
    "labels. Do not speculate about content you cannot see. Respond with "
    f"at most {MAX_DESCRIPTION_WORDS} words of plain text."
)


def _get_groq_client(api_key: str) -> Groq:
    """Create a Groq client.

    Separated into its own function so tests can mock it.
    """
    return Groq(api_key=api_key)


def _strip_think_blocks(text: str) -> str:
    """Remove qwen-style reasoning from a response."""
    return _THINK_RE.sub("", text).strip()


def _image_mime(image_bytes: bytes) -> str:
    """Best-effort MIME detection from magic bytes (defaults to PNG)."""
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return "image/png"


def describe_image(
    image_bytes: bytes,
    groq_api_key: str | None = None,
    model: str | None = None,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Return a plain-text structural description of the image.

    Args:
        image_bytes: Raw image bytes.
        groq_api_key: Optional API key. If not provided, reads from the
            ``GROQ_API_KEY`` environment variable.
        model: Optional vision model override. If not provided, reads
            from ``GROQ_VISION_MODEL`` (default ``qwen/qwen3.6-27b``).
        max_retries: Number of retries for rate-limit/connection errors.

    Returns:
        The ASCII-normalized description text.

    Raises:
        ValueError: If the API key is missing or the model returns an
            empty description.
        RateLimitError: If rate-limited after all retries.
        APIConnectionError: If the connection fails after all retries.
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Groq API key is not configured. Set GROQ_API_KEY in your .env file."
        )
    model = model or os.getenv("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)

    b64 = base64.b64encode(image_bytes).decode()
    mime = _image_mime(image_bytes)
    client = _get_groq_client(api_key)

    backoff = INITIAL_BACKOFF
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    },
                ],
                max_tokens=MAX_TOKENS,
                temperature=0.2,
            )
            description = _strip_think_blocks(response.choices[0].message.content or "")
            if not description:
                raise ValueError("Vision model returned an empty description")
            return normalize_unicode_dashes(description)
        except (RateLimitError, APIConnectionError):
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise
