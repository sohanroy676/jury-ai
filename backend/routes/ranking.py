"""API routes for the weighted leaderboard and rubric config (v0.6.0).

Composite scores are computed ON THE FLY from live ``scores`` rows and
the current rubric weights — never persisted — so rankings always
reflect the latest weights and newly scored submissions immediately.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agents.ranking.engine import (
    CRITERIA_NAMES,
    DEFAULT_WEIGHTS,
    WeightValidationError,
    build_ranking,
    validate_weights,
)
from backend.services import supabase

router = APIRouter(prefix="/api", tags=["ranking"])

# Ranking scans the whole scored pool; hackathon-scale pools are small.
MAX_RANKING_SUBMISSIONS = 10000


class RubricUpdate(BaseModel):
    """PUT /api/rubrics/{hackathon_id} request body."""

    weights: dict[str, float]


def load_leaderboard(
    hackathon_id: str = "default",
    top_n: int | None = None,
    min_score: float | None = None,
) -> dict:
    """Fetch rubric + submissions + scores and build the ranked board.

    Shared by GET /api/rankings and the v0.7.0 feedback/export routes so
    every surface sees identical composites, ordering, and shortlist
    semantics. Raises ``SupabaseNotConfiguredError`` when Supabase is
    not configured (callers map that to HTTP 503).
    """
    configured = supabase.get_rubric(hackathon_id)
    raw_submissions = supabase.list_submissions(limit=MAX_RANKING_SUBMISSIONS)
    submissions = [
        s for s in raw_submissions
        if s.get("hackathon_id", "default") == hackathon_id or not s.get("hackathon_id")
    ]
    try:
        score_rows = supabase.get_all_scores(hackathon_id)
    except TypeError:
        score_rows = supabase.get_all_scores()

    # A partially-configured rubric (e.g. hand-edited rows) falls back to
    # equal weights rather than producing misleading composites.
    if configured and all(c in configured for c in CRITERIA_NAMES):
        weights, rubric_source = configured, "configured"
    else:
        weights, rubric_source = dict(DEFAULT_WEIGHTS), "fallback"

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in score_rows:
        grouped[row["submission_id"]].append(row)

    result = build_ranking(
        submissions,
        grouped,
        weights,
        top_n=top_n,
        min_score=min_score,
    )
    return {
        "rubric": weights,
        "rubric_source": rubric_source,
        "shortlist": {"top_n": top_n, "min_score": min_score},
        **result,
    }


@router.get("/rankings")
async def get_rankings(
    hackathon_id: str = "default",
    top_n: int | None = Query(default=None, gt=0),
    min_score: float | None = Query(default=None, ge=0, le=10),
) -> dict:
    """Return submissions ranked by weighted composite score.

    Shortlisting is configured via ``top_n`` (first N after sorting) or
    ``min_score`` (inclusive threshold) — never both.
    """
    if top_n is not None and min_score is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either top_n or min_score, not both.",
        )

    try:
        body = load_leaderboard(hackathon_id, top_n=top_n, min_score=min_score)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"hackathon_id": hackathon_id, **body}


@router.get("/rubrics/{hackathon_id}")
async def get_rubric(hackathon_id: str) -> dict:
    """Return the configured rubric for a hackathon (or null)."""
    try:
        rubric = supabase.get_rubric(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"hackathon_id": hackathon_id, "rubric": rubric}


@router.put("/rubrics/{hackathon_id}")
async def put_rubric(hackathon_id: str, update: RubricUpdate) -> dict:
    """Configure criterion weights for a hackathon.

    Weights must cover exactly the four criteria and sum to ~1.0 (or
    ~100 as percentages, which are normalized to fractions).
    """
    try:
        normalized = validate_weights(update.weights)
    except WeightValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        stored = supabase.upsert_rubric(hackathon_id, normalized)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"hackathon_id": hackathon_id, "rubric": stored}
