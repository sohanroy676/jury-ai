"""API routes for submission uploads."""

import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.services import supabase

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
    """Upload a submission file and store its metadata.

    Validates the file type and size, uploads to Supabase Storage, then
    inserts a row into the `submissions` table.
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

    return row
