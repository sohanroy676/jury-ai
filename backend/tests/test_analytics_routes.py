"""Tests for analytics dashboard API routes (v3.2.0)."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import supabase

client = TestClient(app)


class FakeAnalyticsStore:
    """In-memory stand-in for analytics queries."""

    def __init__(self):
        self.submissions = [
            {"id": "sub-1", "team_name": "Alpha", "status": "submitted", "hackathon_id": "default"},
            {"id": "sub-2", "team_name": "Beta", "status": "submitted", "hackathon_id": "default"},
        ]
        self.scores = [
            {"submission_id": "sub-1", "criterion": "problem_fit", "score": 8, "hackathon_id": "default"},
            {"submission_id": "sub-1", "criterion": "technical_depth", "score": 9, "hackathon_id": "default"},
            {"submission_id": "sub-1", "criterion": "feasibility", "score": 7, "hackathon_id": "default"},
            {"submission_id": "sub-1", "criterion": "innovation", "score": 8, "hackathon_id": "default"},
            {"submission_id": "sub-2", "criterion": "problem_fit", "score": 5, "hackathon_id": "default"},
            {"submission_id": "sub-2", "criterion": "technical_depth", "score": 6, "hackathon_id": "default"},
            {"submission_id": "sub-2", "criterion": "feasibility", "score": 5, "hackathon_id": "default"},
            {"submission_id": "sub-2", "criterion": "innovation", "score": 4, "hackathon_id": "default"},
        ]

    def get_all_submissions(self, hackathon_id: str = "default"):
        return [s for s in self.submissions if s["hackathon_id"] == hackathon_id]

    def get_all_scores(self, hackathon_id: str = "default"):
        return [s for s in self.scores if s["hackathon_id"] == hackathon_id]

    def get_all_parsed_ids(self, hackathon_id: str = "default"):
        return 2

    def get_feedback_count(self, hackathon_id: str = "default"):
        return 2

    def get_shortlisted_count(self, hackathon_id: str = "default"):
        return 1

    def get_appeal_count(self, hackathon_id: str = "default"):
        return 0


@pytest.fixture
def store(monkeypatch):
    fake = FakeAnalyticsStore()
    monkeypatch.setattr(supabase, "get_all_submissions", fake.get_all_submissions)
    monkeypatch.setattr(supabase, "get_all_scores", fake.get_all_scores)
    monkeypatch.setattr(supabase, "get_all_parsed_ids", fake.get_all_parsed_ids)
    monkeypatch.setattr(supabase, "get_feedback_count", fake.get_feedback_count)
    monkeypatch.setattr(supabase, "get_shortlisted_count", fake.get_shortlisted_count)
    monkeypatch.setattr(supabase, "get_appeal_count", fake.get_appeal_count)
    return fake


def test_analytics_overview(store):
    resp = client.get("/api/analytics/default/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hackathon_id"] == "default"
    assert body["total_submissions"] == 2
    assert body["scored_count"] == 2
    assert body["shortlisted_count"] == 1
    assert "problem_fit" in body["criterion_averages"]


def test_analytics_distributions(store):
    resp = client.get("/api/analytics/default/distributions")
    assert resp.status_code == 200
    body = resp.json()
    assert "distributions" in body
    dist = body["distributions"]
    assert "problem_fit" in dist
    assert "composite" in dist
    assert len(dist["problem_fit"]) == 10


def test_analytics_funnel(store):
    resp = client.get("/api/analytics/default/funnel")
    assert resp.status_code == 200
    body = resp.json()
    funnel = body["funnel"]
    assert funnel["submitted"] == 2
    assert funnel["parsed"] == 2
    assert funnel["scored"] == 2
    assert funnel["shortlisted"] == 1
    assert funnel["appealed"] == 0


def test_analytics_heatmap(store):
    resp = client.get("/api/analytics/default/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["heatmap"]) == 2
    top = body["heatmap"][0]
    assert top["team_name"] == "Alpha"
    assert top["composite"] == 8.0
