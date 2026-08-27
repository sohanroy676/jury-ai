"""API routes for the v1.3.0 appeal flow.

Teams contest a published result by filing an appeal; appeals land in a
human-evaluator queue with the original AI scoring + feedback attached;
the evaluator logs a final decision (upheld | dismissed) against the
submission. The appeal form is gated on the results having been published
via ``hackathon_settings.results_published_at``.

Follows every house convention: narrow sealed service seam (``supabase``),
``SupabaseNotConfiguredError`` -> 503, a per-failure ``HTTPException``,
UUID-validated ids -> 404, reuses ``load_leaderboard`` so composites/ranks
never disagree across surfaces, and appeal emails degrade gracefully
(``EmailResult``, never raise).
"""

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.routes.ranking import load_leaderboard
from backend.services import email as email_service
from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["appeals"])

# Upper bound on an appeal's written reason (kept generous but bounded).
MAX_REASON_CHARS = 2000


class AppealCreate(BaseModel):
    """POST /api/appeals request body."""

    submission_id: str
    reason: str
    contact_email: str | None = None
    hackathon_id: str = "default"


class AppealResolve(BaseModel):
    """POST /api/appeals/{id}/resolve request body."""

    decision: Literal["upheld", "dismissed"]
    decision_note: str = ""
    evaluator: str


class ResultsPublish(BaseModel):
    """PUT /api/hackathon/{hackathon_id}/results request body."""

    published: bool


def _validate_uuid(value: str) -> None:
    """Raise a 404 when the id is not a well-formed UUID (never 500)."""
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Appeal not found.") from exc


def _results_published(hackathon_id: str) -> bool:
    """True when the hackathon has results published (the appeal gate)."""
    settings_row = supabase.get_hackathon_settings(hackathon_id)
    return bool(settings_row and settings_row.get("results_published_at"))


def _appeal_response(
    appeal: dict,
    *,
    board: dict,
    submission: dict,
    feedback: dict,
    scores: list[dict],
) -> dict:
    """Compose an appeal with the original AI context attached.

    The evaluator queue needs to see the same composites/ranks/shortlist
    that produced the result, and the team-facing view the verdict that is
    being contested. ``scores`` carries the per-criterion justifications
    from the ``scores`` table (the ranked entry only has the values).
    """
    entry = next(
        (r for r in board["ranked"] if r["submission_id"] == appeal["submission_id"]),
        None,
    )
    return {
        "id": appeal["id"],
        "submission_id": appeal["submission_id"],
        "hackathon_id": appeal.get("hackathon_id", "default"),
        "reason": appeal.get("reason", ""),
        "status": appeal.get("status", "open"),
        "decision": appeal.get("decision"),
        "decision_note": appeal.get("decision_note") or "",
        "evaluator": appeal.get("evaluator") or "",
        "created_at": appeal.get("created_at", ""),
        "decided_at": appeal.get("decided_at"),
        "context": {
            "team_name": submission.get("team_name", ""),
            "composite_score": entry["composite_score"] if entry else None,
            "rank": entry["rank"] if entry else None,
            "shortlisted": bool(entry["shortlisted"]) if entry else None,
            "scores": [
                {
                    "criterion": s.get("criterion"),
                    "score": s.get("score"),
                    "justification": s.get("justification", ""),
                }
                for s in scores
            ],
            "feedback": {
                "strengths": feedback.get("strengths", []),
                "weaknesses": feedback.get("weaknesses", []),
                "suggestion": feedback.get("suggestion", ""),
                "verdict": feedback.get("verdict"),
            }
            if feedback
            else None,
        },
    }


@router.post("/appeals", status_code=201)
async def create_appeal(body: AppealCreate) -> dict:
    """File an appeal against a scored, verdict-carrying submission.

    Rejected with 403 when results have not been published, 404 for an
    unknown/non-UUID submission, 422 for a missing/blank/oversized reason
    or an unscored submission, and 409 when the team already has an open
    appeal. The confirmation email degrades gracefully and never fails the
    filing.
    """
    # --- Gate: appeals open only after results are published.
    try:
        published = _results_published(body.hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not published:
        raise HTTPException(
            status_code=403,
            detail="Results have not been published yet; appeals are not open.",
        )

    # --- Validate the reason (bounded, meaningful).
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Appeal reason is required.")
    if len(reason) > MAX_REASON_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Appeal reason must be at most {MAX_REASON_CHARS} characters.",
        )

    # --- Validate the contact email shape when provided.
    if body.contact_email and not email_service.is_valid_email(body.contact_email):
        raise HTTPException(
            status_code=422,
            detail="Please provide a valid contact email address.",
        )

    # --- Validate the submission id and that it has a verdict to contest.
    _validate_uuid(body.submission_id)
    try:
        submission = supabase.get_submission(body.submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not submission:
        raise HTTPException(
            status_code=404, detail=f"Submission {body.submission_id} not found."
        )

    try:
        board = load_leaderboard(body.hackathon_id, top_n=1)
        feedback = supabase.get_feedback(body.submission_id)
        score_rows = supabase.get_scores(body.submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    entry = next(
        (r for r in board["ranked"] if r["submission_id"] == body.submission_id),
        None,
    )
    if entry is None or not feedback:
        raise HTTPException(
            status_code=422,
            detail=(
                "This submission has no verdict yet; appeals require a "
                "published result with written feedback."
            ),
        )

    # --- One open appeal per submission (anti-spam; DB index backs this).
    try:
        existing = supabase.get_appeal_by_submission(body.submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if existing is not None and existing.get("status") == "open":
        raise HTTPException(
            status_code=409,
            detail="This team already has an open appeal under review.",
        )

    # --- Persist the appeal.
    try:
        appeal = supabase.insert_appeal(
            body.submission_id,
            reason,
            contact_email=body.contact_email,
            hackathon_id=body.hackathon_id,
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Non-blocking confirmation email to the filing contact.
    recipient = body.contact_email or (submission.get("team_email") or "")
    notification = await asyncio.to_thread(
        email_service.send_appeal_submitted,
        team_name=submission.get("team_name", ""),
        team_email=recipient,
        submission_id=body.submission_id,
        reason=reason,
    )
    if notification.status != "sent":
        logger.warning(
            "Appeal-submitted email %s (%s)",
            notification.status,
            notification.detail or notification.reason,
        )

    response = _appeal_response(
        appeal, board=board, submission=submission, feedback=feedback, scores=score_rows
    )
    response["notification"] = {
        "appeal_email": {
            "status": notification.status,
            "reason": notification.reason,
        }
    }
    return response


@router.get("/appeals")
async def list_appeals(
    status: str | None = Query(default=None),
) -> dict:
    """Human-evaluator queue: appeals with the original AI context attached.

    ``status=open`` (default view) returns only unresolved appeals,
    ``status=resolved`` the decided ones, and omitting it returns all.
    """
    if status not in (None, "open", "resolved"):
        raise HTTPException(
            status_code=422, detail="status must be one of: open, resolved."
        )

    try:
        appeals = supabase.list_appeals(status=status)
        board = load_leaderboard("default", top_n=1)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    enriched: list[dict] = []
    for appeal in appeals:
        submission = supabase.get_submission(appeal["submission_id"]) or {}
        feedback = supabase.get_feedback(appeal["submission_id"]) or {}
        score_rows = supabase.get_scores(appeal["submission_id"])
        enriched.append(
            _appeal_response(
                appeal,
                board=board,
                submission=submission,
                feedback=feedback,
                scores=score_rows,
            )
        )

    return {"appeals": enriched}


@router.get("/appeals/submission/{submission_id}")
async def get_submission_appeal(submission_id: str) -> dict:
    """Team-facing lookup of a submission's most recent appeal (or 404)."""
    _validate_uuid(submission_id)
    try:
        appeal = supabase.get_appeal_by_submission(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not appeal:
        raise HTTPException(
            status_code=404, detail="No appeal on file for this submission."
        )
    return {"appeal": appeal}


@router.post("/appeals/{appeal_id}/resolve")
async def resolve_appeal(appeal_id: str, body: AppealResolve) -> dict:
    """Log the human evaluator's final decision against an open appeal."""
    _validate_uuid(appeal_id)
    if not body.evaluator.strip():
        raise HTTPException(status_code=422, detail="Evaluator identity is required.")

    submission: dict = {}
    try:
        appeal = supabase.get_appeal(appeal_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not appeal:
        raise HTTPException(status_code=404, detail=f"Appeal {appeal_id} not found.")
    if appeal.get("status") == "resolved":
        raise HTTPException(
            status_code=409,
            detail="This appeal has already been resolved.",
        )

    try:
        updated = supabase.resolve_appeal(
            appeal_id,
            body.decision,
            body.decision_note.strip(),
            body.evaluator.strip(),
        )
        submission = supabase.get_submission(appeal["submission_id"]) or {}
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Non-blocking decision email to the filing contact (fall back to
    #     the submission's registered team email). Mail never fails resolve.
    recipient = appeal.get("contact_email") or (submission.get("team_email") or "")
    notification = await asyncio.to_thread(
        email_service.send_appeal_resolved,
        team_name=submission.get("team_name", ""),
        team_email=recipient,
        submission_id=appeal["submission_id"],
        decision=body.decision,
        decision_note=body.decision_note.strip(),
    )
    if notification.status != "sent":
        logger.warning(
            "Appeal-resolved email %s (%s)",
            notification.status,
            notification.detail or notification.reason,
        )

    return {
        "appeal": updated,
        "notification": {
            "appeal_email": {
                "status": notification.status,
                "reason": notification.reason,
            }
        },
    }


# --- Results-published gate (v1.3.0) --------------------------------------


@router.get("/hackathon/{hackathon_id}/settings")
async def get_hackathon_settings(hackathon_id: str) -> dict:
    """Return whether results are published (the appeal gate) for a hackathon."""
    try:
        row = supabase.get_hackathon_settings(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    published = bool(row and row.get("results_published_at"))
    return {"hackathon_id": hackathon_id, "results_published": published}


@router.put("/hackathon/{hackathon_id}/results")
async def put_results_published(hackathon_id: str, body: ResultsPublish) -> dict:
    """Flip the results-published gate (evaluator control for the appeal window)."""
    try:
        supabase.update_results_published(hackathon_id, bool(body.published))
        row = supabase.get_hackathon_settings(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "hackathon_id": hackathon_id,
        "results_published": bool(row and row.get("results_published_at")),
    }
