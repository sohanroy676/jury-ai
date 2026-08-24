"""Core-loop integration test: upload -> parse -> score -> read back.

The v0.4.0 checkpoint contract. Real PDF/PPTX parsing runs (fitz); every
external boundary (Supabase, Groq) is mocked with an in-memory store so
the test proves the stages are correctly WIRED, not that the network
works — live verification covers that separately.
"""

import uuid

import fitz
import pytest
from fastapi.testclient import TestClient

from agents.scoring.scorer import AGENT_VERSION, CriterionScore, ScoringResult
from backend.main import app
from backend.services import supabase

client = TestClient(app)

MARKER = "QuantumQuokka core-loop checkpoint proposal"
CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), MARKER)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def store(monkeypatch):
    """In-memory Supabase stand-in wired into the service layer."""
    state = {"submissions": {}, "parsed": {}, "scores": {}}

    def fake_upload(file_bytes, file_name, file_type):
        return f"https://example.supabase.co/storage/v1/object/public/submissions/{file_name}"

    def fake_insert_submission(team_name, file_url, file_type):
        row = {
            "id": str(uuid.uuid4()),
            "team_name": team_name,
            "file_url": file_url,
            "file_type": file_type,
            "status": "submitted",
        }
        state["submissions"][row["id"]] = row
        return dict(row)

    def fake_insert_parsed(
        submission_id, raw_text, sections, source_format, image_descriptions=None
    ):
        row = {
            "submission_id": submission_id,
            "raw_text": raw_text,
            "sections": sections,
            "source_format": source_format,
            "image_descriptions": image_descriptions or [],
        }
        state["parsed"][submission_id] = row
        return dict(row)

    def fake_get_parsed(submission_id):
        row = state["parsed"].get(submission_id)
        return dict(row) if row else None

    def fake_insert_scores(submission_id, scores, agent_version):
        state["scores"][submission_id] = [
            {
                "submission_id": submission_id,
                "criterion": s.criterion,
                "score": s.score,
                "justification": s.justification,
                "agent_version": agent_version,
            }
            for s in scores
        ]
        return [dict(r) for r in state["scores"][submission_id]]

    def fake_get_scores(submission_id):
        return [dict(r) for r in state["scores"].get(submission_id, [])]

    monkeypatch.setattr(supabase, "upload_submission_file", fake_upload)
    monkeypatch.setattr(supabase, "insert_submission", fake_insert_submission)

    def fake_get_submission(submission_id):
        row = state["submissions"].get(submission_id)
        return dict(row) if row else None

    monkeypatch.setattr(supabase, "get_submission", fake_get_submission)
    monkeypatch.setattr(supabase, "insert_parsed_submission", fake_insert_parsed)
    monkeypatch.setattr(supabase, "get_parsed_submission", fake_get_parsed)
    monkeypatch.setattr(supabase, "insert_scores", fake_insert_scores)
    monkeypatch.setattr(supabase, "get_scores", fake_get_scores)
    monkeypatch.setattr(
        supabase,
        "list_submissions",
        lambda limit=100: [
            dict(r) for r in reversed(list(state["submissions"].values()))
        ],
    )
    return state


@pytest.fixture
def _mock_scoring(monkeypatch):
    """Fixed scoring result — keeps Groq out of the loop test."""

    async def fake_score(submission_id, parsed_text, groq_api_key=None):
        assert MARKER in parsed_text, "parsed text must reach the agent"
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(criterion=c, score=7, justification=f"{c} ok")
                for c in CRITERIA
            ],
        )

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)


def test_core_loop_upload_parse_score_readback(store, _mock_scoring):
    # --- Stage 1: upload + parse-on-upload.
    resp = client.post(
        "/api/submissions",
        data={"team_name": "QuantumQuokka"},
        files={"file": ("proposal.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    submission_id = resp.json()["id"]
    assert MARKER in store["parsed"][submission_id]["raw_text"]

    # --- Readable immediately after upload (pre-score).
    detail = client.get(f"/api/submissions/{submission_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["submission"]["team_name"] == "QuantumQuokka"
    assert MARKER in body["parsed"]["raw_text"]
    assert body["scores"] == []

    listed = client.get("/api/submissions")
    assert listed.status_code == 200
    assert any(row["id"] == submission_id for row in listed.json())

    # --- Stage 2: score.
    scored = client.post(f"/api/submissions/{submission_id}/score")
    assert scored.status_code == 200, scored.text
    assert scored.json()["agent_version"] == AGENT_VERSION

    # --- Stage 3: read back the full record.
    final = client.get(f"/api/submissions/{submission_id}").json()
    assert len(final["scores"]) == 4
    assert {row["criterion"] for row in final["scores"]} == set(CRITERIA)
    for row in final["scores"]:
        assert row["justification"]
        assert row["agent_version"] == AGENT_VERSION
