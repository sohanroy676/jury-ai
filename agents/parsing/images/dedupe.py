"""Perceptual-hash deduplication for extracted images (v0.3.5).

Computes a pHash for each image and removes near-duplicates within a
single submission — the same logo/banner repeated across pages or
slides, even if slightly recompressed or resized between pages. The
first occurrence wins; later near-matches are dropped.

Images that cannot be decoded/hashed are dropped entirely: they can't
be classified, described, or cached reliably.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import imagehash
from PIL import Image

from agents.parsing.images.extract import ExtractedImage

# Hamming distance at or below which two 64-bit pHashes are considered
# the same image. 8 tolerates recompression and modest resizing while
# still separating genuinely different images.
DEFAULT_PHASH_THRESHOLD = 8


@dataclass
class HashedImage:
    """An extracted image paired with its perceptual hash."""

    image: ExtractedImage
    phash: str


def compute_phash(image_bytes: bytes) -> str | None:
    """Return the hex pHash of an image, or ``None`` if undecodable."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return str(imagehash.phash(img.convert("RGB")))
    except (OSError, ValueError, Image.DecompressionBombError):
        # OSError covers PIL's UnidentifiedImageError and truncated data;
        # ValueError covers malformed headers; DecompressionBombError
        # covers oversized images.
        return None


def dedupe_images(
    images: list[ExtractedImage],
    threshold: int = DEFAULT_PHASH_THRESHOLD,
) -> list[HashedImage]:
    """Remove near-duplicate images, keeping the first occurrence.

    Args:
        images: Extracted image candidates, in document order.
        threshold: Max hamming distance between pHashes to consider two
            images the same.

    Returns:
        Unique images as :class:`HashedImage` pairs. Unhashable images
        are dropped.
    """
    kept: list[HashedImage] = []
    kept_hashes: list[imagehash.ImageHash] = []

    for image in images:
        phash = compute_phash(image.image_bytes)
        if phash is None:
            continue

        candidate = imagehash.hex_to_hash(phash)
        if any(candidate - existing <= threshold for existing in kept_hashes):
            continue

        kept_hashes.append(candidate)
        kept.append(HashedImage(image=image, phash=phash))

    return kept
