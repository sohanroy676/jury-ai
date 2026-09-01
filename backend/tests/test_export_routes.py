"""Tests for the v0.7.0 export API routes (CSV + per-team PDF).

The Supabase service layer is mocked with an in-memory store; CSV output
is asserted as parsed rows, PDF output by magic bytes/headers plus a
direct unit test of the ReportLab renderer.
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import pdf, supabase

client = TestClient(app)

CRITERIA = ["problem_fit", "technical_depth", "feasibility", "innovation"]


class FakeStore:
    """In-memory stand-in for submissions/scores/rubric/feedback tables."""

    def __init__(self):
        self.submissions: list[dict] = []
        self.scores: list[dict] = []
        self.feedback: dict[str, dict] = {}

    def get_submission(self, submission_id: str) -> dict | None:
        return next((s for s in self.submissions if s["id"] == submission_id), None)

    def list_submissions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in reversed(self.submissions[-limit:])]

    def get_all_scores(self, hackathon_id: str = "default") -> list[dict]:
        return [dict(r) for r in self.scores]

    def get_scores(self, submission_id: str) -> list[dict]:
        return [dict(r) for r in self.scores if r["submission_id"] == submission_id]

    def get_rubric(self, hackathon_id: str) -> dict[str, float] | None:
        return None  # equal-weight fallback path

    def get_feedback(self, submission_id: str) -> dict | None:
        row = self.feedback.get(submission_id)
        return dict(row) if row else None

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
                {
                    "submission_id": sid,
                    "criterion": criterion,
                    "score": full[criterion],
                    "justification": f"{criterion} evidence",
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
        "get_feedback",
    ):
        monkeypatch.setattr(supabase, name, getattr(fake, name))
    return fake


def _parse_csv(resp) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resp.text)))


# --- CSV --------------------------------------------------------------------------


def test_csv_happy_path_matches_leaderboard(store):
    store.add_submission("id-a", "Alpha")
    store.add_submission("id-b", "Bravo")
    store.add_submission("id-x", "XRay")
    store.add_scores("id-b", problem_fit=9)
    store.add_scores("id-a", problem_fit=7)

    resp = client.get("/api/export/csv?top_n=1")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "rankings_default.csv" in resp.headers["content-disposition"]

    rows = _parse_csv(resp)
    assert rows[0] == ["rank", "team_name", *CRITERIA, "composite_score", "shortlisted"]
    # Bravo first (higher pf), Alpha second; unscored XRay excluded.
    assert [r[1] for r in rows[1:]] == ["Bravo", "Alpha"]
    assert rows[1][-1] == "yes"
    assert rows[2][-1] == "no"


def test_csv_composite_column_uses_weighted_math(store):
    store.add_submission("id-a", "Alpha")
    store.add_scores(
        "id-a", problem_fit=8, technical_depth=6, feasibility=4, innovation=10
    )

    resp = client.get("/api/export/csv")
    rows = _parse_csv(resp)
    expected = round(8 * 0.25 + 6 * 0.25 + 4 * 0.25 + 10 * 0.25, 4)
    assert float(rows[1][6]) == expected


def test_csv_min_score_cutoff_flags_inclusively(store):
    store.add_submission("id-hi", "High")
    store.add_submission("id-edge", "Edge")
    store.add_submission("id-lo", "Low")
    store.add_scores("id-hi", problem_fit=9)  # composite 6.50
    store.add_scores("id-edge")  # composite 5.00 - exactly ON the threshold
    store.add_scores("id-lo", problem_fit=2)  # composite 4.25

    resp = client.get("/api/export/csv", params={"min_score": 5.0})
    rows = {r[1]: r[-1] for r in _parse_csv(resp)[1:]}
    assert rows["High"] == "yes"
    assert rows["Edge"] == "yes"
    assert rows["Low"] == "no"


def test_csv_empty_leaderboard_returns_header_only(store):
    resp = client.get("/api/export/csv")
    assert resp.status_code == 200
    rows = _parse_csv(resp)
    assert len(rows) == 1


@pytest.mark.parametrize(
    "hackathon_id,expected_stem",
    [
        ("SIH 2026!", "SIH_2026"),
        ("../../etc/passwd", "etc_passwd"),
        ("***", "default"),
    ],
)
def test_csv_filename_is_sanitized(store, hackathon_id, expected_stem):
    resp = client.get("/api/export/csv", params={"hackathon_id": hackathon_id})
    header = resp.headers["content-disposition"]
    assert f"rankings_{expected_stem}.csv" in header
    # No path separators or quotes survive.
    assert "/" not in header.split("filename=")[1]


def test_csv_rejects_both_cutoffs(store):
    resp = client.get("/api/export/csv", params={"top_n": 3, "min_score": 5.0})
    assert resp.status_code == 422
    assert "not both" in resp.json()["detail"]


def test_csv_without_cutoff_shortlists_nothing(store):
    """With no top_n/min_score the engine deliberately shortlists NOTHING
    (shortlisted defaults False). This is the contract behind the v1.1
    'everyone shows no' bug: the UI applied top_n=3 but the export URL
    omitted it, so the download reflected the no-cutoff board. Keeping
    the regression explicit documents WHY the frontend must forward the
    cutoff."""
    store.add_submission("id-a", "Alpha")
    store.add_submission("id-b", "Bravo")
    store.add_scores("id-a", problem_fit=7)
    store.add_scores("id-b", problem_fit=9)

    resp = client.get("/api/export/csv")

    rows = _parse_csv(resp)[1:]
    assert rows, "expected two scored rows"
    assert all(row[-1] == "no" for row in rows)


def test_csv_supabase_down_503(store, monkeypatch):
    def broken(*args, **kwargs):
        raise supabase.SupabaseNotConfiguredError("not configured")

    monkeypatch.setattr(supabase, "list_submissions", broken)
    resp = client.get("/api/export/csv")
    assert resp.status_code == 503


# --- PDF (route) --------------------------------------------------------------------


def test_pdf_route_happy_path(store):
    store.add_submission("id-a", "Alpha Team")
    store.add_scores("id-a", problem_fit=8)
    store.feedback["id-a"] = {
        "submission_id": "id-a",
        "strengths": ["Strong problem evidence"],
        "weaknesses": ["Thin feasibility section"],
        "suggestion": "Add a deployment plan.",
        "verdict": "shortlist",
    }

    resp = client.get("/api/export/submissions/id-a/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "evaluation_Alpha_Team.pdf" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 1000


def test_pdf_route_works_without_feedback_yet(store):
    store.add_submission("id-a", "Alpha")
    store.add_scores("id-a")

    resp = client.get("/api/export/submissions/id-a/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_pdf_route_unknown_submission_404(store):
    resp = client.get("/api/export/submissions/ghost/pdf")
    assert resp.status_code == 404


def test_pdf_route_unscored_submission_409(store):
    store.add_submission("id-x", "XRay")
    resp = client.get("/api/export/submissions/id-x/pdf")
    assert resp.status_code == 409


def test_pdf_route_sanitizes_team_name_in_filename(store):
    store.add_submission("id-a", 'A/B:C"D')
    store.add_scores("id-a")

    resp = client.get("/api/export/submissions/id-a/pdf")
    header = resp.headers["content-disposition"]
    assert "/" not in header.split("filename=")[1]
    assert ".pdf" in header


# --- PDF (renderer unit tests) --------------------------------------------------------


_SCORES = [
    {"criterion": c, "score": i + 6, "justification": f"Notes about {c} & <evidence>"}
    for i, c in enumerate(CRITERIA)
]


def _render(**overrides):
    kwargs = {
        "team_name": "QuantumQuokka",
        "hackathon_id": "default",
        "rank": 2,
        "total_scored": 8,
        "composite_score": 7.25,
        "shortlisted": True,
        "tied_on_composite": False,
        "scores": _SCORES,
        "feedback": {
            "strengths": ["Cited survey", "Novel LoRa sync - fresh angle"],
            "weaknesses": ["No architecture diagram"],
            "suggestion": "Add a load-test report.",
            "verdict": "shortlist",
        },
        "agent_version": "v0.7.0-test",
    }
    kwargs.update(overrides)
    return pdf.render_submission_report(**kwargs)


def test_render_produces_valid_pdf_bytes():
    out = _render()
    assert out.startswith(b"%PDF")
    assert b"%%EOF" in out[-2048:]


def test_render_without_feedback_still_builds():
    out = _render(feedback=None)
    assert out.startswith(b"%PDF")


def test_render_escapes_markup_characters():
    # '<evidence>' in justifications must be escaped, not parsed as tags.
    out = _render()  # would raise or corrupt on unescaped markup
    assert isinstance(out, bytes)


def test_render_handles_long_justifications_and_empty_feedback_lists():
    long_scores = [
        {"criterion": c, "score": 5, "justification": "word " * 400} for c in CRITERIA
    ]
    out = _render(
        scores=long_scores,
        feedback={"strengths": [], "weaknesses": [], "suggestion": "", "verdict": "x"},
    )
    assert out.startswith(b"%PDF")


def test_render_handles_none_rank():
    out = _render(rank=None, total_scored=None)
    assert out.startswith(b"%PDF")
