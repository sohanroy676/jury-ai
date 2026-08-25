"""Tests for the v0.7.0 feedback API routes.

The Supabase service layer is mocked with a small in-memory store and
the FeedbackAgent is replaced with a recording fake, so tests prove the
routes are correctly WIRED (404/409/503 mapping, ranking context
plumb-through, persistence) without touching the network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import version
from agents.feedback import FeedbackResult
from backend.main import app
from backend.services import supabase

client = TestClient(app)

CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]


def _fake_feedback_result(submission_id: str, verdict: str = "shortlist"):
    return FeedbackResult(
        submission_id=submission_id,
        strengths=["Cited 500-farmer survey"],
        weaknesses=["No architecture diagram"],
        suggestion="Add a load-test report.",
        verdict=verdict,
    )


class FakeStore:
    """In-memory stand-in for submissions/scores/rubric/feedback tables."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.rubrics: dict[str, dict[str, float]] = {}
        self.feedback: dict[str, dict] = {}
        self.configured = True

    # Service-layer surface used by the feedback route.
    def get_submission(self, submission_id: str) -> dict | None:
        return next((s for s in self.submissions if s["id"] == submission_id), None)

    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self) -> list[dict]:
        return [dict(r) for r in self.scores]

    def get_scores(self, submission_id: str) -> list[dict]:
        return [dict(r) for r in self.scores if r["submission_id"] == submission_id]

    def get_rubric(self, hackathon_id: str) -> dict[str, float] | None:
        if not self.configured:
            raise supabase.SupabaseNotConfiguredError("not configured")
        return {c: w for c, w in self.rubrics.get(hackathon_id, {}).items()} or None

    def upsert_feedback(self, submission_id: str, **fields) -> dict:
        row = {"submission_id": submission_id, **fields}
        self.feedback[submission_id] = row
        return dict(row)

    def get_feedback(self, submission_id: str) -> dict | None:
        row = self.feedback.get(submission_id)
        return dict(row) if row else None

    # Test-data helpers.
    def add_submission(self, sid: str, team: str) -> None:
        self.submissions.append({"id": sid, "team_name": team})

    def add_scores(
        self, sid: str, criteria: list[str] | None = None, **by_criterion
    ) -> None:
        full = {
            "problem_fit": 5,
            "technical_depth": 5,
            "feasibility": 5,
            "innovation": 5,
        }
        full.update(by_criterion)
        for criterion in criteria or CRITERIA:
            self.scores.append(
                {
                    "submission_id": sid,
                    "criterion": criterion,
                    "score": full[criterion],
                    "justification": f"{criterion} evidence for {sid}",
                }
            )


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    for name in (
        "get_submission",
        "list_submissions",
        "get_all_scores",
        "get_scores",
        "get_rubric",
        "upsert_feedback",
        "get_feedback",
    ):
        monkeypatch.setattr(supabase, name, getattr(fake, name))
    return fake


@pytest.fixture
def agent_calls(monkeypatch):
    """Replace generate_feedback with a recording async fake."""
    calls: list[dict] = []

    async def fake_generate(**kwargs):
        calls.append(kwargs)
        verdict = "reject" if not kwargs["shortlisted"] else "shortlist"
        return _fake_feedback_result(kwargs["submission_id"], verdict)

    monkeypatch.setattr("backend.routes.feedback.generate_feedback", fake_generate)
    return calls


# --- POST happy paths -----------------------------------------------------------


def test_post_feedback_returns_full_context_and_persists(store, agent_calls):
    store.add_submission("id-top", "Alpha")
    store.add_submission("id-low", "Bravo")
    store.add_scores("id-top", problem_fit=9, innovation=8)
    store.add_scores("id-low", problem_fit=3, innovation=2)

    resp = client.post("/api/submissions/id-top/feedback?top_n=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["submission_id"] == "id-top"
    assert body["agent_version"] == f"v{version.APP_VERSION}"
    ctx = body["ranking_context"]
    assert ctx["composite_score"] > 0
    assert ctx["rank"] == 1
    assert ctx["scored_count"] == 2
    assert ctx["shortlisted"] is True

    # The agent saw canonical criterion order + real justifications.
    call = agent_calls[0]
    assert [s["criterion"] for s in call["scores"]] == CRITERIA
    assert call["team_name"] == "Alpha"
    assert all(s["justification"] for s in call["scores"])
    assert call["rank"] == 1 and call["total_scored"] == 2

    # Persisted exactly via the upsert path.
    assert store.feedback["id-top"]["verdict"] in ("shortlist", "reject")


def test_post_feedback_flags_unshortlisted_teams(store, agent_calls):
    store.add_submission("id-top", "Alpha")
    store.add_submission("id-low", "Bravo")
    store.add_scores("id-top", problem_fit=9)
    store.add_scores("id-low", problem_fit=3)

    resp = client.post("/api/submissions/id-low/feedback?top_n=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ranking_context"]["shortlisted"] is False
    # Tone follows the shortlist decision (roadmap DoD).
    assert body["feedback"]["verdict"] == "reject"


def test_post_feedback_default_top_n_is_five(store, agent_calls):
    for i in range(6):
        sid = f"id-{i}"
        store.add_submission(sid, f"Team{i}")
        store.add_scores(sid, problem_fit=10 - i)

    client.post("/api/submissions/id-5/feedback")  # rank 6 of 6
    assert agent_calls[-1]["shortlisted"] is False
    client.post("/api/submissions/id-1/feedback")  # rank 2 of 6
    assert agent_calls[-1]["shortlisted"] is True


def test_post_feedback_uses_configured_rubric_for_composite(store, agent_calls):
    store.rubrics["default"] = {
        "problem_fit": 1.0,
        "technical_depth": 0.0,
        "feasibility": 0.0,
        "innovation": 0.0,
    }
    store.add_submission("id-a", "Alpha")
    store.add_scores("id-a", problem_fit=8)

    resp = client.post("/api/submissions/id-a/feedback")
    body = resp.json()
    assert body["rubric_source"] == "configured"
    assert body["ranking_context"]["composite_score"] == 8.0
    assert agent_calls[0]["composite_score"] == 8.0


# --- Error / state paths --------------------------------------------------------


def test_post_feedback_unknown_submission_404(store, agent_calls):
    resp = client.post("/api/submissions/nope/feedback")
    assert resp.status_code == 404


def test_post_feedback_unscored_submission_409(store, agent_calls):
    store.add_submission("id-x", "XRay")
    resp = client.post("/api/submissions/id-x/feedback")
    assert resp.status_code == 409
    assert "no complete score set" in resp.json()["detail"]


def test_post_feedback_partial_scores_409(store, agent_calls):
    store.add_submission("id-p", "Partial")
    store.add_scores("id-p", criteria=["problem_fit"])
    resp = client.post("/api/submissions/id-p/feedback")
    assert resp.status_code == 409


@pytest.mark.parametrize("top_n", ["0", "-2"])
def test_post_feedback_rejects_bad_top_n(store, agent_calls, top_n):
    resp = client.post(f"/api/submissions/any/feedback?top_n={top_n}")
    assert resp.status_code == 422


def test_post_feedback_supabase_down_503(store, agent_calls, monkeypatch):
    def broken(*args, **kwargs):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "get_submission", broken)
    resp = client.post("/api/submissions/id-a/feedback")
    assert resp.status_code == 503


def test_post_feedback_missing_groq_key_maps_to_503(store, monkeypatch):
    store.add_submission("id-a", "Alpha")
    store.add_scores("id-a")

    async def no_key(**kwargs):
        raise ValueError("Groq API key is not configured.")

    monkeypatch.setattr("backend.routes.feedback.generate_feedback", no_key)
    resp = client.post("/api/submissions/id-a/feedback")
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_post_feedback_agent_runtime_error_maps_to_500(store, monkeypatch):
    store.add_submission("id-a", "Alpha")
    store.add_scores("id-a")

    async def boom(**kwargs):
        raise RuntimeError("invalid JSON forever")

    monkeypatch.setattr("backend.routes.feedback.generate_feedback", boom)
    resp = client.post("/api/submissions/id-a/feedback")
    assert resp.status_code == 500


# --- GET --------------------------------------------------------------------------


def test_get_feedback_returns_stored_row(store):
    store.feedback["id-a"] = {"submission_id": "id-a", "verdict": "shortlist"}
    resp = client.get("/api/submissions/id-a/feedback")
    assert resp.status_code == 200
    assert resp.json()["feedback"]["verdict"] == "shortlist"


def test_get_feedback_returns_null_when_absent(store):
    resp = client.get("/api/submissions/id-none/feedback")
    assert resp.status_code == 200
    assert resp.json()["feedback"] is None


def test_get_feedback_supabase_down_503(store, monkeypatch):
    def broken(*args, **kwargs):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "get_feedback", broken)
    resp = client.get("/api/submissions/id-a/feedback")
    assert resp.status_code == 503
