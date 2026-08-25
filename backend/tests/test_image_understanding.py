"""Tests for v0.3.5 image-understanding wiring: upload route integration,
graceful degradation, and merging descriptions into the scoring input."""

import io

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.scoring.scorer import CriterionScore, ScoringResult, build_scoring_text
from backend.main import app
from backend.services import supabase

client = TestClient(app)


# --- Fixture helpers ---------------------------------------------------------


def _png_bytes() -> bytes:
    img = Image.new("RGB", (200, 120), (180, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_with_image_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Proposal with a diagram")
    page.insert_image(pymupdf.Rect(72, 100, 272, 220), stream=_png_bytes())
    data = doc.tobytes()
    doc.close()
    return data


def _text_only_pdf_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Text only proposal")
    data = doc.tobytes()
    doc.close()
    return data


FAKE_DESCRIPTIONS = [
    {
        "page": 1,
        "phash": "abc123",
        "classification": "architecture diagram",
        "confidence": 0.91,
        "description": "Three-tier architecture with a mobile client.",
        "needs_human_review": False,
    }
]


@pytest.fixture(autouse=True)
def _mock_supabase(monkeypatch):
    """Mock the Supabase service layer so tests never hit the network."""

    def fake_upload(file_bytes, file_name, file_type):
        return f"https://example.supabase.co/storage/v1/object/public/submissions/{file_name}"

    def fake_insert(team_name, file_url, file_type, supersedes_team=False):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "team_name": team_name,
            "file_url": file_url,
            "file_type": file_type,
            "status": "submitted",
        }

    captured: dict = {}

    def fake_insert_parsed(
        submission_id,
        raw_text,
        sections,
        source_format,
        image_descriptions=None,
    ):
        captured["image_descriptions"] = image_descriptions
        return {"id": "parsed-1", "submission_id": submission_id}

    monkeypatch.setattr(supabase, "upload_submission_file", fake_upload)
    monkeypatch.setattr(supabase, "insert_submission", fake_insert)
    # v1.1.0: the upload route consults the re-submission gate; nothing is
    # active in these fixtures.
    monkeypatch.setattr(
        supabase,
        "get_active_submission_by_team",
        lambda team_name: None,
    )
    monkeypatch.setattr(supabase, "insert_parsed_submission", fake_insert_parsed)
    return captured


@pytest.fixture
def _captured_insert(_mock_supabase):
    """Expose what the mocked insert_parsed_submission received."""
    return _mock_supabase


# --- Upload route integration ------------------------------------------------


def test_upload_with_images_stores_descriptions(_captured_insert, monkeypatch):
    """A PDF with images stores the pipeline's descriptions."""
    import backend.routes.submissions as routes

    monkeypatch.setattr(
        routes, "extract_images", lambda *a, **k: ["fake-image-candidate"]
    )
    monkeypatch.setattr(
        routes,
        "process_submission_images",
        lambda *a, **k: FAKE_DESCRIPTIONS,
    )

    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Image"},
        files={"file": ("proposal.pdf", _pdf_with_image_bytes(), "application/pdf")},
    )

    assert resp.status_code == 201
    assert _captured_insert["image_descriptions"] == FAKE_DESCRIPTIONS


def test_upload_without_images_stores_empty_descriptions(_captured_insert, monkeypatch):
    """A text-only PDF stores an empty description list (no crash)."""
    import backend.routes.submissions as routes

    monkeypatch.setattr(routes, "extract_images", lambda *a, **k: [])
    monkeypatch.setattr(routes, "process_submission_images", lambda *a, **k: [])

    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Text"},
        files={"file": ("proposal.pdf", _text_only_pdf_bytes(), "application/pdf")},
    )

    assert resp.status_code == 201
    assert _captured_insert["image_descriptions"] == []


def test_upload_survives_image_pipeline_failure(_captured_insert, monkeypatch):
    """If the whole image pipeline blows up, the upload still succeeds."""

    def broken_pipeline(*args, **kwargs):
        raise RuntimeError("CLIP exploded")

    import backend.routes.submissions as routes

    monkeypatch.setattr(
        routes, "extract_images", lambda *a, **k: ["fake-image-candidate"]
    )
    monkeypatch.setattr(routes, "process_submission_images", broken_pipeline)

    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Resilient"},
        files={"file": ("proposal.pdf", _pdf_with_image_bytes(), "application/pdf")},
    )

    assert resp.status_code == 201
    assert _captured_insert["image_descriptions"] == []


# --- Scoring input merge -----------------------------------------------------


def test_build_scoring_text_without_descriptions_returns_raw():
    """No descriptions -> raw text returned unchanged."""
    raw = "Plain submission text."
    assert build_scoring_text(raw, None) == raw
    assert build_scoring_text(raw, []) == raw


def test_build_scoring_text_appends_description_section():
    """Descriptions are appended as a delimited, page-tagged section."""
    result = build_scoring_text("Body text.", FAKE_DESCRIPTIONS)

    assert result.startswith("Body text.")
    assert "---IMAGE DESCRIPTIONS---" in result
    assert "[Page/slide 1] (architecture diagram):" in result
    assert "Three-tier architecture with a mobile client." in result


def test_build_scoring_text_handles_undescribed_entries():
    """Entries with description=None get an explicit pending-review note."""
    entries = [
        {
            "page": 2,
            "phash": "xyz",
            "classification": "flowchart",
            "confidence": 0.6,
            "description": None,
            "needs_human_review": True,
        }
    ]
    result = build_scoring_text("Body.", entries)

    assert "[Page/slide 2] (flowchart):" in result
    assert "pending human review" in result


def test_score_endpoint_merges_descriptions_into_agent_input(monkeypatch):
    """The scoring agent receives raw text + image descriptions merged."""
    captured_text: dict = {}

    def fake_get_parsed(submission_id):
        return {
            "id": "parsed-1",
            "submission_id": submission_id,
            "raw_text": "Submission body about a smart city app.",
            "sections": [],
            "source_format": "pdf",
            "image_descriptions": FAKE_DESCRIPTIONS,
        }

    async def fake_score(submission_id, parsed_text, groq_api_key=None):
        captured_text["value"] = parsed_text
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(criterion="problem_fit", score=8, justification="ok"),
                CriterionScore(
                    criterion="technical_depth", score=7, justification="ok"
                ),
                CriterionScore(criterion="feasibility", score=6, justification="ok"),
                CriterionScore(criterion="innovation", score=9, justification="ok"),
            ],
        )

    monkeypatch.setattr(supabase, "get_parsed_submission", fake_get_parsed)
    monkeypatch.setattr(supabase, "insert_scores", lambda *a, **k: [])
    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)

    resp = client.post("/api/submissions/test-id/score")

    assert resp.status_code == 200
    merged = captured_text["value"]
    assert merged.startswith("Submission body about a smart city app.")
    assert "---IMAGE DESCRIPTIONS---" in merged
    assert "Three-tier architecture with a mobile client." in merged


def test_score_endpoint_without_descriptions_sends_raw_text(monkeypatch):
    """Old rows without the image_descriptions column value still work."""
    captured_text: dict = {}

    def fake_get_parsed(submission_id):
        # Simulates pre-v0.3.5 rows: no image_descriptions key at all.
        return {
            "id": "parsed-1",
            "submission_id": submission_id,
            "raw_text": "Legacy parsed text.",
            "sections": [],
            "source_format": "pdf",
        }

    async def fake_score(submission_id, parsed_text, groq_api_key=None):
        captured_text["value"] = parsed_text
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(criterion=c, score=5, justification="ok")
                for c in (
                    "problem_fit",
                    "technical_depth",
                    "feasibility",
                    "innovation",
                )
            ],
        )

    monkeypatch.setattr(supabase, "get_parsed_submission", fake_get_parsed)
    monkeypatch.setattr(supabase, "insert_scores", lambda *a, **k: [])
    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)

    resp = client.post("/api/submissions/legacy-id/score")

    assert resp.status_code == 200
    assert captured_text["value"] == "Legacy parsed text."
