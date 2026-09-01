"""Tests for the v1.3.0 appeal API routes.

The Supabase service layer is mocked with an in-memory store and the
email seam is autouse-mocked (route tests must never touch real mail
transports). Covers: filing gates (results published, one live appeal),
validation, the evaluator queue with full context, and resolution
transitions + emails.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import email as email_service
from backend.services import supabase

client = TestClient(app)

SUBMISSION_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def mailer(monkeypatch):
    """Never touch real mail transports; record calls instead."""
    calls: list[dict] = []

    def fake_confirmation(**kwargs):
        calls.append(("confirmation", kwargs))
        if not str(kwargs.get("team_email") or "").strip():
            return email_service.EmailResult("skipped", "no_valid_recipient")
        return email_service.EmailResult("sent", "sent")

    def fake_resolution(**kwargs):
        calls.append(("resolution", kwargs))
        if not str(kwargs.get("team_email") or "").strip():
            return email_service.EmailResult("skipped", "no_valid_recipient")
        return email_service.EmailResult("sent", "sent")

    monkeypatch.setattr(email_service, "send_appeal_confirmation", fake_confirmation)
    monkeypatch.setattr(email_service, "send_appeal_resolution", fake_resolution)
    return calls


class FakeStore:
    """In-memory stand-in for submissions/scores/feedback/appeals."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.feedback: dict[str, dict] = {}
        self.appeals: list[dict] = []

    def add_submission(self, sid: str, team: str, email: str | None = None):
        self.submissions.append({"id": sid, "team_name": team, "team_email": email})

    def add_feedback(self, sid: str, verdict: str = "shortlist"):
        self.feedback[sid] = {
            "submission_id": sid,
            "verdict": verdict,
            "strengths": ["Good"],
            "weaknesses": ["Weak"],
            "suggestion": "Improve",
        }

    def add_scores(self, sid: str):
        for c in ("problem_fit", "technical_depth", "feasibility", "innovation"):
            self.scores.append(
                {
                    "submission_id": sid,
                    "criterion": c,
                    "score": 7,
                    "justification": f"{c} is solid.",
                }
            )

    # --- supabase service surface -------------------------------------

    def get_submission(self, sid: str) -> dict | None:
        return next((s for s in self.submissions if s["id"] == sid), None)

    def get_feedback(self, sid: str) -> dict | None:
        return self.feedback.get(sid)

    def get_scores(self, sid: str) -> list[dict]:
        return [dict(r) for r in self.scores if r["submission_id"] == sid]

    def insert_appeal(self, sid: str, text: str) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "submission_id": sid,
            "appeal_text": text,
            "status": "pending",
            "created_at": "2026-09-01T00:00:00Z",
        }
        self.appeals.append(row)
        return dict(row)

    def get_appeal(self, sid: str) -> dict | None:
        return next((a for a in self.appeals if a["submission_id"] == sid), None)

    def get_appeal_by_id(self, aid: str) -> dict | None:
        return next((a for a in self.appeals if a["id"] == aid), None)

    def list_appeals(self, status: str | None = None) -> list[dict]:
        rows = self.appeals
        if status:
            rows = [a for a in rows if a["status"] == status]
        return [dict(a) for a in rows]

    def update_appeal(
        self,
        aid: str,
        *,
        status: str,
        evaluator_notes: str,
        resolved_by: str,
        resolved_at: str | None,
    ) -> dict | None:
        row = next((a for a in self.appeals if a["id"] == aid), None)
        if row is None:
            return None
        row["status"] = status
        row["evaluator_notes"] = evaluator_notes
        row["resolved_by"] = resolved_by
        if resolved_at:
            row["resolved_at"] = resolved_at
        return dict(row)


@pytest.fixture(autouse=True)
def store(monkeypatch):
    """Wire the FakeStore into the supabase service module."""
    fake = FakeStore()
    fake.add_submission(SUBMISSION_ID, "Moonshot", "moonshot@example.com")
    fake.add_feedback(SUBMISSION_ID)
    fake.add_scores(SUBMISSION_ID)

    for name in (
        "get_submission",
        "get_feedback",
        "get_scores",
        "insert_appeal",
        "get_appeal",
        "get_appeal_by_id",
        "list_appeals",
        "update_appeal",
    ):
        monkeypatch.setattr(supabase, name, getattr(fake, name))
    return fake


def _appeal_body(text: str | None = None):
    return {
        "appeal_text": text
        or "We believe the technical depth score was too low given our working prototype and load tests."
    }


def test_file_appeal_success(store, mailer):
    resp = client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["notification"]["appeal_confirmation"]["status"] == "sent"
    assert len(store.appeals) == 1
    assert mailer[0][0] == "confirmation"


def test_file_appeal_requires_published_results(store, monkeypatch):
    monkeypatch.setattr(supabase, "get_feedback", lambda sid: None)
    resp = client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    assert resp.status_code == 409
    assert "not been published" in resp.json()["detail"]


def test_file_appeal_duplicate_rejected(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    resp = client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_file_appeal_short_text_rejected(store):
    resp = client.post(
        f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body("too short")
    )
    assert resp.status_code == 422


def test_file_appeal_unknown_submission_404(store):
    resp = client.post(f"/api/submissions/{uuid.uuid4()}/appeal", json=_appeal_body())
    assert resp.status_code == 404


def test_file_appeal_supabase_down_503(store, monkeypatch):
    def _boom(sid):
        raise supabase.SupabaseNotConfiguredError("credentials missing")

    monkeypatch.setattr(supabase, "get_submission", _boom)
    resp = client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    assert resp.status_code == 503


def test_get_submission_appeal_returns_null_when_none(store):
    resp = client.get(f"/api/submissions/{SUBMISSION_ID}/appeal")
    assert resp.status_code == 200
    assert resp.json()["appeal"] is None


def test_get_submission_appeal_returns_row(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    resp = client.get(f"/api/submissions/{SUBMISSION_ID}/appeal")
    assert resp.status_code == 200
    assert resp.json()["appeal"]["status"] == "pending"


def test_list_appeals_queue_includes_full_context(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    resp = client.get("/api/appeals")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["appeals"]) == 1
    item = body["appeals"][0]
    assert item["submission"]["team_name"] == "Moonshot"
    assert len(item["scores"]) == 4
    assert item["feedback"]["verdict"] == "shortlist"


def test_list_appeals_filters_by_status(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    resp = client.get("/api/appeals?status=under_review")
    assert resp.status_code == 200
    assert resp.json()["appeals"] == []


def test_list_appeals_invalid_status_422(store):
    resp = client.get("/api/appeals?status=bogus")
    assert resp.status_code == 422


def test_resolve_appeal_to_under_review(store, mailer):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    aid = store.appeals[0]["id"]
    resp = client.put(
        f"/api/appeals/{aid}",
        json={
            "status": "under_review",
            "evaluator_notes": "Reviewing the prototype evidence.",
            "resolved_by": "alice@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "under_review"
    # No outcome email for a non-terminal transition.
    assert all(c[0] == "confirmation" for c in mailer)


def test_resolve_appeal_terminal_sends_email(store, mailer):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    aid = store.appeals[0]["id"]
    resp = client.put(
        f"/api/appeals/{aid}",
        json={
            "status": "upheld",
            "evaluator_notes": "The prototype clearly demonstrates the claimed capability.",
            "resolved_by": "alice@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "upheld"
    assert resp.json()["resolved_at"] is not None
    assert any(c[0] == "resolution" for c in mailer)


def test_resolve_appeal_invalid_transition_422(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    aid = store.appeals[0]["id"]
    resp = client.put(
        f"/api/appeals/{aid}",
        json={
            "status": "pending",
            "evaluator_notes": "This should be rejected.",
            "resolved_by": "alice@example.com",
        },
    )
    assert resp.status_code == 422


def test_resolve_appeal_unknown_404(store):
    resp = client.put(
        f"/api/appeals/{uuid.uuid4()}",
        json={
            "status": "upheld",
            "evaluator_notes": "This appeal does not exist.",
            "resolved_by": "alice@example.com",
        },
    )
    assert resp.status_code == 404


def test_resolve_appeal_notes_required(store):
    client.post(f"/api/submissions/{SUBMISSION_ID}/appeal", json=_appeal_body())
    aid = store.appeals[0]["id"]
    resp = client.put(
        f"/api/appeals/{aid}",
        json={
            "status": "upheld",
            "evaluator_notes": "short",
            "resolved_by": "alice@example.com",
        },
    )
    assert resp.status_code == 422
