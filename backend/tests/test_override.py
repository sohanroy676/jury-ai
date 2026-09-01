"""Tests for the evaluator score override endpoint (v2.1.0).

Adversarial focus: validation gaps, wrong-method access, unscored
submissions, Supabase outages, and rank-recomputation correctness.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import override as override_route
from backend.services import supabase

client = TestClient(app)

SUBMISSION_ID = "00000000-0000-0000-0000-000000000001"
URL = f"/api/submissions/{SUBMISSION_ID}/scores/problem_fit"

RANK_CONTEXT = {
    "rank": 1,
    "submission_id": SUBMISSION_ID,
    "team_name": "Moonshot",
    "composite_score": 8.5,
    "criterion_scores": {
        "problem_fit": 10,
        "technical_depth": 8,
        "feasibility": 8,
        "innovation": 9,
    },
    "shortlisted": True,
    "tied_on_composite": False,
}

UPDATED_ROW = {
    "id": "score-1",
    "submission_id": SUBMISSION_ID,
    "criterion": "problem_fit",
    "score": 10,
    "original_score": 6,
    "overridden_by": "alice@example.com",
    "override_reason": "Prototype demo proved the fit.",
}


@pytest.fixture(autouse=True)
def _mock_happy_path(monkeypatch):
    """Default mocks: submission exists, override succeeds, board loads."""
    monkeypatch.setattr(
        supabase, "get_submission", lambda sid: {"id": sid, "team_name": "Moonshot"}
    )
    monkeypatch.setattr(
        supabase,
        "override_score",
        lambda sid, criterion, score, evaluator, reason: dict(UPDATED_ROW),
    )
    monkeypatch.setattr(
        override_route,
        "load_leaderboard",
        lambda *a, **kw: {"ranked": [dict(RANK_CONTEXT)]},
    )


def _override_body(**overrides):
    body = {
        "score": 10,
        "reason": "Prototype demo proved the fit.",
        "evaluator": "alice@example.com",
    }
    body.update(overrides)
    return body


def test_override_success_returns_rank_context():
    resp = client.put(URL, json=_override_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_score"]["score"] == 10
    assert body["updated_score"]["original_score"] == 6
    assert body["rank_context"]["rank"] == 1
    assert body["rank_context"]["criterion_scores"]["problem_fit"] == 10


def test_override_reason_is_required():
    resp = client.put(URL, json=_override_body(reason="   "))
    assert resp.status_code == 422


def test_override_reason_too_short_rejected():
    resp = client.put(URL, json=_override_body(reason="too short"))
    assert resp.status_code == 422


def test_override_score_below_range_rejected():
    resp = client.put(URL, json=_override_body(score=0))
    assert resp.status_code == 422


def test_override_score_above_range_rejected():
    resp = client.put(URL, json=_override_body(score=11))
    assert resp.status_code == 422


def test_override_non_integer_score_rejected():
    resp = client.put(URL, json=_override_body(score=7.5))
    assert resp.status_code == 422


def test_override_evaluator_required():
    resp = client.put(URL, json=_override_body(evaluator="   "))
    assert resp.status_code == 422


def test_override_unknown_criterion_rejected():
    resp = client.put(
        f"/api/submissions/{SUBMISSION_ID}/scores/creativity",
        json=_override_body(),
    )
    assert resp.status_code == 422
    assert "unknown criterion" in resp.json()["detail"].lower()


def test_override_unknown_submission_404(monkeypatch):
    monkeypatch.setattr(supabase, "get_submission", lambda sid: None)
    resp = client.put(
        f"/api/submissions/{uuid.uuid4()}/scores/problem_fit", json=_override_body()
    )
    assert resp.status_code == 404


def test_override_unscored_criterion_conflict_409(monkeypatch):
    """Submission exists but the criterion was never scored -> 409."""
    monkeypatch.setattr(supabase, "override_score", lambda *a, **kw: None)
    resp = client.put(URL, json=_override_body())
    assert resp.status_code == 409
    assert "no 'problem_fit' score" in resp.json()["detail"]


def test_override_supabase_down_503(monkeypatch):
    def _boom(sid):
        raise supabase.SupabaseNotConfiguredError("credentials missing")

    monkeypatch.setattr(supabase, "get_submission", _boom)
    resp = client.put(URL, json=_override_body())
    assert resp.status_code == 503


def test_override_rank_recomputed_from_live_rows(monkeypatch):
    """End-to-end: the rebuilt board provably reflects the override.

    Wires the REAL load_leaderboard to mocked Supabase reads so the
    composite/rank in the response comes from the ranking engine itself.
    """
    scores = [
        {"submission_id": SUBMISSION_ID, "criterion": c, "score": s}
        for c, s in [
            ("problem_fit", 10),
            ("technical_depth", 8),
            ("feasibility", 8),
            ("innovation", 9),
        ]
    ] + [
        {"submission_id": "id-2", "criterion": c, "score": 5}
        for c in ("problem_fit", "technical_depth", "feasibility", "innovation")
    ]
    monkeypatch.setattr(
        supabase,
        "get_rubric",
        lambda hid: {
            c: 0.25
            for c in ("problem_fit", "technical_depth", "feasibility", "innovation")
        },
    )
    monkeypatch.setattr(
        supabase,
        "list_submissions",
        lambda limit=100, include_superseded=False: [
            {"id": SUBMISSION_ID, "team_name": "Moonshot"},
            {"id": "id-2", "team_name": "Others"},
        ],
    )
    monkeypatch.setattr(supabase, "get_all_scores", lambda: scores)
    from backend.routes.ranking import load_leaderboard as real_loader

    monkeypatch.setattr(override_route, "load_leaderboard", real_loader)

    resp = client.put(URL, json=_override_body())
    assert resp.status_code == 200
    body = resp.json()
    # (10 + 8 + 8 + 9) / 4 = 8.75 — the raised score drives the composite.
    assert body["rank_context"]["composite_score"] == 8.75
    assert body["rank_context"]["rank"] == 1
    assert body["rank_context"]["criterion_scores"]["problem_fit"] == 10


def test_override_submission_not_ranked_yet_returns_empty_context(monkeypatch):
    """A submission with an incomplete score set cannot be ranked."""
    monkeypatch.setattr(
        override_route, "load_leaderboard", lambda *a, **kw: {"ranked": []}
    )
    resp = client.put(URL, json=_override_body())
    assert resp.status_code == 200
    assert resp.json()["rank_context"] == {}
