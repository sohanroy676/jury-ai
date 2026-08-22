"""Tests for the scoring API endpoint."""

import pytest
from fastapi.testclient import TestClient
from groq import GroqError

from agents.scoring.scorer import CriterionScore, ScoringResult
from backend.main import app
from backend.services import supabase

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_supabase(monkeypatch):
    """Mock the Supabase service layer so tests never hit the network."""

    def fake_get_parsed(submission_id):
        return {
            "id": "parsed-id-1",
            "submission_id": submission_id,
            "raw_text": "This is a test submission about a smart city app.",
            "sections": [],
            "source_format": "pdf",
            "parsed_at": "2026-08-22T10:00:00Z",
        }

    def fake_insert_scores(submission_id, scores, agent_version):
        return [
            {
                "id": f"score-{i}",
                "submission_id": submission_id,
                "criterion": s.criterion,
                "score": s.score,
                "justification": s.justification,
                "agent_version": agent_version,
            }
            for i, s in enumerate(scores)
        ]

    monkeypatch.setattr(supabase, "get_parsed_submission", fake_get_parsed)
    monkeypatch.setattr(supabase, "insert_scores", fake_insert_scores)


@pytest.fixture
def _mock_scoring(monkeypatch):
    """Mock the scoring agent to return a fixed result."""

    def fake_score(submission_id, parsed_text, groq_api_key=None):
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(
                    criterion="problem_fit",
                    score=8,
                    justification="Clear problem statement.",
                ),
                CriterionScore(
                    criterion="technical_depth",
                    score=7,
                    justification="Good tech stack.",
                ),
                CriterionScore(
                    criterion="feasibility",
                    score=6,
                    justification="Realistic for a hackathon.",
                ),
                CriterionScore(
                    criterion="innovation",
                    score=9,
                    justification="Novel approach.",
                ),
            ],
        )

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)


def test_score_endpoint_success(_mock_scoring):
    """A valid submission ID returns 200 with 4 scores."""
    resp = client.post("/api/submissions/test-submission-id/score")
    assert resp.status_code == 200
    body = resp.json()
    assert body["submission_id"] == "test-submission-id"
    assert body["agent_version"] == "v0.3.0"
    assert len(body["scores"]) == 4
    for s in body["scores"]:
        assert 1 <= s["score"] <= 10
        assert s["justification"]


def test_score_endpoint_not_found(_mock_scoring, monkeypatch):
    """A submission ID with no parsed text returns 404."""
    monkeypatch.setattr(supabase, "get_parsed_submission", lambda sid: None)
    resp = client.post("/api/submissions/nonexistent-id/score")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_score_endpoint_groq_not_configured(_mock_scoring, monkeypatch):
    """When Groq is not configured, returns 503."""

    def fake_score(submission_id, parsed_text, groq_api_key=None):
        raise ValueError("Groq API key is not configured.")

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)
    resp = client.post("/api/submissions/test-submission-id/score")
    assert resp.status_code == 503
    assert "Groq" in resp.json()["detail"]


def test_score_endpoint_supabase_not_configured(_mock_scoring, monkeypatch):
    """When Supabase is not configured, returns 503."""

    def fake_get_parsed(submission_id):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "get_parsed_submission", fake_get_parsed)
    resp = client.post("/api/submissions/test-submission-id/score")
    assert resp.status_code == 503


def test_score_endpoint_groq_api_error(_mock_scoring, monkeypatch):
    """When Groq raises an API error, returns 503."""

    def fake_score(submission_id, parsed_text, groq_api_key=None):
        raise GroqError("API error")

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)
    resp = client.post("/api/submissions/test-submission-id/score")
    assert resp.status_code == 503
    assert "Scoring failed" in resp.json()["detail"]


def test_score_endpoint_runtime_error(_mock_scoring, monkeypatch):
    """When scoring fails with RuntimeError (persistent malformed JSON), returns 500."""

    def fake_score(submission_id, parsed_text, groq_api_key=None):
        raise RuntimeError("Failed to get valid JSON from Groq")

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)
    resp = client.post("/api/submissions/test-submission-id/score")
    assert resp.status_code == 500
