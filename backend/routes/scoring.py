"""API routes for triggering submission scoring."""

from fastapi import APIRouter, HTTPException, Query
from groq import GroqError

from agents.scoring.base import CRITERIA_NAMES
from agents.scoring.scorer import ScoringResult, build_scoring_text, score_submission
from backend.services import supabase

router = APIRouter(prefix="/api", tags=["scoring"])

# The batch route scans the whole submission pool to find pending ones.
MAX_BATCH_SCAN = 10000


async def _score_one_submission(submission_id: str) -> dict:
    """Score one submission end to end and return the response body.

    Shared by the single-submission endpoint and the v1.0.0 batch
    endpoint so both surfaces behave identically. Raises ``HTTPException``
    with a specific status code on every failure mode (404 unknown /
    unparsed, 503 Supabase or Groq unavailable, 500 persistent malformed
    LLM output).
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


@router.post("/submissions/{submission_id}/score", status_code=200)
async def score_submission_endpoint(submission_id: str) -> dict:
    """Trigger scoring for a given submission.

    Fetches the parsed text from Supabase, calls the scoring agent
    (Groq-powered), and stores the results in the ``scores`` table.
    """
    return await _score_one_submission(submission_id)


def _complete_scored_ids(score_rows: list[dict]) -> set[str]:
    """Return submission ids that already have all four criterion scores."""
    counts: dict[str, set[str]] = {}
    for row in score_rows:
        criterion = row.get("criterion")
        if criterion in CRITERIA_NAMES:
            counts.setdefault(row["submission_id"], set()).add(criterion)
    return {
        sid for sid, criteria in counts.items() if len(criteria) == len(CRITERIA_NAMES)
    }


@router.post("/submissions/score-pending", status_code=200)
async def score_pending_submissions(
    limit: int = Query(default=10, gt=0, le=50),
) -> dict:
    """Sequentially score submissions that lack a complete score set.

    Built for pilot scale (v1.0.0): an organizer can score dozens of
    teams without calling the single-submission endpoint once per team.
    Submissions are processed ONE AT A TIME — the four specialist agents
    still run in parallel within each submission, but submissions never
    overlap, which keeps the run inside Groq's free-tier rate limits and
    lets the scorer's own backoff absorb any 429s.

    A submission is *pending* while it has no complete set of the four
    criterion scores; partially scored submissions therefore re-score,
    which self-heals interrupted runs. One submission's failure never
    aborts the batch — failures are reported per item instead.

    ``limit`` caps how many submissions this call attempts (default 10,
    max 50) so a demo cannot accidentally fire hundreds of Groq calls;
    the response reports how many pending submissions remain.
    """
    try:
        submissions = supabase.list_submissions(limit=MAX_BATCH_SCAN)
        score_rows = supabase.get_all_scores()
    except supabase.SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    complete = _complete_scored_ids(score_rows)
    pending = [s for s in submissions if s["id"] not in complete]
    batch = pending[:limit]

    results: list[dict] = []
    for submission in batch:
        sid = submission["id"]
        try:
            outcome = await _score_one_submission(sid)
        except HTTPException as exc:
            results.append(
                {
                    "submission_id": sid,
                    "team_name": submission.get("team_name", ""),
                    "ok": False,
                    "error": str(exc.detail),
                }
            )
            continue
        results.append(
            {
                "submission_id": sid,
                "team_name": submission.get("team_name", ""),
                "ok": True,
                "agent_version": outcome["agent_version"],
            }
        )

    scored = sum(1 for r in results if r["ok"])
    failed = len(results) - scored
    return {
        "scored": scored,
        "failed": failed,
        "remaining": max(len(pending) - len(batch), 0),
        "results": results,
    }
