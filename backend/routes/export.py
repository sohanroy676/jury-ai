"""API routes for result exports (v0.7.0).

- GET /api/export/csv                       — leaderboard as CSV
- GET /api/export/submissions/{id}/pdf      — per-team report as PDF

Both reuse the exact ranking engine behind GET /api/rankings so exported
numbers always match the on-screen leaderboard. CSV uses Python's stdlib
``csv`` module; PDF uses ReportLab (free/open-source).
"""

import csv
import io
import re

from fastapi import APIRouter, HTTPException, Query, Response

from agents.scoring.base import CRITERIA_NAMES
from backend.routes.ranking import load_leaderboard
from backend.services import pdf, supabase
from version import APP_VERSION

router = APIRouter(prefix="/api", tags=["export"])


def _safe_filename_stem(raw: str, fallback: str) -> str:
    """Reduce a user-controlled string to a safe filename stem.

    Keeps alphanumerics, dashes, and underscores only — prevents header
    injection/path tricks via Content-Disposition — collapsing everything
    else into single underscores for readable names, and falling back
    when nothing survives.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned or fallback)[:60]


@router.get("/export/csv")
def export_rankings_csv(
    hackathon_id: str = "default",
    top_n: int | None = Query(default=None, gt=0),
    min_score: float | None = Query(default=None, ge=0, le=10),
) -> Response:
    """Export the ranked leaderboard (with shortlist flags) as CSV.

    Columns: rank, team_name, one column per criterion, composite_score,
    shortlisted. Only fully-scored submissions appear (they are the only
    ones the ranking engine ranks).
    """
    if top_n is not None and min_score is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either top_n or min_score, not both.",
        )

    try:
        board = load_leaderboard(hackathon_id, top_n=top_n, min_score=min_score)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["rank", "team_name", *CRITERIA_NAMES, "composite_score", "shortlisted"]
    )
    for entry in board["ranked"]:
        writer.writerow(
            [
                entry["rank"],
                entry["team_name"],
                *[entry["criterion_scores"][c] for c in CRITERIA_NAMES],
                entry["composite_score"],
                "yes" if entry["shortlisted"] else "no",
            ]
        )

    stem = _safe_filename_stem(hackathon_id, "default")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rankings_{stem}.csv"'},
    )


@router.get("/export/submissions/{submission_id}/pdf")
def export_submission_pdf(
    submission_id: str,
    hackathon_id: str = "default",
    top_n: int = Query(default=5, gt=0),
) -> Response:
    """Export one team's full evaluation (scores + feedback) as a PDF."""
    # --- The submission must exist and be fully scored.
    try:
        submission = supabase.get_submission(submission_id)
        if submission is None:
            raise HTTPException(
                status_code=404,
                detail=f"Submission {submission_id} not found.",
            )
        board = load_leaderboard(hackathon_id, top_n=top_n)
        score_rows = supabase.get_scores(submission_id)
        feedback = supabase.get_feedback(submission_id)
    except HTTPException:
        raise
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
                f"Submission {submission_id} has no complete score set, "
                "so there is nothing to report yet."
            ),
        )

    by_criterion = {row["criterion"]: row for row in score_rows}
    ordered_scores = [by_criterion[c] for c in CRITERIA_NAMES]

    pdf_bytes = pdf.render_submission_report(
        team_name=entry["team_name"],
        hackathon_id=hackathon_id,
        rank=entry["rank"],
        total_scored=board["scored_count"],
        composite_score=entry["composite_score"],
        shortlisted=entry["shortlisted"],
        tied_on_composite=entry["tied_on_composite"],
        scores=ordered_scores,
        feedback=feedback,
        agent_version=f"v{APP_VERSION}",
    )

    stem = _safe_filename_stem(entry["team_name"], submission_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="evaluation_{stem}.pdf"'
        },
    )
