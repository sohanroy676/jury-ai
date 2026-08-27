"""Tests for the v1.3.0 appeal flow (POST /api/appeals, the evaluator
queue, resolve, and the results-published gate).

Mirrors test_batch_feedback.py: the Supabase service layer is replaced with
an in-memory FakeStore and the mailer is autouse-mocked so tests can never
send real email and NO mail is emitted on any 4xx/5xx path. The tests pin
the results-published gate, one-open-appeal-per-submission, the appended
original AI context, the resolve invariant, and that appeal emails degrade
gracefully (never fail the filing/resolve).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import email as email_service
from backend.services import supabase

client = TestClient(app)

CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]

OPEN_VERDICTS = {"shortlist", "reject"}


def _uuid() -> str:
    return str(uuid.uuid4())


class FakeStore:
    """In-memory stand-in for the appeal + ranking service surface."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.rubrics: dict[str, dict[str, float]] = {}
        self.feedback: dict[str, dict] = {}
        self.appeals: list[dict] = []
        self.settings: dict[str, dict] = {}
        self._appeal_seq = 0

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

    def set_feedback(self, sid: str, verdict: str = "shortlist") -> None:
        assert verdict in OPEN_VERDICTS
        self.feedback[sid] = {
            "submission_id": sid,
            "verdict": verdict,
            "strengths": ["Cited 500-farmer survey"],
            "weaknesses": ["No architecture diagram"],
            "suggestion": "Add a load-test report.",
        }

    def publish_results(self, published: bool = True) -> None:
        self.settings["default"] = {
            "hackathon_id": "default",
            "results_published_at": "2026-08-27T00:00:00Z" if published else None,
        }

    def add_open_appeal(self, sid: str) -> dict:
        self._appeal_seq += 1
        appeal = {
            "id": _uuid(),
            "submission_id": sid,
            "hackathon_id": "default",
            "reason": "Pre-existing open appeal",
            "status": "open",
            "decision": None,
            "decision_note": "",
            "evaluator": "",
            "created_at": "2026-08-27T00:00:00Z",
            "decided_at": None,
        }
        self.appeals.append(appeal)
        return dict(appeal)

    # --- Service-layer surface used by the appeal routes --------------------

    # ranking inputs (load_leaderboard)
    def get_rubric(self, hackathon_id: str) -> dict[str, float] | None:
        return {c: w for c, w in self.rubrics.get(hackathon_id, {}).items()} or None

    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self) -> list[dict]:
        return [dict(r) for r in self.scores]

    # appeals
    def get_submission(self, sid: str) -> dict | None:
        return next((s for s in self.submissions if s["id"] == sid), None)

    def get_scores(self, sid: str) -> list[dict]:
        return [dict(r) for r in self.scores if r["submission_id"] == sid]

    def get_feedback(self, sid: str) -> dict | None:
        row = self.feedback.get(sid)
        return dict(row) if row else None

    def get_hackathon_settings(self, hackathon_id: str) -> dict | None:
        row = self.settings.get(hackathon_id)
        return dict(row) if row else None

    def update_results_published(self, hackathon_id: str, published: bool) -> dict:
        row = {
            "hackathon_id": hackathon_id,
            "results_published_at": "2026-08-27T00:00:00Z" if published else None,
        }
        self.settings[hackathon_id] = row
        return dict(row)

    def insert_appeal(
        self,
        submission_id: str,
        reason: str,
        contact_email: str | None = None,
        hackathon_id: str = "default",
    ) -> dict:
        self._appeal_seq += 1
        row = {
            "id": _uuid(),
            "submission_id": submission_id,
            "hackathon_id": hackathon_id,
            "reason": reason,
            "contact_email": contact_email,
            "status": "open",
            "decision": None,
            "decision_note": "",
            "evaluator": "",
            "created_at": "2026-08-27T00:00:00Z",
            "decided_at": None,
        }
        self.appeals.append(row)
        return dict(row)

    def get_appeal(self, appeal_id: str) -> dict | None:
        return next((a for a in self.appeals if a["id"] == appeal_id), None)

    def get_appeal_by_submission(self, submission_id: str) -> dict | None:
        matching = [a for a in self.appeals if a["submission_id"] == submission_id]
        if not matching:
            return None
        return dict(matching[-1])

    def list_appeals(self, status: str | None = None) -> list[dict]:
        rows = self.appeals
        if status in ("open", "resolved"):
            rows = [a for a in rows if a["status"] == status]
        return [dict(r) for r in reversed(rows)]

    def resolve_appeal(
        self, appeal_id: str, decision: str, decision_note: str, evaluator: str
    ) -> dict | None:
        for a in self.appeals:
            if a["id"] == appeal_id:
                a["status"] = "resolved"
                a["decision"] = decision
                a["decision_note"] = decision_note
                a["evaluator"] = evaluator
                a["decided_at"] = "2026-08-27T01:00:00Z"
                return dict(a)
        return None


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
        "get_feedback",
        "get_hackathon_settings",
        "update_results_published",
        "insert_appeal",
        "get_appeal",
        "get_appeal_by_submission",
        "list_appeals",
        "resolve_appeal",
    ):
        monkeypatch.setattr(supabase, name, getattr(fake, name))
    return fake


@pytest.fixture(autouse=True)
def mailer(monkeypatch):
    """Never touch real mail transports; record calls; skip on blank address."""
    calls: list[dict] = []

    def fake_submitted(**kwargs):
        calls.append(("submitted", kwargs))
        if not str(kwargs.get("team_email") or "").strip():
            return email_service.EmailResult("skipped", "no_valid_recipient")
        return email_service.EmailResult("sent", "sent")

    def fake_resolved(**kwargs):
        calls.append(("resolved", kwargs))
        if not str(kwargs.get("team_email") or "").strip():
            return email_service.EmailResult("skipped", "no_valid_recipient")
        return email_service.EmailResult("sent", "sent")

    monkeypatch.setattr(email_service, "send_appeal_submitted", fake_submitted)
    monkeypatch.setattr(email_service, "send_appeal_resolved", fake_resolved)
    return calls


def _scored_verdict_submission(store, verdict: str = "shortlist") -> str:
    """Seed a fully-scored, feedback-carrying submission; return its id."""
    sid = _uuid()
    store.add_submission(sid, "IdeaWorks", email="team@example.com")
    store.add_full_scores(sid, base=7)
    store.set_feedback(sid, verdict=verdict)
    return sid


# --- Results-published gate -------------------------------------------------


def test_appeal_rejected_when_results_not_published(store, mailer):
    """The appeal form is closed (403) until the evaluator publishes results."""
    sid = _scored_verdict_submission(store)

    resp = client.post(
        "/api/appeals", json={"submission_id": sid, "reason": "We disagree."}
    )

    assert resp.status_code == 403
    assert mailer == []


def test_appeal_allowed_after_results_published(store, mailer):
    """Publishing results opens the appeal window (201 on a valid filing)."""
    store.publish_results(True)
    sid = _scored_verdict_submission(store)

    resp = client.post(
        "/api/appeals", json={"submission_id": sid, "reason": "We disagree."}
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["context"]["team_name"] == "IdeaWorks"
    assert body["context"]["feedback"]["verdict"] == "shortlist"
    assert body["notification"]["appeal_email"]["status"] == "sent"
    assert len(mailer) == 1


# --- Validation / error paths -----------------------------------------------


def test_appeal_requires_reason(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)

    resp = client.post("/api/appeals", json={"submission_id": sid, "reason": ""})

    assert resp.status_code == 422
    assert mailer == []


def test_appeal_rejects_oversized_reason(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)

    resp = client.post(
        "/api/appeals", json={"submission_id": sid, "reason": "x" * 2001}
    )

    assert resp.status_code == 422
    assert mailer == []


def test_appeal_unknown_submission_404(store, mailer):
    store.publish_results(True)
    missing = _uuid()

    resp = client.post(
        "/api/appeals", json={"submission_id": missing, "reason": "Hello?"}
    )

    assert resp.status_code == 404
    assert mailer == []


def test_appeal_malformed_submission_id_404(store, mailer):
    store.publish_results(True)

    resp = client.post(
        "/api/appeals", json={"submission_id": "not-a-uuid", "reason": "Hello?"}
    )

    assert resp.status_code == 404
    assert mailer == []


def test_appeal_unscored_submission_422(store, mailer):
    """No verdict (missing feedback) means there is nothing to contest."""
    store.publish_results(True)
    sid = _uuid()
    store.add_submission(sid, "NoVerdict")
    store.add_full_scores(sid)

    resp = client.post(
        "/api/appeals", json={"submission_id": sid, "reason": "Score me."}
    )

    assert resp.status_code == 422
    assert mailer == []


def test_appeal_rejects_invalid_contact_email(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)

    resp = client.post(
        "/api/appeals",
        json={"submission_id": sid, "reason": "Hi", "contact_email": "nope"},
    )

    assert resp.status_code == 422
    assert mailer == []


# --- One open appeal per submission ------------------------------------------


def test_appeal_duplicate_open_is_conflict(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    store.add_open_appeal(sid)

    resp = client.post("/api/appeals", json={"submission_id": sid, "reason": "Again."})

    assert resp.status_code == 409
    assert mailer == []


def test_appeal_after_resolved_allows_new_filing(store, mailer):
    """A resolved appeal releases the one-open-per-submission slot."""
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)
    store.resolve_appeal(appeal["id"], "dismissed", "no", "evaluator-x")

    resp = client.post(
        "/api/appeals", json={"submission_id": sid, "reason": "New evidence."}
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "open"


# --- Appeals never block on mail ---------------------------------------------


def test_appeal_succeeds_even_if_mail_fails(store, monkeypatch):
    """Mail failure must never fail the filing (EmailResult, not a raise)."""
    store.publish_results(True)
    sid = _scored_verdict_submission(store)

    def broken(**kwargs):
        return email_service.EmailResult("failed", "provider_error", "boom")

    monkeypatch.setattr(email_service, "send_appeal_submitted", broken)

    resp = client.post("/api/appeals", json={"submission_id": sid, "reason": "Hello."})

    assert resp.status_code == 201
    assert resp.json()["notification"]["appeal_email"]["status"] == "failed"


# --- Team-facing lookup -------------------------------------------------------


def test_get_submission_appeal_404(store):
    resp = client.get(f"/api/appeals/submission/{_uuid()}")
    assert resp.status_code == 404


def test_get_submission_appeal_returns_latest(store):
    sid = _scored_verdict_submission(store)
    store.add_open_appeal(sid)

    resp = client.get(f"/api/appeals/submission/{sid}")

    assert resp.status_code == 200
    assert resp.json()["appeal"]["submission_id"] == sid
    assert resp.json()["appeal"]["status"] == "open"


# --- Evaluator queue ------------------------------------------------------------


def test_list_appeals_returns_enriched_queue(store):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    store.add_open_appeal(sid)

    resp = client.get("/api/appeals?status=open")

    assert resp.status_code == 200
    items = resp.json()["appeals"]
    assert len(items) == 1
    it = items[0]
    assert it["status"] == "open"
    # Original AI context is attached for the evaluator.
    assert it["context"]["team_name"] == "IdeaWorks"
    assert it["context"]["composite_score"] is not None
    assert it["context"]["scores"]
    assert it["context"]["scores"][0]["justification"]
    assert it["context"]["feedback"]["verdict"] == "shortlist"


def test_list_appeals_defaults_to_all(store):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)
    store.resolve_appeal(appeal["id"], "upheld", "fair", "evaluator-x")

    resp = client.get("/api/appeals")

    assert resp.status_code == 200
    assert len(resp.json()["appeals"]) == 1
    assert resp.json()["appeals"][0]["status"] == "resolved"


def test_list_appeals_rejects_bad_status():
    resp = client.get("/api/appeals?status=bogus")
    assert resp.status_code == 422


# --- Resolve ------------------------------------------------------------------


def test_resolve_appeal_happy_path(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={"decision": "upheld", "decision_note": "Reasonable.", "evaluator": "e-1"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["appeal"]["status"] == "resolved"
    assert body["appeal"]["decision"] == "upheld"
    assert body["appeal"]["evaluator"] == "e-1"
    assert body["notification"]["appeal_email"]["status"] == "sent"
    assert mailer[-1][0] == "resolved"


def test_resolve_appeal_dismissed(store, mailer):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={
            "decision": "dismissed",
            "decision_note": "No new grounds.",
            "evaluator": "e-2",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["appeal"]["decision"] == "dismissed"


def test_resolve_appeal_unknown_404(store):
    resp = client.post(
        f"/api/appeals/{_uuid()}/resolve",
        json={"decision": "upheld", "decision_note": "", "evaluator": "e"},
    )
    assert resp.status_code == 404


def test_resolve_appeal_malformed_id_404():
    resp = client.post(
        "/api/appeals/not-a-uuid/resolve",
        json={"decision": "upheld", "decision_note": "", "evaluator": "e"},
    )
    assert resp.status_code == 404


def test_resolve_appeal_rejects_invalid_decision(store):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={"decision": "maybe", "decision_note": "", "evaluator": "e"},
    )

    assert resp.status_code == 422


def test_resolve_appeal_requires_evaluator(store):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={"decision": "upheld", "decision_note": "", "evaluator": "  "},
    )

    assert resp.status_code == 422


def test_resolve_appeal_already_resolved_is_conflict(store):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)
    store.resolve_appeal(appeal["id"], "upheld", "ok", "e-1")

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={"decision": "dismissed", "decision_note": "", "evaluator": "e-2"},
    )

    assert resp.status_code == 409


def test_resolve_appeal_succeeds_even_if_mail_fails(store, monkeypatch):
    store.publish_results(True)
    sid = _scored_verdict_submission(store)
    appeal = store.add_open_appeal(sid)

    def broken(**kwargs):
        return email_service.EmailResult("failed", "provider_error", "boom")

    monkeypatch.setattr(email_service, "send_appeal_resolved", broken)

    resp = client.post(
        f"/api/appeals/{appeal['id']}/resolve",
        json={"decision": "upheld", "decision_note": "", "evaluator": "e"},
    )

    assert resp.status_code == 200
    assert resp.json()["notification"]["appeal_email"]["status"] == "failed"


# --- Results-published gate API -------------------------------------------------


def test_get_settings_reports_closed_gate(store):
    store.publish_results(False)
    resp = client.get("/api/hackathon/default/settings")
    assert resp.status_code == 200
    assert resp.json()["results_published"] is False


def test_put_results_publishes_and_republishes(store):
    resp = client.put("/api/hackathon/default/results", json={"published": True})
    assert resp.status_code == 200
    assert resp.json()["results_published"] is True

    resp = client.put("/api/hackathon/default/results", json={"published": False})
    assert resp.status_code == 200
    assert resp.json()["results_published"] is False
