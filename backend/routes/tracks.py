"""API routes for track management (v3.1.0).

Organizers can create/delete tracks, each with its own rubric. All
submissions and scoring are scoped to a track via hackathon_id.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tracks"])


class TrackRequest(BaseModel):
    """POST /api/tracks request body."""

    id: str = Field(..., description="Track slug (e.g. 'sih-2026')")
    name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Optional description")

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Track id cannot be empty.")
        if not all(c.isalnum() or c in "-_" for c in value):
            raise ValueError(
                "Track id can only contain letters, numbers, hyphens, underscores."
            )
        return value

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Track name cannot be empty.")
        return value.strip()


@router.get("/tracks")
async def list_tracks() -> dict:
    """List all tracks."""
    try:
        tracks = supabase.list_tracks()
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"tracks": tracks}


@router.post("/tracks", status_code=201)
async def create_track(body: TrackRequest) -> dict:
    """Create a new track with an equal-weight default rubric."""
    try:
        # Check if track already exists
        existing = supabase.get_track(body.id)
        if existing:
            raise HTTPException(
                status_code=409, detail=f"Track '{body.id}' already exists."
            )

        track = supabase.create_track(body.id, body.name, body.description)

        # Create default rubric for the track (equal weights)
        from agents.scoring.base import CRITERIA_NAMES

        for criterion in CRITERIA_NAMES:
            supabase.upsert_rubric(body.id, {criterion: 0.25})

    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"track": track}


@router.delete("/tracks/{track_id}")
async def delete_track(track_id: str) -> dict:
    """Delete a track. Rejects if submissions exist (cascade prevention)."""
    try:
        # Check if track has submissions
        subs = supabase.get_all_submissions(track_id)
        if subs:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete track '{track_id}': {len(subs)} submission(s) exist.",
            )

        deleted = supabase.delete_track(track_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Track not found.")

    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"deleted": True, "id": track_id}
