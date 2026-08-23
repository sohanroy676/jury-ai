"""Tests for pHash near-duplicate removal (v0.3.5).

Pattern choices are empirically verified (scripts/check_phash_distances.py):
pHash keeps only coarse low-frequency structure, so simple/flat images
alias together. The fixtures below use shapes whose pairwise hamming
distances are large (28-34) while JPEG recompression moves each hash
by only ~2-10 bits.
"""

import io
import random

from PIL import Image, ImageDraw

from agents.parsing.images.dedupe import compute_phash, dedupe_images
from agents.parsing.images.extract import ExtractedImage

# --- Fixture helpers ---------------------------------------------------------


def _pattern_png(kind: str, size: tuple[int, int] = (240, 160)) -> bytes:
    """Build a PNG with one of three structurally distinct patterns."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    w, h = size
    if kind == "diag":
        # Black above the main diagonal, white below.
        for y in range(h):
            x_edge = int(w * y / h)
            draw.line([(x_edge, y), (w - 1, y)], fill="black")
    elif kind == "circle":
        draw.ellipse([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill="black")
    elif kind == "noise":
        rng = random.Random(42)  # deterministic
        px = img.load()
        for y in range(h):
            for x in range(w):
                v = rng.randint(0, 255)
                px[x, y] = (v, v, v)
    else:
        raise ValueError(f"unknown pattern {kind}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _recompress(image_bytes: bytes, quality: int = 30, scale: float = 0.9) -> bytes:
    """Re-encode an image as lower-quality JPEG at a slightly smaller size.

    Simulates the same banner image re-saved by a different tool.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        resized = img.convert("RGB").resize(
            (int(img.width * scale), int(img.height * scale))
        )
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()


def _img(image_bytes: bytes, page: int = 1) -> ExtractedImage:
    return ExtractedImage(
        page_number=page, image_bytes=image_bytes, source_format="pdf"
    )


# --- compute_phash -----------------------------------------------------------


def test_phash_deterministic():
    """The same bytes always produce the same hash."""
    data = _pattern_png("circle")
    assert compute_phash(data) == compute_phash(data)


def test_phash_returns_none_for_garbage():
    """Undecodable bytes return None instead of raising."""
    assert compute_phash(b"this is not an image at all") is None
    assert compute_phash(b"") is None


def test_different_patterns_hash_far_apart():
    """Genuinely different images have a large hamming distance (>> 8)."""
    import imagehash

    a = imagehash.hex_to_hash(compute_phash(_pattern_png("diag")))
    b = imagehash.hex_to_hash(compute_phash(_pattern_png("circle")))
    assert a - b > 8


# --- dedupe_images -----------------------------------------------------------


def test_identical_images_deduped():
    """The exact same image appearing twice is kept once."""
    data = _pattern_png("circle")
    kept = dedupe_images([_img(data, 1), _img(data, 2)])
    assert len(kept) == 1
    assert kept[0].image.page_number == 1  # first occurrence wins


def test_recompressed_variant_deduped():
    """A recompressed/resized copy of the same banner is caught by pHash.

    Verified empirically: recompressing the circle pattern moves its
    hash by only ~4 bits (< threshold 8).
    """
    original = _pattern_png("circle")
    variant = _recompress(original)

    # Sanity: the variant really is a near-match, not identical bytes.
    assert variant != original

    kept = dedupe_images([_img(original, 1), _img(variant, 2)])
    assert len(kept) == 1
    assert kept[0].image.page_number == 1


def test_different_images_both_kept():
    """Genuinely different images are all kept (pairwise distances 28+)."""
    kept = dedupe_images(
        [
            _img(_pattern_png("diag"), 1),
            _img(_pattern_png("circle"), 2),
            _img(_pattern_png("noise"), 3),
        ]
    )
    assert len(kept) == 3


def test_unhashable_images_dropped():
    """Images that cannot be decoded are dropped entirely."""
    kept = dedupe_images(
        [
            _img(_pattern_png("circle"), 1),
            _img(b"garbage-not-an-image", 2),
        ]
    )
    assert len(kept) == 1
    assert kept[0].image.page_number == 1


def test_empty_input_returns_empty():
    """No images in, no images out."""
    assert dedupe_images([]) == []


def test_threshold_parameter_respected():
    """A threshold of 0 only dedupes identical hashes.

    The recompressed circle variant sits ~4 bits away from the original,
    so under a strict threshold both are kept.
    """
    original = _pattern_png("circle")
    variant = _recompress(original)

    strict = dedupe_images([_img(original, 1), _img(variant, 2)], threshold=0)
    assert len(strict) == 2  # near-match but not identical -> both kept
