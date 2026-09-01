"""API routes for the appeal flow (v1.3.0).

Teams may contest a result ONLY after results are published (a feedback
verdict exists). Appeals land in an evaluator queue with the original AI
scores + feedback attached; the evaluator resolves them with notes and a
final decision, which is logged on the appeal row and emailed to the team.
Mail problems never fail an appeal action (email-seam contract).
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.services import email as email_service
from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["appeals"])

MIN_APPEAL_LENGTH = 50

# Valid status transitions. pending -> under_review -> upheld|overturned.
# Terminal states (upheld/overturned) can never be reopened.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"under_review", "upheld", "overturned"},
    "under_review": {"upheld", "overturned"},
    "upheld": set(),
    "overturned": set(),
}
TERMINAL_STATUSES = {"upheld", "overturned"}


class AppealRequest(BaseModel):
    """POST /api/submissions/{id}/appeal request body."""

    appeal_text: str = Field(..., description="The team's appeal.")

    @field_validator("appeal_text")
    @classmethod
    def _check_length(cls, value: str) -> str:
        if len(value.strip()) < MIN_APPEAL_LENGTH:
            raise ValueError(
                f"appeal_text must be at least {MIN_APPEAL_LENGTH} characters."
            )
        return value.strip()


class AppealResolution(BaseModel):
    """PUT /api/appeals/{id} request body."""

    status: str = Field(..., description="under_review | upheld | overturned")
    evaluator_notes: str = Field(..., description="Required evaluator notes.")
    resolved_by: str = Field(..., description="Evaluator name or email.")

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        if value not in ALLOWED_TRANSITIONS:
            raise ValueError("status must be one of: under_review, upheld, overturned.")
        return value

    @field_validator("evaluator_notes")
    @classmethod
    def _check_notes(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("evaluator_notes must be at least 10 characters.")
        return value.strip()

    @field_validator("resolved_by")
    @classmethod
    def _check_resolver(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resolved_by is required.")
        return value.strip()


def _compose_appeal(appeal: dict) -> dict:
    """Attach submission + scores + feedback to an appeal row for the queue."""
    sid = appeal["submission_id"]
    submission = supabase.get_submission(sid) or {}
    scores = supabase.get_scores(sid)
    feedback = supabase.get_feedback(sid)
    return {
        **appeal,
        "submission": submission,
        "scores": scores,
        "feedback": feedback,
    }


@router.post("/submissions/{submission_id}/appeal", status_code=201)
async def file_appeal(submission_id: str, body: AppealRequest) -> dict:
    """File an appeal for a submission whose results are published."""
    try:
        UUID(submission_id)
        submission = supabase.get_submission(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")

    # Results must be published: a feedback verdict must exist.
    try:
        feedback = supabase.get_feedback(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if feedback is None:
        raise HTTPException(
            status_code=409,
            detail="Results have not been published yet - appeals open after feedback is generated.",
        )

    # One live appeal per submission.
    try:
        existing = supabase.get_appeal(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An appeal already exists for this submission (status: {existing['status']}).",
        )

    try:
        hackathon_id = submission.get("hackathon_id", "default")
        appeal = supabase.insert_appeal(
            submission_id, body.appeal_text, hackathon_id=hackathon_id
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Confirmation email - graceful, never fails the appeal.
    notification = await asyncio.to_thread(
        email_service.send_appeal_confirmation,
        team_name=submission.get("team_name") or "",
        team_email=submission.get("team_email") or "",
        appeal_id=appeal["id"],
    )
    if notification.status != "sent":
        logger.warning(
            "Appeal confirmation email %s (%s)",
            notification.status,
            notification.detail or notification.reason,
        )

    return {
        **appeal,
        "notification": {
            "appeal_confirmation": {
                "status": notification.status,
                "reason": notification.reason,
            }
        },
    }


@router.get("/submissions/{submission_id}/appeal")
async def get_submission_appeal(submission_id: str) -> dict:
    """Return the current appeal for a submission (or null)."""
    try:
        UUID(submission_id)
        appeal = supabase.get_appeal(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"submission_id": submission_id, "appeal": appeal}


@router.get("/appeals")
async def list_appeals(
    status: str | None = Query(default=None),
    hackathon_id: str = Query(default="default"),
) -> dict:
    """Evaluator queue: list appeals, optionally filtered by status and track."""
    if (
        status is not None
        and status not in ALLOWED_TRANSITIONS
        and status not in TERMINAL_STATUSES
    ):
        raise HTTPException(
            status_code=422,
            detail="status must be one of: pending, under_review, upheld, overturned.",
        )
    try:
        appeals = supabase.list_appeals(status=status, hackathon_id=hackathon_id)
        composed = [_compose_appeal(a) for a in appeals]
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"appeals": composed}


@router.put("/appeals/{appeal_id}")
async def resolve_appeal(appeal_id: str, body: AppealResolution) -> dict:
    """Resolve an appeal: under_review, upheld, or overturned."""
    try:
        UUID(appeal_id)
        appeal = supabase.get_appeal_by_id(appeal_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found.")

    current = appeal["status"]
    if body.status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot move appeal from '{current}' to '{body.status}'.",
        )

    resolved_at = (
        datetime.now(timezone.utc).isoformat()
        if body.status in TERMINAL_STATUSES
        else None
    )
    try:
        updated = supabase.update_appeal(
            appeal_id,
            status=body.status,
            evaluator_notes=body.evaluator_notes,
            resolved_by=body.resolved_by,
            resolved_at=resolved_at,
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Outcome email on terminal decisions - graceful, never fails.
    if body.status in TERMINAL_STATUSES:
        submission = supabase.get_submission(appeal["submission_id"]) or {}
        notification = await asyncio.to_thread(
            email_service.send_appeal_resolution,
            team_name=submission.get("team_name") or "",
            team_email=submission.get("team_email") or "",
            decision=body.status,
            evaluator_notes=body.evaluator_notes,
        )
        if notification.status != "sent":
            logger.warning(
                "Appeal resolution email %s (%s)",
                notification.status,
                notification.detail or notification.reason,
            )
    else:
        notification = email_service.EmailResult("skipped", "non_terminal")

    return {
        **updated,
        "notification": {
            "appeal_resolution": {
                "status": notification.status,
                "reason": notification.reason,
            }
        },
    }
