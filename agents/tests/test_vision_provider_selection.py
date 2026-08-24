"""Tests for VISION_PROVIDER-based describer selection (v0.3.6).

Verifies that the pipeline picks the Groq describer by default and the
Gemini describer when ``VISION_PROVIDER=gemini``, and that an explicit
``describe_fn`` override always wins.

Images are real patterned PNGs (like test_image_pipeline.py) because
unhashable bytes get dropped by dedupe before any describer runs.
"""

import io

import pytest
from PIL import Image, ImageDraw

from agents.parsing.images import pipeline as pipeline_module
from agents.parsing.images.describe import describe_image as groq_describe
from agents.parsing.images.describe_gemini import (
    describe_image_gemini,
)
from agents.parsing.images.extract import ExtractedImage
from agents.parsing.images.pipeline import process_submission_images


def _pattern_png(kind: str) -> bytes:
    """Build a structurally distinct PNG so dedupe keeps each image."""
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


def _image(tag: str) -> ExtractedImage:
    return ExtractedImage(
        page_number=1, image_bytes=_pattern_png(tag), source_format="pdf"
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("VISION_PROVIDER", raising=False)


@pytest.fixture()
def _diagram_routing(monkeypatch):
    """Force CLIP routing into the describe branch for every image."""
    monkeypatch.setattr(
        pipeline_module, "classify_image", lambda b: ("flowchart", 0.95)
    )


def _spy_describer(monkeypatch, target: str):
    calls: list[bytes] = []

    def spy(image_bytes: bytes) -> str:
        calls.append(image_bytes)
        return "spied description"

    monkeypatch.setattr(pipeline_module, target, spy)
    return calls


def test_default_provider_uses_groq_describer(monkeypatch, _diagram_routing):
    """With no VISION_PROVIDER set, images go through the Groq path."""
    groq_calls = _spy_describer(monkeypatch, "describe_image")
    gemini_calls = _spy_describer(monkeypatch, "describe_image_gemini")

    result = process_submission_images(
        [_image("circle")],
        classify_fn=pipeline_module.classify_image,
    )

    assert len(result) == 1
    assert result[0]["description"] == "spied description"
    assert len(groq_calls) == 1
    assert gemini_calls == []


def test_gemini_provider_selects_gemini_describer(monkeypatch, _diagram_routing):
    """VISION_PROVIDER=gemini routes descriptions through Gemini."""
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    groq_calls = _spy_describer(monkeypatch, "describe_image")
    gemini_calls = _spy_describer(monkeypatch, "describe_image_gemini")

    result = process_submission_images(
        [_image("diag")],
        classify_fn=pipeline_module.classify_image,
    )

    assert result[0]["description"] == "spied description"
    assert len(gemini_calls) == 1
    assert groq_calls == []


def test_explicit_describe_fn_wins_over_env(monkeypatch, _diagram_routing):
    """An injected describe_fn overrides the env-selected default."""
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    injected_calls: list[bytes] = []

    def injected(image_bytes: bytes) -> str:
        injected_calls.append(image_bytes)
        return "injected"

    result = process_submission_images(
        [_image("circle")],
        describe_fn=injected,
        classify_fn=pipeline_module.classify_image,
    )

    assert result[0]["description"] == "injected"
    assert len(injected_calls) == 1


def test_case_and_whitespace_tolerant(monkeypatch, _diagram_routing):
    """VISION_PROVIDER is matched case-insensitively, trimmed."""
    monkeypatch.setenv("VISION_PROVIDER", "  Gemini ")
    gemini_calls = _spy_describer(monkeypatch, "describe_image_gemini")

    result = process_submission_images(
        [_image("diag")],
        classify_fn=pipeline_module.classify_image,
    )

    assert result[0]["description"] == "spied description"
    assert len(gemini_calls) == 1


def test_unknown_provider_fails_fast(monkeypatch):
    """An unsupported VISION_PROVIDER raises immediately with options."""
    monkeypatch.setenv("VISION_PROVIDER", "openai")

    with pytest.raises(ValueError, match="VISION_PROVIDER"):
        process_submission_images([_image("circle")])


# --- Resolver unit checks ----------------------------------------------------


def test_resolver_returns_expected_functions(monkeypatch):
    """The resolver returns the exact describer callables."""
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
    assert pipeline_module._resolve_default_describer() is groq_describe

    monkeypatch.setenv("VISION_PROVIDER", "groq")
    assert pipeline_module._resolve_default_describer() is groq_describe

    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    assert pipeline_module._resolve_default_describer() is describe_image_gemini
