"""API routes for submission uploads."""

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.parsing.extractor import ParsingError, extract_text
from agents.parsing.images.extract import extract_images
from agents.parsing.images.pipeline import process_submission_images
from backend.config import settings
from backend.services import email as email_service
from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["submissions"])

# Allowed file extensions and their canonical type.
ALLOWED_EXTENSIONS = {".pdf": "pdf", ".pptx": "pptx"}

# Max upload size: 50 MB.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/submissions", status_code=201)
async def create_submission(
    team_name: str = Form(...),
    file: UploadFile = File(...),
    replace_existing: bool = Form(False),
    team_email: str = Form(""),
) -> dict:
    """Upload a submission file, parse it, and store both.

    Validates the file type and size, parses the file into structured text,
    uploads to Supabase Storage, then inserts rows into the `submissions`
    and `parsed_submissions` tables.

    Re-submission (v1.1.0): when the team already has an active submission,
    the request is rejected with 409 unless ``replace_existing`` is true —
    in which case the previous active row is archived (``superseded_at``
    stamped, history preserved) and this upload becomes the team's active
    submission.

    Notifications (v1.2.0): ``team_email`` opts the team into a
    confirmation email now and results-with-feedback later. Optional at
    the API level (blank skips notifications); the portal requires it.
    """
    # --- Validate file type by extension (never trust the client).
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Only .pdf and .pptx are allowed.",
        )
    file_type = ALLOWED_EXTENSIONS[file_ext]

    # --- Validate team name is non-empty.
    if not team_name.strip():
        raise HTTPException(status_code=400, detail="Team name is required.")

    # --- Validate the contact email when provided (v1.2.0). Malformed
    #     input is rejected BEFORE anything is persisted or emailed.
    team_email = team_email.strip()
    if team_email and not email_service.is_valid_email(team_email):
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid contact email address.",
        )

    # --- Re-submission gate (v1.1.0): a duplicate upload under the same
    #     team name must be an explicit replace, so the portal can show a
    #     confirmation prompt driven by this 409.
    try:
        existing_active = supabase.get_active_submission_by_team(team_name)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if existing_active is not None and not replace_existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Team '{team_name.strip()}' already has an active submission "
                f"(uploaded {existing_active['uploaded_at']}). "
                "Confirm below to replace it - the previous version is kept in history."
            ),
        )

    # --- Read and validate file size.
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 50 MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # --- Parse the file into structured text (before persisting anything,
    #     so a corrupt file that can't be parsed is rejected cleanly).
    try:
        parsed = extract_text(file_bytes, file_type)
    except ParsingError as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not parse file: {exc}"
        ) from exc

    # --- Understand embedded images (v0.3.5): extract -> dedupe ->
    #     cache -> CLIP classify -> vision describe. Failures here
    #     degrade gracefully: the upload proceeds with whatever
    #     descriptions were produced (possibly none) — image
    #     understanding must never block a valid submission.
    try:
        images = extract_images(
            file_bytes, file_type, min_dimension=settings.min_image_dimension
        )
        parsed.image_descriptions = process_submission_images(
            images,
            cache_get=supabase.get_cached_image,
            cache_put=supabase.upsert_image_cache,
            confidence_threshold=settings.image_classify_threshold,
            phash_threshold=settings.phash_hamming_threshold,
        )
    except Exception:
        logger.warning(
            "Image understanding failed; continuing without descriptions",
            exc_info=True,
        )
        parsed.image_descriptions = []

    # --- Upload to Supabase Storage under a unique path.
    storage_path = f"{uuid.uuid4()}/{file.filename}"
    try:
        file_url = supabase.upload_submission_file(file_bytes, storage_path, file_type)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Insert a row into the submissions table (archiving the team's
    #     previous active row first when this is an explicit re-submission).
    try:
        row = supabase.insert_submission(
            team_name,
            file_url,
            file_type,
            team_email=team_email,
            supersedes_team=bool(existing_active),
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Insert the parsed output, linked to the submission row.
    try:
        supabase.insert_parsed_submission(
            row["id"],
            parsed.raw_text,
            parsed.sections,
            parsed.source_format,
            image_descriptions=parsed.image_descriptions,
        )
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # --- Confirmation email (v1.2.0): fires only after the whole
    #     parse-complete path succeeded. Degrades gracefully — a mail
    #     problem must never fail an upload (image-stage philosophy).
    notification = await asyncio.to_thread(
        email_service.send_submission_confirmation,
        team_name=row.get("team_name") or team_name.strip(),
        team_email=row.get("team_email") or team_email,
        file_type=file_type,
        uploaded_at=row.get("uploaded_at", ""),
    )
    if notification.status != "sent":
        logger.warning(
            "Confirmation email %s (%s)",
            notification.status,
            notification.detail or notification.reason,
        )

    return {
        **row,
        "notification": {
            "confirmation_email": {
                "status": notification.status,
                "reason": notification.reason,
            }
        },
    }


@router.get("/submissions")
async def get_submissions() -> list[dict]:
    """List uploaded submissions, newest first.

    Powers the evaluator dashboard feed and team status views.
    """
    try:
        return supabase.list_submissions()
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/submissions/{submission_id}")
async def read_submission(submission_id: str) -> dict:
    """Return the full record for one submission.

    Composes the submission row, its parsed text (when the parse stage
    has run), and its score rows (when scored). All three stages are
    orphan-tolerant: a valid submission may legitimately have no parsed
    text yet or no scores yet.
    """
    # Reject malformed ids before touching Postgres — a non-UUID would
    # surface as a PostgREST 400/APIError and an unhandled 500.
    try:
        uuid.UUID(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Submission not found.") from exc

    try:
        submission = supabase.get_submission(submission_id)
        if submission is None:
            raise HTTPException(status_code=404, detail="Submission not found.")
        parsed = supabase.get_parsed_submission(submission_id)
        scores = supabase.get_scores(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # v2.1.0: images the CLIP router flagged as low-confidence or
    # undescribed are surfaced for evaluator review. Fails soft — a
    # malformed image_descriptions payload must not break the detail view.
    flagged_images: list[dict] = []
    if parsed:
        for desc in parsed.get("image_descriptions") or []:
            if isinstance(desc, dict) and desc.get("needs_human_review"):
                flagged_images.append(desc)

    return {
        "submission": submission,
        "parsed": parsed,
        "scores": scores,
        "flagged_images": flagged_images,
    }
