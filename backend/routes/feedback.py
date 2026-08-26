"""API routes for AI-generated team feedback (v0.7.0).

POST /api/submissions/{id}/feedback runs the Groq-powered FeedbackAgent
over the four criterion scores + justifications and stores one CURRENT
feedback row per submission. GET returns whatever is stored. Both
endpoints reuse the exact ranking engine used by GET /api/rankings so
composites, ranks, and shortlist flags always agree across surfaces.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from groq import GroqError

from agents.feedback import generate_feedback
from agents.scoring.base import CRITERIA_NAMES
from backend.routes.ranking import load_leaderboard
from backend.services import email as email_service
from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/submissions/{submission_id}/feedback")
async def generate_submission_feedback(
    submission_id: str,
    hackathon_id: str = "default",
    top_n: int = Query(default=5, gt=0),
) -> dict:
    """Generate and store written feedback for a scored submission.

    ``top_n`` mirrors GET /api/rankings' shortlist semantics — the team's
    shortlisted flag (and thus the feedback tone) follows the same cutoff.
    """
    # --- The submission must exist.
    try:
        submission = supabase.get_submission(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not submission:
        raise HTTPException(
            status_code=404,
            detail=f"Submission {submission_id} not found.",
        )

    # --- It must be fully scored (the ranking engine excludes partial
    #     sets, so a missing leaderboard entry means unscored/partial).
    try:
        board = load_leaderboard(hackathon_id, top_n=top_n)
        score_rows = supabase.get_scores(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    entry = next(
        (r for r in board["ranked"] if r["submission_id"] == submission_id),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Submission {submission_id} has no complete score set. "
                "Trigger scoring first via POST /api/submissions/{id}/score."
            ),
        )

    by_criterion = {row["criterion"]: row for row in score_rows}
    ordered_scores = [by_criterion[c] for c in CRITERIA_NAMES]

    # --- Generate the feedback (Groq-powered).
    try:
        result = await generate_feedback(
            submission_id=submission_id,
            team_name=entry["team_name"],
            scores=ordered_scores,
            composite_score=entry["composite_score"],
            shortlisted=entry["shortlisted"],
            rank=entry["rank"],
            total_scored=board["scored_count"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GroqError as exc:
        raise HTTPException(status_code=503, detail=f"Feedback failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # --- Store it (one current row per submission).
    try:
        supabase.upsert_feedback(
            submission_id,
            strengths=result.strengths,
            weaknesses=result.weaknesses,
            suggestion=result.suggestion,
            verdict=result.verdict,
            agent_version=result.agent_version,
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = {
        "submission_id": submission_id,
        "agent_version": result.agent_version,
        "rubric_source": board["rubric_source"],
        "ranking_context": {
            "hackathon_id": hackathon_id,
            "composite_score": entry["composite_score"],
            "rank": entry["rank"],
            "scored_count": board["scored_count"],
            "shortlisted": entry["shortlisted"],
            "tied_on_composite": entry["tied_on_composite"],
        },
        "feedback": {
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "suggestion": result.suggestion,
            "verdict": result.verdict,
        },
    }

    # --- Results email (v1.2.0): every successful generation produces the
    #     team's current official result, so regeneration re-notifies.
    #     Degrades gracefully like the confirmation path — never 500s.
    notification = await asyncio.to_thread(
        email_service.send_results_notification,
        team_name=entry["team_name"],
        team_email=(submission.get("team_email") or ""),
        submission_id=submission_id,
        composite_score=entry["composite_score"],
        rank=entry["rank"],
        scored_count=board["scored_count"],
        shortlisted=bool(entry["shortlisted"]),
        scores=[
            {
                "criterion": score_row["criterion"],
                "score": score_row["score"],
                "justification": score_row["justification"],
            }
            for score_row in ordered_scores
        ],
        feedback={
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "suggestion": result.suggestion,
            "verdict": result.verdict,
        },
    )
    if notification.status != "sent":
        logger.warning(
            "Results email %s (%s)",
            notification.status,
            notification.detail or notification.reason,
        )
    response["notification"] = {
        "results_email": {
            "status": notification.status,
            "reason": notification.reason,
        }
    }

    return response


@router.get("/submissions/{submission_id}/feedback")
async def get_submission_feedback(submission_id: str) -> dict:
    """Return the stored feedback for a submission (or null)."""
    try:
        feedback = supabase.get_feedback(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"submission_id": submission_id, "feedback": feedback}
