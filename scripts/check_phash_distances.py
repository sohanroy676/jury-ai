"""Empirical check: pairwise pHash hamming distances for candidate
test-fixture patterns (originals + JPEG recompressions).

Run: python scripts/check_phash_distances.py
"""

import io

import imagehash
from PIL import Image, ImageDraw


def pattern(kind: str, size=(240, 160)) -> Image.Image:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    w, h = size
    if kind == "left-half":
        d.rectangle([0, 0, w // 2 - 1, h - 1], fill="black")
    elif kind == "top-half":
        d.rectangle([0, 0, w - 1, h // 2 - 1], fill="black")
    elif kind == "diag":
        for y in range(h):
            x = int(w * y / h)
            d.line([(x, y), (w - 1, y)], fill="black")
    elif kind == "circle":
        d.ellipse([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill="black")
    elif kind == "frame":
        d.rectangle([10, 10, w - 11, h - 11], outline="black", width=12)
    elif kind == "noise":
        import random

        rng = random.Random(42)
        px = img.load()
        for yy in range(h):
            for xx in range(w):
                v = rng.randint(0, 255)
                px[xx, yy] = (v, v, v)
    else:
        raise ValueError(kind)
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def recompress(image_bytes: bytes, quality=30, scale=0.9) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    resized = img.convert("RGB").resize(
        (int(img.width * scale), int(img.height * scale))
    )
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def main() -> None:
    kinds = ["left-half", "top-half", "diag", "circle", "frame", "noise"]
    hashes = {}
    for k in kinds:
        b = png_bytes(pattern(k))
        hashes[k] = imagehash.phash(Image.open(io.BytesIO(b)).convert("RGB"))
        rb = recompress(b)
        rh = imagehash.phash(Image.open(io.BytesIO(rb)).convert("RGB"))
        print(f"{k:10s} orig={hashes[k]}  recompressed_dist={hashes[k] - rh}")

    print("\nPairwise distances (originals):")
    for i, a in enumerate(kinds):
        for bkind in kinds[i + 1 :]:
            dist = hashes[a] - hashes[bkind]
            flag = "  <-- TOO CLOSE" if dist <= 8 else ""
            print(f"{a:10s} vs {bkind:10s}: {dist}{flag}")


if __name__ == "__main__":
    main()
