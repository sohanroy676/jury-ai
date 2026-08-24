"""Tests for the submission read endpoints (list + detail)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import supabase

client = TestClient(app)

SUBMISSION_ID = "00000000-0000-0000-0000-000000000001"
SUBMISSION_ROW = {
    "id": SUBMISSION_ID,
    "team_name": "Test Team",
    "file_url": "https://example.supabase.co/storage/v1/object/public/submissions/f.pdf",
    "file_type": "pdf",
    "status": "submitted",
}
PARSED_ROW = {
    "id": "parsed-1",
    "submission_id": SUBMISSION_ID,
    "raw_text": "QuantumQuokka proposal text",
    "sections": [],
    "source_format": "pdf",
    "image_descriptions": [],
}
SCORE_ROWS = [
    {
        "submission_id": SUBMISSION_ID,
        "criterion": "problem_fit",
        "score": 8,
        "justification": "Clear problem.",
        "agent_version": "vTEST",
    }
]


@pytest.fixture(autouse=True)
def _mock_supabase(monkeypatch):
    """Mock the Supabase read layer so tests never hit the network."""
    monkeypatch.setattr(
        supabase, "list_submissions", lambda limit=100: [dict(SUBMISSION_ROW)]
    )
    monkeypatch.setattr(supabase, "get_submission", lambda sid: dict(SUBMISSION_ROW))
    monkeypatch.setattr(supabase, "get_parsed_submission", lambda sid: dict(PARSED_ROW))
    monkeypatch.setattr(
        supabase, "get_scores", lambda sid: [dict(row) for row in SCORE_ROWS]
    )


def test_list_submissions_returns_rows():
    resp = client.get("/api/submissions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == SUBMISSION_ID


def test_list_submissions_empty(monkeypatch):
    monkeypatch.setattr(supabase, "list_submissions", lambda limit=100: [])
    resp = client.get("/api/submissions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_detail_returns_submission_parsed_and_scores():
    resp = client.get(f"/api/submissions/{SUBMISSION_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["submission"]["id"] == SUBMISSION_ID
    assert body["parsed"]["raw_text"] == PARSED_ROW["raw_text"]
    assert len(body["scores"]) == 1
    assert body["scores"][0]["criterion"] == "problem_fit"


def test_detail_is_orphan_tolerant_when_parse_missing(monkeypatch):
    monkeypatch.setattr(supabase, "get_parsed_submission", lambda sid: None)
    resp = client.get(f"/api/submissions/{SUBMISSION_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"] is None
    assert body["scores"]  # scores may exist independently of parsed text


def test_detail_404_when_submission_missing(monkeypatch):
    monkeypatch.setattr(supabase, "get_submission", lambda sid: None)
    monkeypatch.setattr(supabase, "get_parsed_submission", lambda sid: None)
    monkeypatch.setattr(supabase, "get_scores", lambda sid: [])
    resp = client.get(f"/api/submissions/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_detail_404_on_malformed_uuid_without_db_call(monkeypatch):
    called = []

    def _fail(sid):
        called.append(sid)
        return {}

    monkeypatch.setattr(supabase, "get_submission", _fail)
    resp = client.get("/api/submissions/not-a-uuid")
    assert resp.status_code == 404
    assert called == []  # rejected before any Postgres round-trip
