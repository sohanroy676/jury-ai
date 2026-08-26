"""Tests for the v1.2.0 batch feedback endpoint (POST /api/submissions/feedback-pending).

Mirrors test_batch_scoring.py: the Supabase service layer and the
FeedbackAgent are replaced with in-memory/recording fakes, and the mailer
is autouse-mocked so tests can never send real email. The tests pin the
pending definition (complete score set AND no current feedback row),
best-composite-first ordering, per-item failure isolation, and the
limit/remaining contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from groq import GroqError

from agents.feedback import FeedbackResult
from backend.main import app
from backend.services import email as email_service
from backend.services import supabase

client = TestClient(app)

CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]


class FakeStore:
    """In-memory stand-in for the Supabase service surface."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.rubrics: dict[str, dict[str, float]] = {}
        self.feedback: dict[str, dict] = {}

    # --- Test-data helpers -------------------------------------------------

    def add_submission(self, sid: str, team: str, email: str | None = None) -> None:
        self.submissions.append({"id": sid, "team_name": team, "team_email": email})

    def add_full_scores(self, sid: str, base: int = 5) -> None:
        for criterion in CRITERIA:
            self.scores.append(
                {
                    "submission_id": sid,
                    "criterion": criterion,
                    "score": base,
                    "justification": f"{criterion} evidence for {sid}",
                }
            )

    def add_partial_scores(self, sid: str) -> None:
        self.scores.append(
            {
                "submission_id": sid,
                "criterion": "problem_fit",
                "score": 4,
                "justification": "partial",
            }
        )

    def set_feedback(self, sid: str, verdict: str = "shortlist") -> None:
        self.feedback[sid] = {"submission_id": sid, "verdict": verdict}

    # --- Service-layer surface used by the feedback routes -----------------

    def get_submission(self, sid: str) -> dict | None:
        return next((s for s in self.submissions if s["id"] == sid), None)

    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self) -> list[dict]:
        return [dict(r) for r in self.scores]

    def get_scores(self, sid: str) -> list[dict]:
        return [dict(r) for r in self.scores if r["submission_id"] == sid]

    def get_rubric(self, hackathon_id: str) -> dict[str, float] | None:
        return {c: w for c, w in self.rubrics.get(hackathon_id, {}).items()} or None

    def upsert_feedback(self, sid: str, **fields) -> dict:
        row = {"submission_id": sid, **fields}
        self.feedback[sid] = row
        return dict(row)

    def get_feedback(self, sid: str) -> dict | None:
        row = self.feedback.get(sid)
        return dict(row) if row else None

    def get_all_feedback_ids(self) -> set[str]:
        return set(self.feedback)


@pytest.fixture
def store(monkeypatch):
    """Wire the FakeStore into the service module and return it."""
    fake = FakeStore()
    for name in (
        "get_submission",
        "list_submissions",
        "get_all_scores",
        "get_scores",
        "get_rubric",
        "upsert_feedback",
        "get_feedback",
        "get_all_feedback_ids",
    ):
        monkeypatch.setattr(supabase, name, getattr(fake, name))
    return fake


@pytest.fixture(autouse=True)
def mailer(monkeypatch):
    """Route tests must never touch real transports (the developer's .env
    may hold live credentials). Mirrors the service skip/sent contract."""
    calls: list[dict] = []

    def fake_results(**kwargs):
        calls.append(kwargs)
        if not str(kwargs.get("team_email") or "").strip():
            return email_service.EmailResult("skipped", "no_valid_recipient")
        return email_service.EmailResult("sent", "sent")

    monkeypatch.setattr(email_service, "send_results_notification", fake_results)
    return calls


@pytest.fixture
def agent_calls(monkeypatch):
    """Replace generate_feedback with a recording async fake."""
    calls: list[dict] = []

    async def fake_generate(**kwargs):
        calls.append(kwargs)
        verdict = "shortlist" if kwargs["shortlisted"] else "reject"
        return FeedbackResult(
            submission_id=kwargs["submission_id"],
            strengths=["Cited evidence"],
            weaknesses=["Missing metrics"],
            suggestion="Add benchmarks.",
            verdict=verdict,
        )

    monkeypatch.setattr("backend.routes.feedback.generate_feedback", fake_generate)
    return calls


# --- Batch behaviour -------------------------------------------------------------


def test_batch_generates_only_missing_feedback(store, agent_calls, mailer):
    """Teams WITH feedback are skipped; only the gap is filled."""
    store.add_submission("id-a", "Alpha", email="a@example.com")
    store.add_submission("id-b", "Bravo", email="b@example.com")
    store.add_submission("id-c", "Charlie", email="c@example.com")
    for sid in ("id-a", "id-b", "id-c"):
        store.add_full_scores(sid)
    store.set_feedback("id-c")

    resp = client.post("/api/submissions/feedback-pending?top_n=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] == 2
    assert body["failed"] == 0
    assert body["remaining"] == 0
    attempted = {r["submission_id"] for r in body["results"]}
    assert attempted == {"id-a", "id-b"}
    assert all(r["ok"] for r in body["results"])
    # Exactly one Groq call + one results email per generated team.
    assert len(agent_calls) == 2
    assert len(mailer) == 2


def test_batch_skips_unscored_and_partial_teams(store, agent_calls, mailer):
    """Incomplete score sets are invisible to the batch (ranking rule)."""
    store.add_submission("id-none", "NoScores")
    store.add_submission("id-partial", "Partial")
    store.add_submission("id-full", "Full", email="f@example.com")
    store.add_full_scores("id-full")

    resp = client.post("/api/submissions/feedback-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] == 1
    assert [r["submission_id"] for r in body["results"]] == ["id-full"]
    assert len(agent_calls) == 1
    assert mailer[0]["team_email"] == "f@example.com"


def test_batch_processes_best_composite_first(store, agent_calls):
    """Ranked order: highest composite gets its result first."""
    store.add_submission("id-low", "Low", email="low@example.com")
    store.add_submission("id-high", "High", email="high@example.com")
    store.add_full_scores("id-low", base=3)
    store.add_full_scores("id-high", base=9)

    resp = client.post("/api/submissions/feedback-pending?top_n=1")

    assert resp.status_code == 200
    by_id = {r["submission_id"]: r for r in resp.json()["results"]}
    assert by_id["id-high"]["verdict"] == "shortlist"
    assert by_id["id-low"]["verdict"] == "reject"
    assert [c["submission_id"] for c in agent_calls] == ["id-high", "id-low"]
    assert agent_calls[0]["shortlisted"] is True
    assert agent_calls[1]["shortlisted"] is False


def test_batch_respects_limit_and_reports_remaining(store, agent_calls):
    for i in range(4):
        store.add_submission(f"id-{i}", f"Team{i}")
        store.add_full_scores(f"id-{i}")

    resp = client.post("/api/submissions/feedback-pending?limit=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] == 2
    assert body["remaining"] == 2
    assert len(agent_calls) == 2


def test_batch_item_failure_never_aborts_run(store, agent_calls, monkeypatch):
    """A Groq failure marks its own item failed; the rest still generate."""

    async def flaky(**kwargs):
        if kwargs["submission_id"] == "bad":
            raise GroqError("API error")
        verdict = "shortlist" if kwargs["shortlisted"] else "reject"
        return FeedbackResult(
            submission_id=kwargs["submission_id"],
            strengths=["s"],
            weaknesses=["w"],
            suggestion="Do better.",
            verdict=verdict,
        )

    monkeypatch.setattr("backend.routes.feedback.generate_feedback", flaky)

    store.add_submission("bad", "Bad", email="bad@example.com")
    store.add_submission("good", "Good", email="good@example.com")
    store.add_full_scores("bad")
    store.add_full_scores("good")

    resp = client.post("/api/submissions/feedback-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] == 1
    assert body["failed"] == 1
    by_id = {r["submission_id"]: r for r in body["results"]}
    assert by_id["bad"]["ok"] is False
    assert "Feedback failed" in by_id["bad"]["error"]
    assert by_id["good"]["ok"] is True


def test_batch_empty_pool(store, agent_calls):
    """With no submissions at all, nothing is attempted."""
    resp = client.post("/api/submissions/feedback-pending")

    assert resp.status_code == 200
    assert resp.json() == {
        "generated": 0,
        "failed": 0,
        "remaining": 0,
        "results": [],
    }
    assert agent_calls == []


# --- Error / validation paths ------------------------------------------------------


def test_batch_all_have_feedback_nothing_pending(store, agent_calls):
    """An all-feedbacked pool reports zero work without touching Groq."""
    store.add_submission("done", "Done", email="d@example.com")
    store.add_full_scores("done")
    store.set_feedback("done")

    resp = client.post("/api/submissions/feedback-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] == 0
    assert body["remaining"] == 0
    assert body["results"] == []
    assert agent_calls == []


def test_batch_supabase_down_503(monkeypatch):
    def broken(limit: int = 100):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "list_submissions", broken)
    resp = client.post("/api/submissions/feedback-pending")
    assert resp.status_code == 503


@pytest.mark.parametrize("limit", [0, -1, 51])
def test_batch_rejects_out_of_range_limit(limit):
    resp = client.post(f"/api/submissions/feedback-pending?limit={limit}")
    assert resp.status_code == 422


def test_batch_rejects_bad_top_n():
    resp = client.post("/api/submissions/feedback-pending?top_n=0")
    assert resp.status_code == 422


# --- Single-endpoint regression -----------------------------------------------------


def test_single_feedback_endpoint_still_wired_after_refactor(
    store, agent_calls, mailer
):
    """The refactor into _generate_one_feedback must not change the
    single-team contract (404/409 mapping, response shape)."""
    store.add_submission("id-solo", "Solo", email="solo@example.com")
    store.add_full_scores("id-solo", base=7)

    resp = client.post("/api/submissions/id-solo/feedback?top_n=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["feedback"]["verdict"] in ("shortlist", "reject")
    assert body["notification"]["results_email"]["status"] == "sent"
    assert body["ranking_context"]["rank"] == 1
