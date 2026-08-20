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
