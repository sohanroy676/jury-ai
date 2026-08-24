"""Image-understanding pipeline (v0.3.5).

Orchestrates: dedupe -> cache lookup -> CLIP classify -> three-tier
routing -> vision describe -> cache write.

Database access is injected via callables so this module — and the
agents layer as a whole — never touches Supabase directly. Passing
``None`` for either callable runs fully offline (no caching).

Three-tier routing per the roadmap (v0.3.6 refinement):
  - high-confidence diagram/flowchart/chart -> vision description
  - decorative-labeled, ANY confidence       -> dropped, nothing stored,
    no vision call, not cached (genuine diagrams mislabeled as
    decorative are rescued upstream in classify.py via the
    diagram-floor relabel)
  - other low-confidence / ambiguous         -> vision description tagged
    ``needs_human_review=True``

Failure semantics (graceful degradation):
  - a per-image failure never aborts the run; it only affects that image
  - classification failure -> image skipped entirely
  - description failure    -> entry kept with ``description=None`` and
    ``needs_human_review=True`` so the signal isn't lost; failures are
    NOT cached so a later submission can retry them
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from groq import RateLimitError

from agents.parsing.images.classify import DECORATIVE_LABELS, classify_image
from agents.parsing.images.dedupe import DEFAULT_PHASH_THRESHOLD, dedupe_images
from agents.parsing.images.describe import describe_image
from agents.parsing.images.describe_gemini import describe_image_gemini
from agents.parsing.images.extract import ExtractedImage

logger = logging.getLogger(__name__)

# Injected dependency types.
CacheGet = Callable[[str], dict | None]
CachePut = Callable[[str, str, float, str | None], None]
ClassifyFn = Callable[[bytes], tuple[str, float]]
DescribeFn = Callable[[bytes], str]

# Vision describer selection (v0.3.6): VISION_PROVIDER=groq|gemini in
# .env picks the default describer; the default stays groq and the
# scoring/text stages are unaffected either way.
DEFAULT_VISION_PROVIDER = "groq"
VALID_VISION_PROVIDERS = ("groq", "gemini")


def _resolve_default_describer() -> DescribeFn:
    """Return the describer selected by ``VISION_PROVIDER``.

    Used only when no explicit ``describe_fn`` is injected. Unknown
    values fail fast with the accepted options listed.
    """
    provider = os.getenv("VISION_PROVIDER", DEFAULT_VISION_PROVIDER).strip().lower()
    if provider == "groq":
        return describe_image
    if provider == "gemini":
        return describe_image_gemini
    raise ValueError(
        f"Unsupported VISION_PROVIDER {provider!r}. Expected one of: "
        + ", ".join(VALID_VISION_PROVIDERS)
    )


def process_submission_images(
    images: list[ExtractedImage],
    cache_get: CacheGet | None = None,
    cache_put: CachePut | None = None,
    classify_fn: ClassifyFn | None = None,
    describe_fn: DescribeFn | None = None,
    confidence_threshold: float = 0.7,
    phash_threshold: int = DEFAULT_PHASH_THRESHOLD,
) -> list[dict[str, Any]]:
    """Turn extracted images into stored image descriptions.

    Args:
        images: Extracted image candidates from :func:`extract_images`.
        cache_get: Optional ``(phash) -> entry dict | None`` lookup.
            Errors are treated as a cache miss so local processing can
            continue even if the cache backend hiccups.
        cache_put: Optional ``(phash, label, confidence, description)``
            writer. Only successful descriptions are cached. Errors are
            logged and ignored.
        classify_fn: Optional classifier override (tests).
        describe_fn: Optional describer override (tests). When omitted,
            the describer is chosen by ``VISION_PROVIDER`` in `.env`
            (``groq`` default, or ``gemini``). Overrides always win.
        confidence_threshold: At/above this CLIP confidence the top
            label is trusted for routing.
        phash_threshold: Max hamming distance for within-submission
            near-duplicate removal.

    Returns:
        A list of description dicts (see migration 0005 for the shape),
        in document order. May be empty.
    """
    classify = classify_fn or classify_image
    describe = describe_fn or _resolve_default_describer()

    descriptions: list[dict[str, Any]] = []
    rate_limited = False

    for hashed in dedupe_images(images, threshold=phash_threshold):
        phash = hashed.phash
        image = hashed.image

        # --- Cache lookup (exact or near-match, handled by the caller's
        #     implementation). A hit skips both CLIP and the vision LLM.
        entry: dict | None = None
        if cache_get is not None:
            try:
                entry = cache_get(phash)
            except Exception:
                logger.warning(
                    "Image cache lookup failed for phash %s; treating as miss",
                    phash,
                    exc_info=True,
                )

        if entry is not None:
            confidence = float(entry.get("confidence") or 0.0)
            description = entry.get("description")
            descriptions.append(
                {
                    "page": image.page_number,
                    "phash": phash,
                    "classification": entry.get("classification", ""),
                    "confidence": confidence,
                    "description": description,
                    "needs_human_review": (
                        confidence < confidence_threshold or not description
                    ),
                }
            )
            continue

        # --- Classify locally with CLIP.
        try:
            label, confidence = classify(image.image_bytes)
        except Exception:
            logger.warning(
                "Image classification failed for phash %s; skipping image",
                phash,
                exc_info=True,
            )
            continue

        # --- Three-tier routing.
        if label in DECORATIVE_LABELS:
            # Decorative-labeled images are never described — confident
            # or not. Template banners/logos would only waste vision
            # quota; genuinely diagram-like images that CLIP misread as
            # decorative were already relabelled upstream by the
            # diagram-floor rescue in classify_image.
            continue

        needs_review = confidence < confidence_threshold

        # --- Describe with the vision model (diagram-like or ambiguous).
        description: str | None = None
        if rate_limited:
            # A persistent rate limit was hit earlier THIS run; don't
            # burn more doomed calls — flag for review instead. Failed
            # entries are not cached, so later submissions retry them.
            logger.warning(
                "Vision API rate-limited earlier this run; storing phash "
                "%s without a description",
                phash,
            )
            needs_review = True
        else:
            try:
                description = describe(image.image_bytes)
            except RateLimitError:
                # Persistent: retries were exhausted inside describe().
                rate_limited = True
                logger.warning(
                    "Vision API rate limit exhausted for phash %s; "
                    "skipping descriptions for remaining images this run",
                    phash,
                )
            except Exception:
                logger.warning(
                    "Image description failed for phash %s", phash, exc_info=True
                )
            if description is None:
                needs_review = True

        descriptions.append(
            {
                "page": image.page_number,
                "phash": phash,
                "classification": label,
                "confidence": confidence,
                "description": description,
                "needs_human_review": needs_review,
            }
        )

        # --- Cache only successful descriptions (failures stay retryable).
        if description is not None and cache_put is not None:
            try:
                cache_put(phash, label, confidence, description)
            except Exception:
                logger.warning(
                    "Image cache write failed for phash %s", phash, exc_info=True
                )

    return descriptions
