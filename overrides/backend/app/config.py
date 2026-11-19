"""Application configuration.

Every value is sourced from the environment (or a local ``.env`` file).
No secret is ever hard-coded, and nothing in here is shipped to the iOS app —
the app only ever learns the public base URL of this API.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- core ---------------------------------------------------------------
    env: str = Field(default="development", alias="BRIEFLY_ENV")
    log_level: str = Field(default="INFO", alias="BRIEFLY_LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="BRIEFLY_API_HOST")
    api_port: int = Field(default=8000, alias="BRIEFLY_API_PORT")
    cors_origins: str = Field(default="", alias="BRIEFLY_CORS_ORIGINS")

    # --- database -----------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://briefly:briefly@localhost:5432/briefly",
        alias="BRIEFLY_DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="BRIEFLY_DATABASE_ECHO")

    # --- auth ---------------------------------------------------------------
    admin_token: str = Field(default="", alias="BRIEFLY_ADMIN_TOKEN")
    client_api_key: str = Field(default="", alias="BRIEFLY_CLIENT_API_KEY")

    # --- ingestion ----------------------------------------------------------
    user_agent: str = Field(
        default="BrieflyNewsBot/0.1 (+https://example.com/briefly-bot)",
        alias="BRIEFLY_USER_AGENT",
    )
    http_timeout_seconds: float = Field(default=20.0, alias="BRIEFLY_HTTP_TIMEOUT_SECONDS")
    respect_robots: bool = Field(default=True, alias="BRIEFLY_RESPECT_ROBOTS")
    max_articles_per_feed: int = Field(default=60, alias="BRIEFLY_MAX_ARTICLES_PER_FEED")
    ingest_lookback_hours: int = Field(default=36, alias="BRIEFLY_INGEST_LOOKBACK_HOURS")
    # Reports that pass the Arbitration desk's gate are kept this long instead.
    # Judgments are not stale after a day and law reporters file a handful a
    # week, so a 36-hour window leaves the desk nearly empty. Nothing else is
    # kept longer: every other section still uses the window above.
    arbitration_lookback_hours: int = Field(
        default=168, alias="BRIEFLY_ARBITRATION_LOOKBACK_HOURS"
    )
    google_news_hl: str = Field(default="en-IN", alias="BRIEFLY_GOOGLE_NEWS_HL")
    google_news_gl: str = Field(default="IN", alias="BRIEFLY_GOOGLE_NEWS_GL")
    google_news_ceid: str = Field(default="IN:en", alias="BRIEFLY_GOOGLE_NEWS_CEID")

    # --- clustering ---------------------------------------------------------
    cluster_similarity_threshold: float = Field(
        default=0.42, alias="BRIEFLY_CLUSTER_SIMILARITY_THRESHOLD"
    )
    cluster_time_window_hours: int = Field(default=30, alias="BRIEFLY_CLUSTER_TIME_WINDOW_HOURS")
    embedding_provider: str = Field(default="none", alias="BRIEFLY_EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="text-embedding-3-small", alias="BRIEFLY_EMBEDDING_MODEL")

    # --- llm ----------------------------------------------------------------
    llm_provider: str = Field(default="rule_based", alias="BRIEFLY_LLM_PROVIDER")
    llm_model: str = Field(default="claude-sonnet-4-5", alias="BRIEFLY_LLM_MODEL")
    llm_max_tokens: int = Field(default=1500, alias="BRIEFLY_LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=60.0, alias="BRIEFLY_LLM_TIMEOUT_SECONDS")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    summary_max_words: int = Field(default=22, alias="BRIEFLY_SUMMARY_MAX_WORDS")
    # How many stories one processing run takes, best-sourced first.
    process_batch_size: int = Field(default=200, alias="BRIEFLY_PROCESS_BATCH_SIZE")
    # Whose words go on the card.
    #   excerpt  — one outlet's own opening line, quoted unaltered and credited.
    #   composed — Briefly's own summary, assembled from extracted facts.
    #   auto     — composed when a hosted model wrote the facts, excerpt when
    #              the offline extractor did. Without a model there is nothing
    #              that can honestly be called an original summary of a
    #              one-sentence feed item; quoting it is the truthful option.
    card_mode: str = Field(default="auto", alias="BRIEFLY_CARD_MODE")
    # Whether a story needs its core fact confirmed by a second independent
    # outlet (or an official source) before it may be shown at all.
    #   false (default) — single-outlet stories are shown, labelled REPORTED
    #                     with "1 source", never CONFIRMED.
    #   true            — they are held. Specialist desks such as Arbitration,
    #                     where one law reporter is often the only outlet
    #                     covering a judgment, then stay mostly empty.
    require_corroboration: bool = Field(default=False, alias="BRIEFLY_REQUIRE_CORROBORATION")

    # --- tts ----------------------------------------------------------------
    tts_provider: str = Field(default="local", alias="BRIEFLY_TTS_PROVIDER")
    tts_voice: str = Field(default="briefly-anchor", alias="BRIEFLY_TTS_VOICE")
    tts_format: str = Field(default="mp3", alias="BRIEFLY_TTS_FORMAT")
    # Spoken word, one voice, no music. 48 kbit/s mono is transparent for
    # speech and a third the size of a music-grade encode — which matters
    # when the audio is committed to a repository twice a day.
    tts_bitrate: str = Field(default="48k", alias="BRIEFLY_TTS_BITRATE")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_TTS_MODEL")
    azure_speech_key: str = Field(default="", alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="", alias="AZURE_SPEECH_REGION")

    # --- storage ------------------------------------------------------------
    storage_backend: str = Field(default="local", alias="BRIEFLY_STORAGE_BACKEND")
    storage_local_dir: str = Field(default="./var/media", alias="BRIEFLY_STORAGE_LOCAL_DIR")
    storage_public_base_url: str = Field(
        default="http://localhost:8000/media", alias="BRIEFLY_STORAGE_PUBLIC_BASE_URL"
    )
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    s3_bucket: str = Field(default="", alias="BRIEFLY_S3_BUCKET")
    s3_endpoint_url: str = Field(default="", alias="BRIEFLY_S3_ENDPOINT_URL")

    # --- scheduler ----------------------------------------------------------
    scheduler_enabled: bool = Field(default=False, alias="BRIEFLY_SCHEDULER_ENABLED")
    ingest_cron: str = Field(default="*/20 * * * *", alias="BRIEFLY_INGEST_CRON")
    daily_podcast_cron: str = Field(default="30 0 * * *", alias="BRIEFLY_DAILY_PODCAST_CRON")
    scheduler_timezone: str = Field(default="Asia/Kolkata", alias="BRIEFLY_SCHEDULER_TIMEZONE")

    # --- quality control ----------------------------------------------------
    qc_autopublish: bool = Field(default=True, alias="BRIEFLY_QC_AUTOPUBLISH")
    qc_max_source_overlap: float = Field(default=0.55, alias="BRIEFLY_QC_MAX_SOURCE_OVERLAP")

    @field_validator("respect_robots")
    @classmethod
    def _robots_must_stay_on(cls, v: bool) -> bool:
        # Deliberately non-configurable in effect: Briefly never ignores robots.txt.
        return True

    @field_validator("card_mode")
    @classmethod
    def _known_card_mode(cls, v: str) -> str:
        v = (v or "auto").strip().lower()
        if v not in {"auto", "excerpt", "composed"}:
            raise ValueError("BRIEFLY_CARD_MODE must be auto, excerpt or composed")
        return v

    def resolved_card_mode(self, extraction_provider: str) -> str:
        if self.card_mode != "auto":
            return self.card_mode
        return "excerpt" if extraction_provider == "rule_based" else "composed"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def media_dir(self) -> Path:
        p = Path(self.storage_local_dir)
        return p if p.is_absolute() else (BACKEND_ROOT / p).resolve()

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache — used by tests that patch the environment."""
    get_settings.cache_clear()
    return get_settings()
