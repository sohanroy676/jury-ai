"""One-off diagnostic: call the vision describer directly on the PDF's
page 5-7 images to capture the REAL exception behind the failures."""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from PIL import Image

from agents.parsing.images.describe import describe_image
from agents.parsing.images.extract import extract_images

PATH = sys.argv[1] if len(sys.argv) > 1 else "D:/Documents/Hackathons/scango.pdf"

with open(PATH, "rb") as f:
    images = extract_images(f.read(), "pdf")

targets = [i for i in images if i.page_number in (5, 6, 7)]
print(f"{len(targets)} candidate images on pages 5-7")

for img in targets:
    with Image.open(io.BytesIO(img.image_bytes)) as pil:
        dims = pil.size
    kb = len(img.image_bytes) / 1024
    b64_kb = len(img.image_bytes) * 4 / 3 / 1024
    print(
        f"\npage {img.page_number}: pixels={dims}, "
        f"raw={kb:.0f}KB, base64~{b64_kb:.0f}KB"
    )
    try:
        desc = describe_image(img.image_bytes)
        print(f"  OK: {desc[:100]}")
    except Exception as exc:  # noqa: BLE001 - diagnostic must report ANY failure per image
        print(f"  FAILED: {type(exc).__module__}.{type(exc).__name__}: {exc}")
