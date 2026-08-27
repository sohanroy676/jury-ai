"""Supabase client wrapper — the single place that touches Supabase.

All credentials come from environment variables via `config.settings`.
This module intentionally exposes a narrow API so the rest of the
backend never deals with Supabase internals directly.
"""

from datetime import datetime, timezone

from supabase import Client, create_client

from agents.scoring.base import CRITERIA_NAMES
from backend.config import settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when Supabase credentials are missing from the environment."""


_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client, raising if not configured."""
    global _client

    if not settings.is_configured:
        raise SupabaseNotConfiguredError(
            "Supabase credentials are missing. "
            "Copy .env.example to .env and fill in your Supabase values."
        )

    if _client is None:
        _client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )

    return _client


def upload_submission_file(file_bytes: bytes, file_name: str, file_type: str) -> str:
    """Upload a submission file to Supabase Storage and return its public URL.

    Args:
        file_bytes: The raw file contents.
        file_name: The storage path/name (e.g. ``uuid/file.pdf``).
        file_type: One of ``pdf`` or ``pptx`` — used for the Content-Type.

    Returns:
        The public URL of the stored file.
    """
    client = get_client()

    content_type = (
        "application/pdf"
        if file_type == "pdf"
        else (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    )

    client.storage.from_(settings.supabase_storage_bucket).upload(
        path=file_name,
        file=file_bytes,
        file_options={"content-type": content_type},
    )

    return client.storage.from_(settings.supabase_storage_bucket).get_public_url(
        file_name
    )


def insert_submission(
    team_name: str,
    file_url: str,
    file_type: str,
    team_email: str | None = None,
    supersedes_team: bool = False,
) -> dict:
    """Insert a submission row into Supabase Postgres.

    Args:
        team_name: The team's name.
        file_url: Public URL of the uploaded file.
        file_type: One of ``pdf`` or ``pptx``.
        team_email: Contact address for notifications (v1.2.0). Stored as
            NULL when blank so legacy rows and optional input stay valid.
        supersedes_team: When True (v1.1.0 re-submission), first archive
            the team's current active submission by stamping
            ``superseded_at`` so history is preserved while only the new
            row stays active. No-op when the team has no active row.

    Returns:
        The inserted row as a dict.
    """
    client = get_client()

    if supersedes_team:
        client.table("submissions").update(
            {"superseded_at": datetime.now(timezone.utc).isoformat()}
        ).ilike("team_name", team_name).is_("superseded_at", "null").execute()

    row = (
        client.table("submissions")
        .insert(
            {
                "team_name": team_name,
                "file_url": file_url,
                "file_type": file_type,
                # v1.2.0: contact email for notifications. Blank input is
                # stored as NULL (the DB CHECK allows NULL, not '').
                "team_email": (team_email or None),
            }
        )
        .execute()
        .data[0]
    )

    return row


def get_active_submission_by_team(team_name: str) -> dict | None:
    """Return the team's ACTIVE submission (v1.1.0), or ``None``.

    Matching is case-insensitive but exact: ``ilike`` narrows the query,
    then equality is re-verified in Python so pattern characters in team
    names (``%``, ``_``) can never widen the match.

    Returns:
        The newest unsuperseded row for the team, or ``None``.
    """
    client = get_client()

    result = (
        client.table("submissions")
        .select("*")
        .ilike("team_name", team_name)
        .is_("superseded_at", "null")
        .order("uploaded_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    row = rows[0]
    if row["team_name"].strip().lower() != team_name.strip().lower():
        return None
    return row


def insert_parsed_submission(
    submission_id: str,
    raw_text: str,
    sections: list[dict],
    source_format: str,
    image_descriptions: list[dict] | None = None,
) -> dict:
    """Insert a parsed-submission row into Supabase Postgres.

    Args:
        submission_id: The UUID of the parent submission row.
        raw_text: The full extracted text.
        sections: Per-page/slide text chunks (JSON-serializable).
        source_format: One of ``pdf`` or ``pptx``.
        image_descriptions: Vision-LLM descriptions of embedded images
            (v0.3.5). Defaults to an empty list.

    Returns:
        The inserted row as a dict.
    """
    client = get_client()

    row = (
        client.table("parsed_submissions")
        .insert(
            {
                "submission_id": submission_id,
                "raw_text": raw_text,
                "sections": sections,
                "source_format": source_format,
                "image_descriptions": image_descriptions or [],
            }
        )
        .execute()
        .data[0]
    )

    return row


def get_parsed_submission(submission_id: str) -> dict | None:
    """Fetch a parsed submission row from Supabase Postgres.

    Args:
        submission_id: The UUID of the parent submission row.

    Returns:
        The parsed submission row as a dict, or ``None`` if not found.
    """
    client = get_client()

    # NOTE: deliberately NOT using .single() — PostgREST raises
    # APIError PGRST116 on zero rows with .single(), which surfaced as
    # an unhandled 500 when scoring an unknown/unparsed submission id.
    # limit(1) + explicit None keeps the documented dict | None contract.
    result = (
        client.table("parsed_submissions")
        .select("*")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_cached_image(phash: str) -> dict | None:
    """Look up a cached image classification/description by perceptual hash.

    Tries an exact phash match first. If none, scans cached hashes for
    a near-match within ``settings.phash_hamming_threshold`` so slightly
    recompressed copies of a shared template image still hit the cache.

    Args:
        phash: Hex perceptual hash of the image.

    Returns:
        A dict with ``phash``, ``classification``, ``confidence``, and
        ``description``, or ``None`` on miss.
    """
    import imagehash

    from backend.config import settings

    client = get_client()

    columns = "phash, classification, confidence, description"

    # --- Exact match first.
    exact = (
        client.table("image_cache")
        .select(columns)
        .eq("phash", phash)
        .limit(1)
        .execute()
    )
    if exact.data:
        return exact.data[0]

    # --- Near-match scan (hamming distance <= threshold).
    threshold = settings.phash_hamming_threshold
    candidates = client.table("image_cache").select(columns).execute()
    if not candidates.data:
        return None

    target = imagehash.hex_to_hash(phash)
    best_row: dict | None = None
    best_distance = threshold + 1

    for row in candidates.data:
        try:
            distance = target - imagehash.hex_to_hash(row["phash"])
        except (ValueError, TypeError):
            continue  # malformed stored hash — skip it
        if distance < best_distance:
            best_row = row
            best_distance = distance

    return best_row


def upsert_image_cache(
    phash: str, classification: str, confidence: float, description: str | None
) -> None:
    """Insert or update an entry in the image cache, keyed by phash."""
    client = get_client()

    client.table("image_cache").upsert(
        {
            "phash": phash,
            "classification": classification,
            "confidence": confidence,
            "description": description,
        }
    ).execute()


def insert_scores(
    submission_id: str,
    scores: list,
    agent_version: str,
) -> list[dict]:
    """Insert score rows into Supabase Postgres.

    Args:
        submission_id: The UUID of the parent submission row.
        scores: A list of objects with ``criterion``, ``score``, and
            ``justification`` attributes (e.g. ``CriterionScore`` dataclasses).
        agent_version: The version string of the scoring agent.

    Returns:
        The inserted rows as a list of dicts.
    """
    client = get_client()

    rows = [
        {
            "submission_id": submission_id,
            "criterion": s.criterion,
            "score": s.score,
            "justification": s.justification,
            "agent_version": agent_version,
        }
        for s in scores
    ]

    result = client.table("scores").insert(rows).execute()

    return result.data


def list_submissions(limit: int = 100, include_superseded: bool = False) -> list[dict]:
    """List submission rows, newest first (uploaded_at descending).

    By default only ACTIVE submissions are returned (v1.1.0): rows whose
    ``superseded_at`` is set are archived re-submission history and are
    excluded from listings, leaderboards, and batch scoring. Pass
    ``include_superseded=True`` to see archived rows too.

    Args:
        limit: Maximum number of rows to return.
        include_superseded: Include archived (superseded) rows as well.

    Returns:
        A list of submission row dicts; empty when none exist.
    """
    client = get_client()

    query = client.table("submissions").select("*")
    if not include_superseded:
        query = query.is_("superseded_at", "null")
    result = query.order("uploaded_at", desc=True).limit(limit).execute()

    return list(result.data or [])


def get_submission(submission_id: str) -> dict | None:
    """Fetch a single submission row by id.

    Args:
        submission_id: The UUID of the submission row.

    Returns:
        The submission row as a dict, or ``None`` if not found.
    """
    client = get_client()

    # NOTE: limit(1) + explicit None, never .single() — PostgREST raises
    # PGRST116 on zero rows with .single() (see get_parsed_submission).
    result = (
        client.table("submissions")
        .select("*")
        .eq("id", submission_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_scores(submission_id: str) -> list[dict]:
    """Fetch all score rows for a submission, oldest first.

    Args:
        submission_id: The UUID of the parent submission row.

    Returns:
        A list of score row dicts; empty when the submission is unscored.
    """
    client = get_client()

    result = (
        client.table("scores")
        .select("*")
        .eq("submission_id", submission_id)
        .order("scored_at")
        .execute()
    )

    return list(result.data or [])


# --- Rubric config + ranking inputs (v0.6.0) --------------------------


def get_rubric(hackathon_id: str) -> dict[str, float] | None:
    """Fetch configured criterion weights for a hackathon.

    Args:
        hackathon_id: Hackathon scope key ('default' unless multi-hackathon
            support lands later).

    Returns:
        ``{criterion: weight}`` or ``None`` when nothing is configured
        (the caller falls back to equal weights). Rows with unknown
        criteria are ignored defensively; an all-unknown result counts
        as unconfigured.
    """
    client = get_client()

    result = (
        client.table("rubric_config")
        .select("criterion, weight")
        .eq("hackathon_id", hackathon_id)
        .execute()
    )

    rubric = {
        row["criterion"]: float(row["weight"])
        for row in (result.data or [])
        if row.get("criterion") in CRITERIA_NAMES
    }
    return rubric or None


def upsert_rubric(hackathon_id: str, weights: dict[str, float]) -> dict[str, float]:
    """Insert or update one rubric row per criterion for a hackathon.

    Args:
        hackathon_id: Hackathon scope key.
        weights: Normalized fractions keyed by criterion (validated by
            the route via ``validate_weights``).

    Returns:
        The stored weights as ``{criterion: weight}``.
    """
    client = get_client()

    rows = [
        {"hackathon_id": hackathon_id, "criterion": criterion, "weight": float(weight)}
        for criterion, weight in weights.items()
    ]
    result = (
        client.table("rubric_config")
        .upsert(rows, on_conflict="hackathon_id,criterion")
        .execute()
    )

    stored = {row["criterion"]: float(row["weight"]) for row in (result.data or [])}
    # Fall back to the input when the API echoes nothing unexpected.
    return stored or {c: float(w) for c, w in weights.items()}


def get_all_scores() -> list[dict]:
    """Fetch every score row (ranking input), minimal columns.

    Returns:
        A list of rows with ``submission_id``, ``criterion``, ``score``;
        empty when nothing has been scored yet.
    """
    client = get_client()

    result = client.table("scores").select("submission_id, criterion, score").execute()

    return list(result.data or [])


# --- Feedback + export (v0.7.0) ---------------------------------------


def get_all_feedback_ids() -> set[str]:
    """Return submission ids that already have a CURRENT feedback row.

    Batch-feedback input (v1.2.0): one minimal-column query instead of a
    per-submission lookup loop.
    """
    client = get_client()

    result = client.table("feedback").select("submission_id").execute()

    return {row["submission_id"] for row in (result.data or [])}


def upsert_feedback(
    submission_id: str,
    *,
    strengths: list[str],
    weaknesses: list[str],
    suggestion: str,
    verdict: str,
    agent_version: str,
) -> dict:
    """Insert or update the CURRENT feedback row for a submission.

    One row per submission (unique on ``submission_id``): regenerating
    feedback overwrites so reads always reflect the latest scores.

    Args:
        submission_id: The UUID of the parent submission row.
        strengths: Evidence-citing strength bullets.
        weaknesses: Evidence-citing weakness bullets.
        suggestion: The single actionable improvement.
        verdict: ``shortlist`` or ``reject`` (validated upstream).
        agent_version: Provenance string of the generating release.

    Returns:
        The stored row as a dict.
    """
    client = get_client()

    result = (
        client.table("feedback")
        .upsert(
            {
                "submission_id": submission_id,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "suggestion": suggestion,
                "verdict": verdict,
                "agent_version": agent_version,
            },
            on_conflict="submission_id",
        )
        .execute()
    )

    return (result.data or [None])[0]


def get_feedback(submission_id: str) -> dict | None:
    """Fetch the feedback row for a submission.

    Args:
        submission_id: The UUID of the parent submission row.

    Returns:
        The feedback row as a dict, or ``None`` when none exists yet.
    """
    client = get_client()

    # NOTE: limit(1) + explicit None, never .single() — PostgREST raises
    # PGRST116 on zero rows with .single() (see get_parsed_submission).
    result = (
        client.table("feedback")
        .select("*")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


# --- Appeals (v1.3.0) ---------------------------------------------------


def insert_appeal(
    submission_id: str,
    reason: str,
    contact_email: str | None = None,
    hackathon_id: str = "default",
) -> dict:
    """File an appeal against a submission (results must be published).

    Raises the underlying ``supabase`` conflict error when the partial
    unique index ``(submission_id) where status='open'`` rejects a second
    open appeal — the route maps that to a 409 before inserting.

    Args:
        submission_id: The UUID of the scored, feedback-carrying submission.
        reason: The team's written contest-argument.
        contact_email: Address for appeal outcome notifications (blank opts out).
        hackathon_id: Hackathon scope key.

    Returns:
        The inserted appeal row as a dict.
    """
    client = get_client()

    row = (
        client.table("appeals")
        .insert(
            {
                "submission_id": submission_id,
                "hackathon_id": hackathon_id,
                "reason": reason,
                "contact_email": (contact_email or None),
            }
        )
        .execute()
        .data[0]
    )
    return row


def get_appeal(appeal_id: str) -> dict | None:
    """Fetch one appeal by id, or ``None`` when it does not exist."""
    client = get_client()

    result = client.table("appeals").select("*").eq("id", appeal_id).limit(1).execute()

    if not result.data:
        return None

    return result.data[0]


def get_appeal_by_submission(submission_id: str) -> dict | None:
    """Return the most recent appeal for a submission (team-facing).

    Returns the newest row regardless of status so the team-facing view can
    show both an open appeal and a resolved one. ``None`` when none exists.
    """
    client = get_client()

    result = (
        client.table("appeals")
        .select("*")
        .eq("submission_id", submission_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def list_appeals(status: str | None = None) -> list[dict]:
    """Fetch appeals for the evaluator queue, newest-first.

    Args:
        status: When ``"open"`` or ``"resolved"``, filter to that state;
            ``None`` returns every appeal.

    Returns:
        A list of appeal rows.
    """
    client = get_client()

    query = client.table("appeals").select("*")
    if status in ("open", "resolved"):
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()

    return list(result.data or [])


def resolve_appeal(
    appeal_id: str,
    decision: str,
    decision_note: str,
    evaluator: str,
) -> dict | None:
    """Resolve an open appeal, logging the final decision against it.

    Args:
        appeal_id: The UUID of the appeal to resolve.
        decision: ``upheld`` or ``dismissed`` (validated upstream).
        decision_note: Free-text rationale for the decision.
        evaluator: Identity of the human evaluator who decided.

    Returns:
        The updated appeal row, or ``None`` when the appeal does not exist.
    """
    client = get_client()

    result = (
        client.table("appeals")
        .update(
            {
                "status": "resolved",
                "decision": decision,
                "decision_note": decision_note,
                "evaluator": evaluator,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", appeal_id)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


# --- Hackathon settings / results-published gate (v1.3.0) ---------------


def get_hackathon_settings(hackathon_id: str) -> dict | None:
    """Fetch a hackathon's settings row (results-published gate).

    Returns ``None`` when the hackathon row does not exist (the route should
    treat an unknown hackathon as NOT published).
    """
    client = get_client()

    result = (
        client.table("hackathon_settings")
        .select("*")
        .eq("hackathon_id", hackathon_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def update_results_published(hackathon_id: str, published: bool) -> dict:
    """Flip the results-published gate for a hackathon.

    ``published=True`` stamps ``results_published_at`` (idempotent);
    ``published=False`` clears it, closing the appeal window.
    """
    client = get_client()

    row = (
        client.table("hackathon_settings")
        .update(
            {
                "results_published_at": (
                    datetime.now(timezone.utc).isoformat() if published else None
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("hackathon_id", hackathon_id)
        .execute()
    )

    return (row.data or [{}])[0]
