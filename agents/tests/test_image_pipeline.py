"""Tests for the image-understanding pipeline (v0.3.5).

All external effects (CLIP, vision LLM, cache) are injected as fakes,
so tests exercise the real orchestration/routing logic offline.
"""

import io
from unittest.mock import Mock

from groq import RateLimitError
from PIL import Image, ImageDraw

from agents.parsing.images.dedupe import compute_phash
from agents.parsing.images.extract import ExtractedImage
from agents.parsing.images.pipeline import process_submission_images

# --- Fixture helpers ---------------------------------------------------------


def _png_bytes(color=(150, 150, 150)) -> bytes:
    img = Image.new("RGB", (100, 80), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pattern_png(kind: str) -> bytes:
    """Build a structurally distinct pattern (flat colors alias together
    in pHash space and would be deduped as near-identical)."""
    img = Image.new("RGB", (120, 90), "white")
    draw = ImageDraw.Draw(img)
    if kind == "circle":
        draw.ellipse([30, 22, 90, 68], fill="black")
    elif kind == "diag":
        for y in range(90):
            x_edge = int(120 * y / 90)
            draw.line([(x_edge, y), (119, y)], fill="black")
    else:
        raise ValueError(f"unknown pattern {kind}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _img(page: int = 1, color=(150, 150, 150)) -> ExtractedImage:
    return ExtractedImage(
        page_number=page, image_bytes=_png_bytes(color), source_format="pdf"
    )


class FakeCache:
    """Dict-backed cache_get/cache_put pair with call recording."""

    def __init__(self, entries: dict | None = None):
        self.entries = entries or {}
        self.get_calls: list[str] = []
        self.put_calls: list[tuple] = []

    def get(self, phash: str):
        self.get_calls.append(phash)
        return self.entries.get(phash)

    def put(self, phash: str, label: str, confidence: float, description):
        self.put_calls.append((phash, label, confidence, description))
        self.entries[phash] = {
            "phash": phash,
            "classification": label,
            "confidence": confidence,
            "description": description,
        }


def make_classify(
    results: dict[str, tuple[str, float]] | None = None, error: Exception | None = None
):
    """Build a fake classify fn returning per-call results in order."""
    calls: list[bytes] = []

    def classify(image_bytes: bytes) -> tuple[str, float]:
        calls.append(image_bytes)
        if error is not None:
            raise error
        if results:
            # Pop deterministically; fall back to the last entry.
            key = next(iter(results))
            value = results.pop(key)
            return value
        raise AssertionError("classify called more times than configured")

    classify.calls = calls
    return classify


def make_describe(
    descriptions: list[str] | None = None, error: Exception | None = None
):
    """Build a fake describe fn returning descriptions in order."""
    calls: list[bytes] = []

    def describe(image_bytes: bytes) -> str:
        calls.append(image_bytes)
        if error is not None:
            raise error
        if descriptions:
            return descriptions.pop(0)
        raise AssertionError("describe called more times than configured")

    describe.calls = calls
    return describe


# --- Basic behavior ----------------------------------------------------------


def test_empty_input_returns_empty():
    """No images -> empty result, zero external calls."""
    cache = FakeCache()
    classify = make_classify()
    describe = make_describe()

    result = process_submission_images(
        [],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert result == []
    assert cache.get_calls == [] and cache.put_calls == []
    assert classify.calls == [] and describe.calls == []


def test_diagram_high_confidence_described_and_cached():
    """High-confidence diagram -> vision description + cache write."""
    cache = FakeCache()
    classify = make_classify({"a": ("architecture diagram", 0.92)})
    describe = make_describe(["Three boxes connected left to right."])

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    entry = result[0]
    assert entry["page"] == 1
    assert entry["classification"] == "architecture diagram"
    assert abs(entry["confidence"] - 0.92) < 1e-9
    assert entry["description"] == "Three boxes connected left to right."
    assert entry["needs_human_review"] is False
    assert len(cache.put_calls) == 1


def test_decorative_high_confidence_dropped():
    """High-confidence logo/photo/decorative -> dropped, nothing stored."""
    cache = FakeCache()
    classify = make_classify({"a": ("logo or icon", 0.95)})
    describe = make_describe()

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert result == []
    assert describe.calls == []  # no vision call
    assert cache.put_calls == []  # nothing cached


def test_low_confidence_described_and_flagged():
    """Ambiguous image -> described AND flagged needs_human_review."""
    cache = FakeCache()
    classify = make_classify({"a": ("photo", 0.45)})
    describe = make_describe(["Possibly a whiteboard sketch."])

    result = process_submission_images(
        [_img(2)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    entry = result[0]
    assert entry["needs_human_review"] is True
    assert entry["description"] == "Possibly a whiteboard sketch."
    assert len(cache.put_calls) == 1  # still cached for reuse


def test_threshold_boundary_is_inclusive():
    """Confidence exactly at the threshold counts as high-confidence."""
    cache = FakeCache()
    classify = make_classify({"a": ("logo or icon", 0.70)})
    describe = make_describe()

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
        confidence_threshold=0.70,
    )

    assert result == []  # treated as decorative -> dropped, not reviewed


# --- Caching -----------------------------------------------------------------


def test_cache_hit_skips_classify_and_describe():
    """An exact-phash cache hit reuses the stored entry with zero model calls."""
    # Seed with the image's REAL computed phash — that's what the
    # pipeline looks up.
    phash_key = compute_phash(_png_bytes())
    cache = FakeCache(
        entries={
            phash_key: {
                "phash": phash_key,
                "classification": "flowchart",
                "confidence": 0.88,
                "description": "Decision flow with four nodes.",
            }
        }
    )
    classify = make_classify()
    describe = make_describe()

    result = process_submission_images(
        [_img(3)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    entry = result[0]
    assert entry["classification"] == "flowchart"
    assert entry["description"] == "Decision flow with four nodes."
    assert entry["needs_human_review"] is False
    assert classify.calls == [] and describe.calls == []
    assert cache.put_calls == []


def test_cache_hit_low_confidence_still_flagged():
    """A cached low-confidence entry keeps its needs_human_review flag."""
    phash_key = compute_phash(_png_bytes())
    cache = FakeCache(
        entries={
            phash_key: {
                "phash": phash_key,
                "classification": "photo",
                "confidence": 0.5,
                "description": "Unclear image.",
            }
        }
    )
    classify = make_classify()
    describe = make_describe()

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert result[0]["needs_human_review"] is True


def test_second_submission_same_template_served_from_cache():
    """Cross-submission reuse: the second upload of a shared template
    image hits the cache written by the first (roadmap DoD)."""
    cache = FakeCache()

    first_classify = make_classify({"a": ("architecture diagram", 0.9)})
    first_describe = make_describe(["Shared template diagram."])
    process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=first_classify,
        describe_fn=first_describe,
    )

    # Second submission: same image content -> same pHash -> cache hit.
    second_classify = make_classify()
    second_describe = make_describe()
    result2 = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=second_classify,
        describe_fn=second_describe,
    )

    assert len(result2) == 1
    assert result2[0]["description"] == "Shared template diagram."
    assert second_classify.calls == [] and second_describe.calls == []


def test_cache_lookup_error_treated_as_miss():
    """A failing cache backend degrades to a miss, processing continues."""

    def broken_get(phash):
        raise RuntimeError("supabase down")

    classify = make_classify({"a": ("flowchart", 0.85)})
    describe = make_describe(["Flow description."])

    result = process_submission_images(
        [_img(1)],
        cache_get=broken_get,
        cache_put=None,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    assert result[0]["description"] == "Flow description."


def test_cache_write_error_ignored():
    """A failing cache write doesn't lose the description."""

    def broken_put(*args):
        raise RuntimeError("write failed")

    classify = make_classify({"a": ("chart or graph", 0.8)})
    describe = make_describe(["Bar chart of latency."])

    result = process_submission_images(
        [_img(1)],
        cache_get=None,
        cache_put=broken_put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    assert result[0]["description"] == "Bar chart of latency."


# --- Failure semantics -------------------------------------------------------


def test_classification_failure_skips_image():
    """A CLIP failure skips that image entirely (no entry, no describe)."""
    cache = FakeCache()
    classify = make_classify(error=RuntimeError("model failed"))
    describe = make_describe()

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert result == []
    assert describe.calls == []
    assert cache.put_calls == []


def test_rate_limit_circuit_breaker_skips_subsequent_describes():
    """Once a persistent rate limit is hit, remaining images skip the
    vision call entirely (no doomed retries) and are stored as
    description=None + needs_human_review=True, uncached."""
    cache = FakeCache()
    describe_calls: list[bytes] = []

    def rate_limited_describe(image_bytes: bytes) -> str:
        describe_calls.append(image_bytes)
        raise RateLimitError("rate limited", response=Mock(), body=None)

    result = process_submission_images(
        [
            ExtractedImage(1, _pattern_png("circle"), "pdf"),
            ExtractedImage(2, _pattern_png("diag"), "pdf"),
        ],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=make_classify(
            {
                "b": ("architecture diagram", 0.9),
                "a": ("flowchart", 0.85),
            }
        ),
        describe_fn=rate_limited_describe,
    )

    # Exactly ONE doomed call was made; the second image skipped it.
    assert len(describe_calls) == 1
    assert len(result) == 2
    for entry in result:
        assert entry["description"] is None
        assert entry["needs_human_review"] is True
    assert cache.put_calls == []  # failures stay retryable


def test_description_failure_keeps_entry_flagged_and_uncached():
    """A vision failure stores description=None + review flag, and does
    NOT cache the failure (so later submissions can retry it)."""
    cache = FakeCache()
    classify = make_classify({"a": ("architecture diagram", 0.9)})
    describe = make_describe(error=RuntimeError("vision down"))

    result = process_submission_images(
        [_img(1)],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    entry = result[0]
    assert entry["description"] is None
    assert entry["needs_human_review"] is True
    assert cache.put_calls == []


def test_within_submission_duplicates_processed_once():
    """The same banner on pages 1 and 2 is deduped before any calls."""
    same_bytes = _png_bytes()
    images = [
        ExtractedImage(page_number=1, image_bytes=same_bytes, source_format="pdf"),
        ExtractedImage(page_number=2, image_bytes=same_bytes, source_format="pdf"),
    ]
    cache = FakeCache()
    classify = make_classify({"a": ("decorative graphic", 0.93)})
    describe = make_describe()

    result = process_submission_images(
        images,
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert result == []  # decorative, dropped once
    assert len(classify.calls) == 1  # classified only once


def test_mixed_batch_preserves_document_order():
    """Multiple distinct images produce entries in document order."""
    cache = FakeCache()
    classify = make_classify(
        {
            "c": ("architecture diagram", 0.91),
            "b": ("flowchart", 0.87),
        }
    )
    describe = make_describe(["First diagram.", "Second flow."])

    result = process_submission_images(
        [
            ExtractedImage(1, _pattern_png("circle"), "pdf"),
            ExtractedImage(2, _pattern_png("diag"), "pdf"),
        ],
        cache_get=cache.get,
        cache_put=cache.put,
        classify_fn=classify,
        describe_fn=describe,
    )

    assert [e["page"] for e in result] == [1, 2]
    assert [e["description"] for e in result] == ["First diagram.", "Second flow."]


def test_offline_mode_no_cache_callables():
    """Passing no cache callables runs fully offline without errors."""
    classify = make_classify({"a": ("architecture diagram", 0.9)})
    describe = make_describe(["Offline description."])

    result = process_submission_images(
        [_img(1)],
        classify_fn=classify,
        describe_fn=describe,
    )

    assert len(result) == 1
    assert result[0]["description"] == "Offline description."
