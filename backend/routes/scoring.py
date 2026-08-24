"""API routes for triggering submission scoring."""

from fastapi import APIRouter, HTTPException
from groq import GroqError

from agents.scoring.scorer import ScoringResult, build_scoring_text, score_submission
from backend.services import supabase

router = APIRouter(prefix="/api", tags=["scoring"])


@router.post("/submissions/{submission_id}/score", status_code=200)
async def score_submission_endpoint(submission_id: str) -> dict:
    """Trigger scoring for a given submission.

    Fetches the parsed text from Supabase, calls the scoring agent
    (Groq-powered), and stores the results in the ``scores`` table.
    """
    # --- Fetch the parsed submission text.
    try:
        parsed = supabase.get_parsed_submission(submission_id)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not parsed:
        raise HTTPException(
            status_code=404,
            detail=f"Submission {submission_id} not found or not yet parsed.",
        )

    # --- Score the submission. Image descriptions (v0.3.5), when
    #     present, are merged into the text the agents see. The four
    #     v0.5.0 specialist agents run in parallel behind this call.
    scoring_text = build_scoring_text(
        parsed["raw_text"], parsed.get("image_descriptions")
    )
    try:
        result: ScoringResult = await score_submission(submission_id, scoring_text)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GroqError as exc:
        raise HTTPException(status_code=503, detail=f"Scoring failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # --- Store the scores.
    try:
        supabase.insert_scores(submission_id, result.scores, result.agent_version)
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "submission_id": submission_id,
        "agent_version": result.agent_version,
        "scores": [
            {
                "criterion": s.criterion,
                "score": s.score,
                "justification": s.justification,
            }
            for s in result.scores
        ],
    }
