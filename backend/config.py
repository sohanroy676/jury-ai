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

        # --- Image understanding (v0.3.5) -----------------------------
        # Groq vision model used to describe diagram-like images.
        # qwen/qwen3.6-27b is verified vision-capable on the free tier.
        self.groq_vision_model: str = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
        # --- Image understanding (v0.3.6) -----------------------------
        # Vision describer for diagram-like images: "groq" (qwen via
        # Groq, default) or "gemini" (Google AI Studio free tier).
        # Scoring/text stages always use Groq regardless of this value.
        self.vision_provider: str = os.getenv("VISION_PROVIDER", "groq")
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        # Stable free-tier model; gemini-2.5-flash 404s on new keys
        # ("no longer available to new users") — do not go back.
        self.gemini_vision_model: str = os.getenv(
            "GEMINI_VISION_MODEL", "gemini-3.6-flash"
        )
        # Local CLIP zero-shot classifier (open_clip).
        self.clip_model: str = os.getenv("CLIP_MODEL", "ViT-B-32")
        self.clip_pretrained: str = os.getenv("CLIP_PRETRAINED", "openai")
        # At/above this CLIP confidence the top label is trusted for
        # three-tier routing; below it, images are flagged for review.
        self.image_classify_threshold: float = float(
            os.getenv("IMAGE_CLASSIFY_THRESHOLD", "0.7")
        )
        # When the top label is decorative but the best diagram-label
        # probability reaches this floor, classify_image returns that
        # diagram label instead (rescues misread diagrams from being
        # treated as decoration).
        self.image_diagram_floor: float = float(os.getenv("IMAGE_DIAGRAM_FLOOR", "0.3"))
        # Hamming distance at/below which two pHashes count as the
        # same image (within-submission dedupe and cache near-match).
        self.phash_hamming_threshold: int = int(
            os.getenv("PHASH_HAMMING_THRESHOLD", "8")
        )
        # Images smaller than this on either side are skipped as icons.
        self.min_image_dimension: int = int(os.getenv("MIN_IMAGE_DIMENSION", "64"))

        # --- Notifications (v1.2.0) --------------------------------------
        # Transport for team-facing emails: "smtp" (Gmail free tier via
        # App Password, default) or "resend" (Resend REST free tier).
        self.email_provider: str = os.getenv("EMAIL_PROVIDER", "smtp")
        self.email_from: str = os.getenv("EMAIL_FROM", "")
        self.smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user: str = os.getenv("SMTP_USER", "")
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        # Resend talks REST over the already-pinned httpx — the official
        # SDK needs httpx>=0.28 which conflicts with supabase's pin.
        self.resend_api_key: str = os.getenv("RESEND_API_KEY", "")
        # Frontend origins (comma-separated, mirrors FRONTEND_URL). The
        # first entry is the link base for notification emails.
        self.frontend_urls: list[str] = [
            origin.strip()
            for origin in os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
            if origin.strip()
        ]

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

    @property
    def is_gemini_configured(self) -> bool:
        """True when the Gemini API key is present (vision option)."""
        return bool(self.gemini_api_key)

    @property
    def frontend_url(self) -> str:
        """Primary frontend origin — link base for notification emails."""
        return self.frontend_urls[0] if self.frontend_urls else ""

    @property
    def is_smtp_configured(self) -> bool:
        """True when the SMTP transport has everything it needs."""
        return bool(
            self.email_from and self.smtp_host and self.smtp_user and self.smtp_password
        )

    @property
    def is_resend_configured(self) -> bool:
        """True when the Resend transport has everything it needs."""
        return bool(self.email_from and self.resend_api_key)

    @property
    def is_email_configured(self) -> bool:
        """True when credentials for the selected EMAIL_PROVIDER are complete."""
        if self.email_provider == "smtp":
            return self.is_smtp_configured
        if self.email_provider == "resend":
            return self.is_resend_configured
        return False


settings = Settings()
