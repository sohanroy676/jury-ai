"""Tests for the batch scoring endpoint (POST /api/submissions/score-pending)."""

import pytest
from fastapi.testclient import TestClient
from groq import GroqError

from agents.scoring.scorer import AGENT_VERSION, CriterionScore, ScoringResult
from backend.main import app
from backend.services import supabase

client = TestClient(app)


class FakeStore:
    """In-memory stand-in for the Supabase service surface."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.score_rows: list[dict] = []
        self.parsed: dict[str, dict] = {}
        self.inserted: list[tuple[str, str]] = []

    def add_submission(self, sid: str, team_name: str) -> None:
        self.submissions.append(
            {"id": sid, "team_name": team_name, "file_type": "pdf", "status": "parsed"}
        )

    def set_parsed(self, sid: str) -> None:
        self.parsed[sid] = {
            "id": f"parsed-{sid}",
            "submission_id": sid,
            "raw_text": f"Test text for {sid}.",
            "sections": [],
            "source_format": "pdf",
        }

    def add_scores(self, sid: str, criteria: list[str]) -> None:
        for criterion in criteria:
            self.score_rows.append(
                {
                    "submission_id": sid,
                    "criterion": criterion,
                    "score": 5,
                }
            )

    # --- Service-layer surface used by the scoring routes ---

    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self, hackathon_id: str = "default") -> list[dict]:
        return [dict(r) for r in self.score_rows]

    def get_parsed_submission(self, sid: str) -> dict | None:
        row = self.parsed.get(sid)
        return dict(row) if row else None

    def insert_scores(self, sid: str, scores, agent_version: str, hackathon_id: str = "default") -> list[dict]:
        self.inserted.append((sid, agent_version))
        return [
            {"submission_id": sid, "criterion": s.criterion, "score": s.score}
            for s in scores
        ]


@pytest.fixture
def store(monkeypatch):
    """Wire the FakeStore into the service module and return it."""
    fake = FakeStore()
    monkeypatch.setattr(supabase, "list_submissions", fake.list_submissions)
    monkeypatch.setattr(supabase, "get_all_scores", fake.get_all_scores)
    monkeypatch.setattr(supabase, "get_parsed_submission", fake.get_parsed_submission)
    monkeypatch.setattr(supabase, "insert_scores", fake.insert_scores)
    return fake


@pytest.fixture
def score_calls(monkeypatch):
    """Replace the scorer with a deterministic success and record calls."""
    calls: list[str] = []

    async def fake_score(submission_id, parsed_text, groq_api_key=None):
        calls.append(submission_id)
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(criterion=c, score=7, justification="ok.")
                for c in (
                    "problem_fit",
                    "technical_depth",
                    "feasibility",
                    "innovation",
                )
            ],
        )

    monkeypatch.setattr("backend.routes.scoring.score_submission", fake_score)
    return calls


def test_batch_scores_all_pending(store, score_calls):
    """Unscored submissions are all scored, in order, and stored."""
    store.add_submission("id-a", "Alpha")
    store.add_submission("id-b", "Beta")
    store.set_parsed("id-a")
    store.set_parsed("id-b")

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 2
    assert body["failed"] == 0
    assert body["remaining"] == 0
    # list_submissions is newest-first, so id-b comes before id-a.
    assert [r["submission_id"] for r in body["results"]] == ["id-b", "id-a"]
    assert all(r["ok"] for r in body["results"])
    assert all(r["agent_version"] == AGENT_VERSION for r in body["results"])
    assert sorted(score_calls) == ["id-a", "id-b"]
    assert {sid for sid, _ in store.inserted} == {"id-a", "id-b"}


def test_batch_skips_complete_scored(store, score_calls):
    """A submission with all four criteria already is never re-scored."""
    store.add_submission("done", "Done")
    store.add_submission("fresh", "Fresh")
    store.set_parsed("done")
    store.set_parsed("fresh")
    store.add_scores(
        "done", ["problem_fit", "technical_depth", "feasibility", "innovation"]
    )

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 1
    assert body["results"][0]["submission_id"] == "fresh"
    assert score_calls == ["fresh"]


def test_batch_rescores_partial(store, score_calls):
    """A partially-scored submission counts as pending and re-scores."""
    store.add_submission("half", "Halfway")
    store.set_parsed("half")
    store.add_scores("half", ["problem_fit", "innovation"])

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 1
    assert score_calls == ["half"]


def test_batch_continues_after_failure(store, monkeypatch):
    """A Groq failure on one item records it as failed and keeps going."""
    store.add_submission("bad", "Bad")
    store.add_submission("good", "Good")
    store.set_parsed("bad")
    store.set_parsed("good")

    async def flaky_score(submission_id, parsed_text, groq_api_key=None):
        if submission_id == "bad":
            raise GroqError("API error")
        return ScoringResult(
            submission_id=submission_id,
            scores=[
                CriterionScore(criterion="problem_fit", score=6, justification="ok.")
            ],
        )

    monkeypatch.setattr("backend.routes.scoring.score_submission", flaky_score)

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["failed"] == 1
    assert body["scored"] == 1
    by_id = {r["submission_id"]: r for r in body["results"]}
    assert by_id["bad"]["ok"] is False
    assert "Scoring failed" in by_id["bad"]["error"]
    assert by_id["good"]["ok"] is True


def test_batch_empty_queue(store, score_calls):
    """With no submissions at all, nothing is attempted."""
    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"scored": 0, "failed": 0, "remaining": 0, "results": []}
    assert score_calls == []


def test_batch_all_complete_nothing_pending(store, score_calls):
    """An all-complete pool reports zero work without touching Groq."""
    store.add_submission("done", "Done")
    store.add_scores(
        "done", ["problem_fit", "technical_depth", "feasibility", "innovation"]
    )

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 0
    assert body["remaining"] == 0
    assert body["results"] == []
    assert score_calls == []


def test_batch_respects_limit(store, score_calls):
    """limit caps how many pending items this call attempts."""
    for i in range(5):
        sid = f"id-{i}"
        store.add_submission(sid, f"Team{i}")
        store.set_parsed(sid)

    resp = client.post("/api/submissions/score-pending?limit=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 2
    assert body["remaining"] == 3
    assert len(score_calls) == 2


@pytest.mark.parametrize("limit", [0, -1, 51])
def test_batch_rejects_out_of_range_limit(limit):
    """limit outside 1..50 is rejected before any work happens."""
    resp = client.post(f"/api/submissions/score-pending?limit={limit}")
    assert resp.status_code == 422


def test_batch_supabase_unconfigured(monkeypatch):
    """Supabase listing failures map to 503."""

    def broken(limit: int = 100):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "list_submissions", broken)

    resp = client.post("/api/submissions/score-pending")
    assert resp.status_code == 503


def test_batch_reports_unparsed_item_and_continues(store, score_calls):
    """An unparsed submission fails its own entry but not the batch."""
    store.add_submission("noparse", "NoParse")
    store.add_submission("fine", "Fine")
    # noparse deliberately has NO parsed row.
    store.set_parsed("fine")

    resp = client.post("/api/submissions/score-pending")

    assert resp.status_code == 200
    body = resp.json()
    assert body["failed"] == 1
    assert body["scored"] == 1
    by_id = {r["submission_id"]: r for r in body["results"]}
    assert by_id["noparse"]["ok"] is False
    assert "not found or not yet parsed" in by_id["noparse"]["error"]
    assert by_id["fine"]["ok"] is True
    assert score_calls == ["fine"]
