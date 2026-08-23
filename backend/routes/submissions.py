"""API routes for submission uploads."""

import logging
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.parsing.extractor import ParsingError, extract_text
from agents.parsing.images.extract import extract_images
from agents.parsing.images.pipeline import process_submission_images
from backend.config import settings
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
) -> dict:
    """Upload a submission file, parse it, and store both.

    Validates the file type and size, parses the file into structured text,
    uploads to Supabase Storage, then inserts rows into the `submissions`
    and `parsed_submissions` tables.
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

    # --- Insert a row into the submissions table.
    try:
        row = supabase.insert_submission(team_name, file_url, file_type)
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

    return row
