"""API routes for analytics dashboard (v3.2.0).

Track-scoped analytics: score distributions, criterion heatmap,
submission funnel. All aggregations are computed on the fly from
existing data — no stored analytics tables.
"""

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from agents.scoring.base import CRITERIA_NAMES
from backend.services import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{hackathon_id}/overview")
async def analytics_overview(hackathon_id: str) -> dict:
    """Summary stats for a track: totals, averages, counts."""
    try:
        submissions = supabase.get_all_submissions(hackathon_id)
        scores = supabase.get_all_scores(hackathon_id)
        shortlisted = supabase.get_shortlisted_count(hackathon_id)

        # Compute per-criterion averages
        criterion_sums: dict[str, float] = {c: 0.0 for c in CRITERIA_NAMES}
        criterion_counts: dict[str, int] = {c: 0 for c in CRITERIA_NAMES}
        for s in scores:
            c = s.get("criterion")
            if c in criterion_sums:
                criterion_sums[c] += s.get("score", 0)
                criterion_counts[c] += 1

        criterion_averages = {
            c: (criterion_sums[c] / criterion_counts[c] if criterion_counts[c] else 0.0)
            for c in CRITERIA_NAMES
        }

        # Compute average composite (equal weights for simplicity)
        submission_composites: dict[str, dict[str, int]] = defaultdict(dict)
        for s in scores:
            sid = s.get("submission_id")
            c = s.get("criterion")
            if sid and c:
                submission_composites[sid][c] = s.get("score", 0)

        complete_composites = [
            sum(scores_dict.values()) / len(CRITERIA_NAMES)
            for scores_dict in submission_composites.values()
            if len(scores_dict) == len(CRITERIA_NAMES)
        ]
        avg_composite = (
            sum(complete_composites) / len(complete_composites)
            if complete_composites
            else 0.0
        )

    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "hackathon_id": hackathon_id,
        "total_submissions": len(submissions),
        "scored_count": len(submission_composites),
        "shortlisted_count": shortlisted,
        "avg_composite": round(avg_composite, 4),
        "criterion_averages": {c: round(v, 2) for c, v in criterion_averages.items()},
    }


@router.get("/{hackathon_id}/distributions")
async def score_distributions(hackathon_id: str) -> dict:
    """Score distribution histograms per criterion + composite."""
    try:
        scores = supabase.get_all_scores(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Build per-criterion histograms (bins 1-10)
    distributions = {}
    for criterion in CRITERIA_NAMES:
        bins = [{"score": i, "count": 0} for i in range(1, 11)]
        for s in scores:
            if s.get("criterion") == criterion:
                score_val = s.get("score", 0)
                if 1 <= score_val <= 10:
                    bins[score_val - 1]["count"] += 1
        distributions[criterion] = bins

    # Composite distribution (binned 1-10)
    submission_scores: dict[str, dict[str, int]] = defaultdict(dict)
    for s in scores:
        sid = s.get("submission_id")
        c = s.get("criterion")
        if sid and c:
            submission_scores[sid][c] = s.get("score", 0)

    composite_bins = [{"score": i, "count": 0} for i in range(1, 11)]
    for scores_dict in submission_scores.values():
        if len(scores_dict) == len(CRITERIA_NAMES):
            composite = sum(scores_dict.values()) / len(CRITERIA_NAMES)
            bin_idx = min(int(composite), 10) - 1
            if 0 <= bin_idx < 10:
                composite_bins[bin_idx]["count"] += 1

    distributions["composite"] = composite_bins

    return {"hackathon_id": hackathon_id, "distributions": distributions}


@router.get("/{hackathon_id}/funnel")
async def submission_funnel(hackathon_id: str) -> dict:
    """Submission funnel: submitted -> parsed -> scored -> shortlisted -> appealed."""
    try:
        submissions = supabase.get_all_submissions(hackathon_id)
        parsed_count = supabase.get_all_parsed_ids(hackathon_id)
        feedback_count = supabase.get_feedback_count(hackathon_id)
        shortlisted_count = supabase.get_shortlisted_count(hackathon_id)
        appeal_count = supabase.get_appeal_count(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "hackathon_id": hackathon_id,
        "funnel": {
            "submitted": len(submissions),
            "parsed": parsed_count,
            "scored": feedback_count,
            "shortlisted": shortlisted_count,
            "appealed": appeal_count,
        },
    }


@router.get("/{hackathon_id}/heatmap")
async def criterion_heatmap(hackathon_id: str) -> dict:
    """Teams x criteria heatmap (top 20 teams by composite)."""
    try:
        scores = supabase.get_all_scores(hackathon_id)
        submissions = supabase.get_all_submissions(hackathon_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Build submission_id -> team_name mapping
    team_names = {s["id"]: s.get("team_name", "Unknown") for s in submissions}

    # Group scores by submission
    submission_scores: dict[str, dict[str, int]] = defaultdict(dict)
    for s in scores:
        sid = s.get("submission_id")
        c = s.get("criterion")
        if sid and c:
            submission_scores[sid][c] = s.get("score", 0)

    # Compute composites for sorting
    rows = []
    for sid, criteria in submission_scores.items():
        if len(criteria) == len(CRITERIA_NAMES):
            composite = sum(criteria.values()) / len(CRITERIA_NAMES)
            rows.append(
                {
                    "submission_id": sid,
                    "team_name": team_names.get(sid, "Unknown"),
                    "composite": composite,
                    "scores": criteria,
                }
            )

    # Sort by composite desc, take top 20
    rows.sort(key=lambda r: -r["composite"])
    top_rows = rows[:20]

    return {
        "hackathon_id": hackathon_id,
        "heatmap": top_rows,
        "total_scored": len(submission_scores),
    }
