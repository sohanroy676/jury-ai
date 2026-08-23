"""Tests for CLIP zero-shot classification routing logic (v0.3.5).

The real CLIP model is never loaded: ``_load_model`` is monkeypatched
to return fakes built on small torch tensors, so tests run offline and
instantly while still exercising the real inference math path.
"""

import io

import pytest
import torch
from PIL import Image

from agents.parsing.images import classify as classify_module
from agents.parsing.images.classify import (
    CLASSIFICATION_LABELS,
    classify_image,
)

# --- Fixture helpers ---------------------------------------------------------


def _png_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), (120, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_model_bundle(top_probs: list[float]):
    """Build a (model, preprocess, tokenizer) triple that yields EXACTLY
    ``top_probs`` through classify_image's real inference math.

    Construction: image features point along e1; text feature row i has
    e1-component d_i = log(p_i)/100 + 0.05 (plus an orthogonal unit
    component so rows are unit length). After L2 normalization both sides,
    the cosine similarities are exactly d_i, and
    softmax(100 * d_i) = softmax(log(p_i) + 5) = p_i (shift invariance).
    """
    import math

    def _row(di: float) -> list[float]:
        return [di, math.sqrt(max(0.0, 1.0 - di * di)), 0.0, 0.0, 0.0, 0.0]

    class FakeModel:
        def eval(self):
            return self

        def encode_image(self, tensor):
            return torch.tensor([[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]])

        def encode_text(self, tensor):
            return torch.tensor([_row(math.log(p) / 100.0 + 0.05) for p in top_probs])

    def preprocess(img):
        return torch.zeros(3, 8, 8)

    def tokenizer(labels):
        return torch.zeros(len(labels), 1)

    return FakeModel(), preprocess, tokenizer


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test starts with no cached model."""
    classify_module._model = None
    classify_module._preprocess = None
    classify_module._tokenizer = None
    yield
    classify_module._model = None
    classify_module._preprocess = None
    classify_module._tokenizer = None


def _patch_model(monkeypatch, top_probs):
    bundle = _fake_model_bundle(top_probs)
    monkeypatch.setattr(classify_module, "_load_model", lambda *a, **k: bundle)


# --- Happy path --------------------------------------------------------------


def test_classify_returns_top_label_and_confidence(monkeypatch):
    """The argmax label and its probability are returned."""
    probs = [0.05, 0.05, 0.80, 0.04, 0.03, 0.03]  # chart or graph wins
    _patch_model(monkeypatch, probs)

    label, confidence = classify_image(_png_bytes())

    assert label == "chart or graph"
    assert 0.79 <= confidence <= 0.81


def test_classify_confidence_in_unit_range(monkeypatch):
    probs = [0.2, 0.2, 0.15, 0.15, 0.15, 0.15]
    _patch_model(monkeypatch, probs)

    _, confidence = classify_image(_png_bytes())
    assert 0.0 <= confidence <= 1.0


def test_labels_match_roadmap_specification():
    """The candidate labels are exactly the roadmap's six."""
    assert CLASSIFICATION_LABELS == [
        "architecture diagram",
        "flowchart",
        "chart or graph",
        "photo",
        "logo or icon",
        "decorative graphic",
    ]


def test_label_sets_partition_candidates():
    """Every label is either diagram-like or decorative — never both."""
    from agents.parsing.images.classify import DECORATIVE_LABELS, DIAGRAM_LABELS

    all_labels = set(CLASSIFICATION_LABELS)
    assert DIAGRAM_LABELS | DECORATIVE_LABELS == all_labels
    assert not (DIAGRAM_LABELS & DECORATIVE_LABELS)


def test_model_loaded_once_and_cached(monkeypatch):
    """The lazy singleton loads the model only once across calls.

    Patches the heavy open_clip entry points (NOT ``_load_model``) so
    the real singleton-caching logic is what's exercised.
    """
    import open_clip

    bundle = _fake_model_bundle([0.9, 0.02, 0.02, 0.02, 0.02, 0.02])
    calls = []

    def counting_create(*args, **kwargs):
        calls.append(1)
        return bundle[0], None, bundle[1]

    monkeypatch.setattr(open_clip, "create_model_and_transforms", counting_create)
    monkeypatch.setattr(open_clip, "get_tokenizer", lambda *a, **k: bundle[2])

    classify_image(_png_bytes())
    classify_image(_png_bytes())

    assert len(calls) == 1


def test_garbage_image_bytes_raise(monkeypatch):
    """Undecodable image bytes propagate an error (pipeline handles it).

    PIL raises UnidentifiedImageError (an OSError subclass) for bytes it
    cannot identify.
    """
    _patch_model(monkeypatch, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    with pytest.raises(OSError):
        classify_image(b"not-an-image")
