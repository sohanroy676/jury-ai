"""Spike: verify Groq vision model availability for v0.3.5.

1. Lists all models visible to the configured GROQ_API_KEY.
2. Sends a tiny generated image to each candidate model and reports
   which ones accept image input end-to-end.

Run: python scripts/check_groq_vision.py
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from groq import Groq

CANDIDATE_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "groq/compound",
    "groq/compound-mini",
    "qwen/qwen3.6-27b",
]


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise SystemExit("GROQ_API_KEY not set in .env")

    client = Groq(api_key=api_key)

    # --- 1. List models -----------------------------------------------------
    print("Models available to this API key:")
    models = client.models.list()
    for m in sorted(models.data, key=lambda x: x.id):
        print(f"  - {m.id}")

    # --- 2. Build a tiny test image (PyMuPDF render -> PNG) -----------------
    import warnings

    warnings.filterwarnings("ignore")
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Architecture: client -> server -> database")
    png_bytes = doc[0].get_pixmap().tobytes("png")
    doc.close()

    b64 = base64.b64encode(png_bytes).decode()

    # --- 3. Vision call against each candidate -------------------------------
    working = []
    for model in CANDIDATE_MODELS:
        print(f"\nTesting vision call with model: {model}")
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this image in one sentence.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=100,
            )
            content = response.choices[0].message.content
            print(f"  SUCCESS: {content}")
            working.append(model)
        except Exception as exc:  # noqa: BLE001 — diagnostic spike must report ANY failure per candidate
            print(f"  FAILED: {type(exc).__name__}: {exc}")

    print("\n=== SUMMARY ===")
    if working:
        print(f"Vision-capable models on this account: {working}")
    else:
        print(
            "No Groq model accepted image input. "
            "Fallback required (e.g. Google AI Studio Gemini free tier)."
        )


if __name__ == "__main__":
    main()
