"""Application configuration.

Centralised, type-safe settings loaded from environment variables (and an
optional ``.env`` file) via pydantic-settings. Every other module imports the
singleton returned by :func:`get_settings` rather than reading ``os.environ``
directly, so configuration has exactly one source of truth.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values are read from the process environment first and fall back to a
    local ``.env`` file. Field names map to upper-case env keys.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database -------------------------------------------------------
    database_url: str = Field(
        default="postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        description="asyncpg-compatible PostgreSQL DSN for the Supabase database.",
    )
    db_pool_min_size: int = Field(default=2, ge=1)
    db_pool_max_size: int = Field(default=10, ge=1)
    db_command_timeout: float = Field(default=30.0, gt=0)

    # --- Embeddings -----------------------------------------------------
    embedding_dim: int = Field(
        default=1536,
        description="Dimensionality of text-embedding-3-small vectors.",
    )
    hnsw_ef_search: int = Field(
        default=40,
        ge=1,
        description="pgvector HNSW runtime search breadth (ef_search).",
    )

    # --- Chat answer providers (priority: Groq > Gemini > template) ----
    # Both are free tiers; the offline template answerer covers the no-key case.
    # Groq — free tier, no billing; OpenAI-compatible API.
    groq_api_key: str | None = Field(default=None)
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    # Google Gemini (free tier via AI Studio). Uses the rolling "-latest" alias;
    # pinned ids (e.g. gemini-2.0-flash) can carry a per-account free-tier limit
    # of 0, while the alias has quota.
    gemini_api_key: str | None = Field(default=None)
    gemini_model: str = Field(default="gemini-flash-latest")

    # --- Ingestion (Stage 01) ------------------------------------------
    # Live website scraping of public campus event sources (real HTTP, no keys).
    enable_web_scraping: bool = Field(default=True)
    # UBC AMS — "The Events Calendar" WordPress REST API.
    ams_events_api: str = Field(
        default="https://www.ams.ubc.ca/wp-json/tribe/events/v1/events",
    )
    # Douglas Students' Union — Squarespace events collection (JSON via ?format=json).
    dsu_events_url: str = Field(default="https://www.thedsu.ca/events-9itk7")
    # BCIT Student Association — "The Events Calendar" WordPress REST API.
    bcitsa_events_api: str = Field(
        default="https://www.bcitsa.ca/wp-json/tribe/events/v1/events",
    )
    # SFU — LiveWhale calendar JSON feed.
    sfu_events_feed: str = Field(
        default="https://events.sfu.ca/live/json/events",
    )
    # Max events to pull per source per run.
    scrape_per_source_limit: int = Field(default=40, ge=1)
    # When True, only keep events classified as free.
    free_events_only: bool = Field(default=True)
    # Offline fallback: replay bundled fixtures instead of live HTTP.
    use_mock_sources: bool = Field(default=False)

    # Instagram (added later): when APIFY_API_TOKEN is unset, Instagram
    # scraping is skipped. Vision-LLM is only used for image-flyer sources.
    apify_api_token: str | None = Field(default=None)
    apify_actor_id: str = Field(default="apify/instagram-profile-scraper")
    # Student associations + clubs across the four campuses. Unknown/renamed
    # handles are skipped harmlessly by the scraper.
    club_handles: str = Field(
        default=(
            # UBC — AMS + major undergrad societies and clubs
            "amsubc,ubccsss,nwplusubc,ubcsus,aus_ubc,ubcengineers,"
            "ubcrec,ubcbiztech,ubcdanceclub,"
            # SFU — student society + big clubs
            "simonfraseru,sfss_,sfusurge,sfurecreation,sfu_csss,"
            # BCIT — student association
            "bcit,bcitsa,"
            # Douglas — college + students' union (DSU)
            "douglascollege,thedsu6"
        ),
    )
    # Latest posts pulled per handle each run (kept small to stay near-free).
    instagram_posts_per_handle: int = Field(default=10, ge=1, le=12)
    # Google Gemini reads flyer images (reuses gemini_api_key above). Optional:
    # when unset or out of quota, the Instagram adapter degrades to caption-only
    # extraction on the Groq text model, so ingestion still runs anywhere.
    gemini_vision_model: str = Field(default="gemini-flash-latest")
    # Scheduler cadence for the background ingestion worker.
    ingestion_interval_minutes: int = Field(default=60, ge=1)

    # --- API / CORS -----------------------------------------------------
    # Comma-separated list of allowed frontend origins for the demo UI.
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
    )

    # --- Authentication ---------------------------------------------------
    # HMAC key for signing session tokens. Override in production.
    auth_secret: str = Field(default="dev-secret-change-me")
    # Google OAuth client id (for "Sign in with Google"). When unset, the
    # Google button is hidden and only email/password sign-in is offered.
    google_client_id: str | None = Field(default=None)

    # --- Logging --------------------------------------------------------
    log_level: str = Field(default="INFO")

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a clean list."""

        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def club_handle_list(self) -> list[str]:
        """Return configured club Instagram handles as a clean list."""

        return [
            handle.strip()
            for handle in self.club_handles.split(",")
            if handle.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    Cached so repeated imports do not re-parse the environment.
    """

    return Settings()
