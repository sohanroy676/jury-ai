"""Local CLIP zero-shot classification of extracted images (v0.3.5).

Uses open_clip (ViT-B-32 by default) running entirely on CPU — no API,
no cost. The model is lazy-loaded as a thread-safe module singleton so
importing this module (and running the test suite) never downloads
weights; the first real classification triggers a one-time ~350 MB
download that is cached locally by the Hugging Face/torch hub cache.
"""

from __future__ import annotations

import io
import threading

from PIL import Image

# Roadmap-specified candidate labels.
CLASSIFICATION_LABELS = [
    "architecture diagram",
    "flowchart",
    "chart or graph",
    "photo",
    "logo or icon",
    "decorative graphic",
]

# Labels whose high-confidence match means the image carries content
# worth describing with a vision model.
DIAGRAM_LABELS = {"architecture diagram", "flowchart", "chart or graph"}

# Labels whose high-confidence match means template decoration — drop.
DECORATIVE_LABELS = {"photo", "logo or icon", "decorative graphic"}

DEFAULT_CLIP_MODEL = "ViT-B-32"
DEFAULT_CLIP_PRETRAINED = "openai"

_model = None
_preprocess = None
_tokenizer = None
_lock = threading.Lock()


def _load_model(model_name: str, pretrained: str):
    """Load and cache the CLIP model, preprocess fn, and tokenizer.

    Separated into its own function so tests can monkeypatch it and
    never download weights.
    """
    global _model, _preprocess, _tokenizer
    with _lock:
        if _model is None:
            import open_clip

            model, _, preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained=pretrained
            )
            model.eval()
            tokenizer = open_clip.get_tokenizer(model_name)
            _model, _preprocess, _tokenizer = model, preprocess, tokenizer
    return _model, _preprocess, _tokenizer


def classify_image(
    image_bytes: bytes,
    model_name: str = DEFAULT_CLIP_MODEL,
    pretrained: str = DEFAULT_CLIP_PRETRAINED,
) -> tuple[str, float]:
    """Classify an image against the candidate labels.

    Args:
        image_bytes: Raw image bytes (any Pillow-decodable format).
        model_name: open_clip architecture name.
        pretrained: Which pretrained weights to use.

    Returns:
        ``(top_label, confidence)`` where confidence is in [0.0, 1.0].

    Raises:
        Exception: Propagates model-loading or inference failures; the
            pipeline treats these as per-image failures.
    """
    import torch

    model, preprocess, tokenizer = _load_model(model_name, pretrained)

    with Image.open(io.BytesIO(image_bytes)) as img:
        pil_image = img.convert("RGB")
    image_tensor = preprocess(pil_image).unsqueeze(0)
    text_tensor = tokenizer(CLASSIFICATION_LABELS)

    with torch.no_grad():
        image_features = model.encode_image(image_tensor)
        text_features = model.encode_text(text_tensor)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        logit_scale = getattr(model, "logit_scale", None)
        if logit_scale is not None:
            logits = logit_scale.exp() * image_features @ text_features.T
        else:
            logits = 100.0 * image_features @ text_features.T
        probs = logits.softmax(dim=-1)[0]

    best_index = int(probs.argmax())
    return CLASSIFICATION_LABELS[best_index], float(probs[best_index])
