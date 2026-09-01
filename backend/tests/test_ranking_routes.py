"""Tests for the v0.6.0 ranking + rubric API routes.

The Supabase service layer is mocked with a small in-memory store so
tests prove the routes are correctly WIRED (params, validation, fallbacks,
freshness) without touching the network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import supabase

client = TestClient(app)

CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]


# --- Fake store ----------------------------------------------------------------


class FakeStore:
    """In-memory stand-in for submissions/scores/rubric_config tables."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.rubrics: dict[str, dict[str, float]] = {}
        self.configured = True

    # Service-layer surface used by the ranking routes.
    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self, hackathon_id: str = "default") -> list[dict]:
        return [dict(r) for r in self.scores]

    def get_rubric(self, hackathon_id: str) -> dict[str, float] | None:
        if not self.configured:
            raise supabase.SupabaseNotConfiguredError("not configured")
        return {c: w for c, w in self.rubrics.get(hackathon_id, {}).items()} or None

    def upsert_rubric(
        self, hackathon_id: str, weights: dict[str, float]
    ) -> dict[str, float]:
        self.rubrics.setdefault(hackathon_id, {}).update(weights)
        return {c: w for c, w in self.rubrics[hackathon_id].items()}

    # Test-data helpers.
    def add_submission(self, sid: str, team: str) -> None:
        self.submissions.append({"id": sid, "team_name": team})

    def add_scores(self, sid: str, **by_criterion) -> None:
        full = {
            "problem_fit": 5,
            "technical_depth": 5,
            "feasibility": 5,
            "innovation": 5,
        }
        full.update(by_criterion)
        for criterion in CRITERIA:
            self.scores.append(
                {"submission_id": sid, "criterion": criterion, "score": full[criterion]}
            )


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(supabase, "list_submissions", fake.list_submissions)
    monkeypatch.setattr(supabase, "get_all_scores", fake.get_all_scores)
    monkeypatch.setattr(supabase, "get_rubric", fake.get_rubric)
    monkeypatch.setattr(supabase, "upsert_rubric", fake.upsert_rubric)
    return fake


# --- GET /api/rankings ----------------------------------------------------------


def test_rankings_falls_back_to_equal_weights_when_unconfigured(store):
    resp = client.get("/api/rankings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rubric_source"] == "fallback"
    assert body["rubric"] == {c: 0.25 for c in CRITERIA}
    assert body["ranked"] == []
    assert body["scored_count"] == 0


def test_rankings_happy_path_orders_and_reports_counts(store):
    store.add_submission("id-a", "Alpha")
    store.add_submission("id-b", "Bravo")
    store.add_submission("id-none", "Charlie")
    store.add_scores(
        "id-a", problem_fit=8, technical_depth=7, feasibility=6, innovation=9
    )
    store.add_scores(
        "id-b", problem_fit=9, technical_depth=9, feasibility=9, innovation=5
    )

    resp = client.get("/api/rankings")
    body = resp.json()

    assert resp.status_code == 200
    order = [r["submission_id"] for r in body["ranked"]]
    assert order == ["id-b", "id-a"]  # composites 8.0 vs 7.5
    top = body["ranked"][0]
    assert top["team_name"] == "Bravo"
    assert top["composite_score"] == 8.0
    assert top["criterion_scores"]["problem_fit"] == 9
    assert [r["rank"] for r in body["ranked"]] == [1, 2]
    assert body["scored_count"] == 2
    assert body["unscored_count"] == 1
    assert body["partial_count"] == 0
    assert body["shortlist"] == {"top_n": None, "min_score": None}
    assert all(not r["shortlisted"] for r in body["ranked"])


def test_rankings_reflect_newly_scored_submission_immediately(store):
    """Roadmap DoD: the ranked list updates when a new submission scores."""
    store.add_submission("id-first", "First")
    store.add_scores(
        "id-first", innovation=10, problem_fit=4, technical_depth=4, feasibility=4
    )

    before = client.get("/api/rankings").json()
    assert [r["submission_id"] for r in before["ranked"]] == ["id-first"]

    # A stronger submission arrives and gets scored.
    store.add_submission("id-second", "Second")
    store.add_scores(
        "id-second", problem_fit=9, technical_depth=9, feasibility=9, innovation=9
    )

    after = client.get("/api/rankings").json()
    order = [r["submission_id"] for r in after["ranked"]]
    assert order == ["id-second", "id-first"]
    assert after["ranked"][0]["composite_score"] == 9.0


def test_rankings_configured_rubric_changes_order_and_source(store):
    store.add_submission("id-a", "Alpha")
    store.add_submission("id-b", "Bravo")
    store.add_scores(
        "id-a", problem_fit=6, technical_depth=6, feasibility=6, innovation=10
    )
    store.add_scores(
        "id-b", problem_fit=9, technical_depth=9, feasibility=9, innovation=2
    )

    fallback_first = client.get("/api/rankings").json()
    assert fallback_first["rubric_source"] == "fallback"
    assert fallback_first["ranked"][0]["submission_id"] == "id-b"

    put = client.put(
        "/api/rubrics/default",
        json={
            "weights": {
                "problem_fit": 15,
                "technical_depth": 20,
                "feasibility": 25,
                "innovation": 40,
            }
        },
    )
    assert put.status_code == 200
    assert abs(put.json()["rubric"]["innovation"] - 0.40) < 1e-9

    after = client.get("/api/rankings").json()
    assert after["rubric_source"] == "configured"
    assert after["ranked"][0]["submission_id"] == "id-a"  # composite 7.7 vs 7.4


def test_top_n_marks_exactly_n(store):
    """Roadmap DoD: cutoff at top 5 -> exactly 5 marked shortlisted."""
    for i in range(8):
        sid = f"id-{i}"
        store.add_submission(sid, f"Team{i}")
        store.add_scores(
            sid,
            problem_fit=4 + i,
            technical_depth=4 + i,
            feasibility=4 + i,
            innovation=4 + i,
        )

    body = client.get("/api/rankings", params={"top_n": 5}).json()
    flagged = [r["submission_id"] for r in body["ranked"] if r["shortlisted"]]
    assert len(flagged) == 5
    assert [r["rank"] for r in body["ranked"] if r["shortlisted"]] == [1, 2, 3, 4, 5]
    assert body["shortlist"] == {"top_n": 5, "min_score": None}


def test_min_score_cutoff_inclusive_through_route(store):
    store.add_submission("id-high", "High")
    store.add_submission("id-edge", "Edge")
    store.add_submission("id-low", "Low")
    store.add_scores(
        "id-high", problem_fit=9, technical_depth=9, feasibility=9, innovation=9
    )
    store.add_scores(
        "id-edge", problem_fit=6, technical_depth=6, feasibility=6, innovation=6
    )
    store.add_scores(
        "id-low", problem_fit=2, technical_depth=2, feasibility=2, innovation=2
    )

    body = client.get("/api/rankings", params={"min_score": 6.0}).json()
    shortlisted = {r["submission_id"] for r in body["ranked"] if r["shortlisted"]}
    assert shortlisted == {"id-high", "id-edge"}  # exactly-on-threshold included


def test_exact_tie_flagged_and_deterministically_ordered(store):
    """Roadmap DoD: a tie fires the rule instead of arbitrary ordering."""
    store.add_submission("id-x", "XRay")
    store.add_submission("id-w", "Whiskey")
    store.add_scores(
        "id-x", problem_fit=6, technical_depth=6, feasibility=6, innovation=6
    )
    store.add_scores(
        "id-w", problem_fit=6, technical_depth=6, feasibility=6, innovation=6
    )

    orders = set()
    for _ in range(3):
        body = client.get("/api/rankings").json()
        rows = body["ranked"]
        assert all(r["tied_on_composite"] for r in rows)
        assert {r["composite_score"] for r in rows} == {6.0}
        orders.add(tuple(r["submission_id"] for r in rows))
    assert len(orders) == 1
    assert next(iter(orders)) == ("id-w", "id-x")  # id ASC tie-break


# --- Validation & error paths ---------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"top_n": 0},
        {"top_n": -3},
        {"min_score": -0.1},
        {"min_score": 10.5},
    ],
)
def test_rankings_rejects_bad_cutoff_values(store, params):
    resp = client.get("/api/rankings", params=params)
    assert resp.status_code == 422


def test_rankings_rejects_both_cutoffs(store):
    resp = client.get("/api/rankings", params={"top_n": 3, "min_score": 7.0})
    assert resp.status_code == 422
    assert "not both" in resp.json()["detail"]


@pytest.mark.parametrize(
    "weights",
    [
        {"problem_fit": 0.25, "technical_depth": 0.25, "feasibility": 0.25},  # missing
        {**{c: 0.25 for c in CRITERIA}, "style_points": 0.0},  # unknown criterion
        {c: 20 for c in CRITERIA[:-1]} | {"innovation": 50},  # sum = 110
        {c: -0.05 for c in CRITERIA[:-1]} | {"innovation": 1.2},  # negative
    ],
)
def test_put_rubric_rejects_invalid_weights(store, weights):
    resp = client.put("/api/rubrics/default", json={"weights": weights})
    assert resp.status_code == 422


def test_put_rubric_rejects_non_numeric_weight(store):
    weights = {c: 0.25 for c in CRITERIA}
    weights["problem_fit"] = "quarter"
    resp = client.put("/api/rubrics/default", json={"weights": weights})
    assert resp.status_code == 422


def test_put_then_get_rubric_round_trip(store):
    put = client.put(
        "/api/rubrics/sih-2026",
        json={
            "weights": {
                "problem_fit": 0.30,
                "technical_depth": 0.30,
                "feasibility": 0.20,
                "innovation": 0.20,
            }
        },
    )
    assert put.status_code == 200

    got = client.get("/api/rubrics/sih-2026")
    assert got.status_code == 200
    rubric = got.json()["rubric"]
    assert rubric is not None
    assert abs(sum(rubric.values()) - 1.0) < 1e-9


def test_get_rubric_returns_null_when_unconfigured(store):
    resp = client.get("/api/rubrics/never-configured")
    assert resp.status_code == 200
    assert resp.json()["rubric"] is None


def test_rankings_supabase_not_configured_returns_503(store, monkeypatch):
    def broken(*args, **kwargs):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "get_rubric", broken)
    resp = client.get("/api/rankings")
    assert resp.status_code == 503
