"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

# Load .env from repo root (one level up from backend/)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


class Settings:
    """Runtime settings read from environment variables.

    All values come from the root `.env` file (see `.env.example`).
    """

    def __init__(self) -> None:
        self.supabase_url: str = os.getenv("SUPABASE_URL", "")
        self.supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
        self.supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_storage_bucket: str = os.getenv(
            "SUPABASE_STORAGE_BUCKET", "submissions"
        )
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        """True when the required Supabase credentials are present."""
        return bool(
            self.supabase_url
            and self.supabase_anon_key
            and self.supabase_service_role_key
        )

    @property
    def is_groq_configured(self) -> bool:
        """True when the Groq API key is present."""
        return bool(self.groq_api_key)


settings = Settings()
