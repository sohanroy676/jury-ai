"""API routes for evaluator score overrides (v2.1.0).

A human judge can adjust any AI-assigned criterion score. The override
is written to the live ``scores`` row (ranking reads live rows, so the
next leaderboard build reflects it immediately), requires a reason, and
the endpoint returns the recomputed composite + rank so the UI can show
the consequence of the change without a second round-trip.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from agents.ranking.engine import CRITERIA_NAMES
from backend.routes.ranking import load_leaderboard
from backend.services import supabase

router = APIRouter(prefix="/api", tags=["override"])

MIN_REASON_LENGTH = 10
HACKATHON_ID = "default"


class ScoreOverride(BaseModel):
    """PUT /api/submissions/{id}/scores/{criterion} request body."""

    score: int = Field(..., description="New score, integer 1-10.")
    reason: str = Field(..., description="Required human justification (min 10 chars).")
    evaluator: str = Field(..., description="Evaluator name or email.")

    @field_validator("score")
    @classmethod
    def _check_score_range(cls, value: int) -> int:
        if not 1 <= value <= 10:
            raise ValueError("score must be between 1 and 10.")
        return value

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        if len(value.strip()) < MIN_REASON_LENGTH:
            raise ValueError(
                f"a reason of at least {MIN_REASON_LENGTH} characters is required."
            )
        return value.strip()

    @field_validator("evaluator")
    @classmethod
    def _check_evaluator(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluator identity is required.")
        return value.strip()


def _load_rank_context(submission_id: str) -> dict:
    """Rebuild the leaderboard and return this submission's entry.

    Raises 503 when Supabase is unavailable; returns an empty dict when
    the submission has no complete score set (cannot be ranked yet).
    """
    board = load_leaderboard(HACKATHON_ID)
    for row in board.get("ranked", []):
        if row["submission_id"] == submission_id:
            return row
    return {}


@router.put("/submissions/{submission_id}/scores/{criterion}")
async def override_submission_score(
    submission_id: str, criterion: str, override: ScoreOverride
) -> dict:
    """Override one criterion score for a submission.

    Validation order: criterion name, submission existence, scored
    state — each with a distinct status code (422 / 404 / 409) so the UI
    can show a precise message. On success the leaderboard is recomputed
    and the submission's new composite + rank ride along in the response.
    """
    if criterion not in CRITERIA_NAMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown criterion '{criterion}'. "
                f"Allowed: {', '.join(CRITERIA_NAMES)}."
            ),
        )

    try:
        UUID(submission_id)
        submission = supabase.get_submission(submission_id)
        if submission is None:
            raise HTTPException(status_code=404, detail="Submission not found.")
        updated = supabase.override_score(
            submission_id,
            criterion,
            override.score,
            evaluator=override.evaluator,
            reason=override.reason,
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if updated is None:
        # Submission exists but this criterion was never scored.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Submission has no '{criterion}' score to override. Score it first."
            ),
        )

    try:
        rank_context = _load_rank_context(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "submission_id": submission_id,
        "criterion": criterion,
        "updated_score": updated,
        "rank_context": rank_context,
    }
