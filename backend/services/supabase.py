"""Supabase client wrapper — the single place that touches Supabase.

All credentials come from environment variables via `config.settings`.
This module intentionally exposes a narrow API so the rest of the
backend never deals with Supabase internals directly.
"""

from supabase import Client, create_client

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


def insert_submission(team_name: str, file_url: str, file_type: str) -> dict:
    """Insert a submission row into Supabase Postgres.

    Args:
        team_name: The team's name.
        file_url: Public URL of the uploaded file.
        file_type: One of ``pdf`` or ``pptx``.

    Returns:
        The inserted row as a dict.
    """
    client = get_client()

    row = (
        client.table("submissions")
        .insert({"team_name": team_name, "file_url": file_url, "file_type": file_type})
        .execute()
        .data[0]
    )

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
