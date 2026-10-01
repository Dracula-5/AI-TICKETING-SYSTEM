from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Anything shorter than this, or equal to the development default, is refused
# when ENVIRONMENT=production (see validate_for_environment).
_DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-before-deploying"  # noqa: S105 -- refused in production
_MIN_PROD_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NexaDesk AI"
    environment: Literal["development", "test", "staging", "production"] = "development"

    database_url: str = "sqlite:///./nexadesk.db"
    # Per API/worker process. Keep processes × (size + overflow) below PostgreSQL's max_connections.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 10
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = _DEV_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    email_token_expire_hours: int = 24
    # bcrypt work factor. Tests lower it; never below 12 in deployed environments.
    bcrypt_rounds: int = 12
    password_reset_expire_minutes: int = 30
    invitation_expire_days: int = 7

    # Comma/semicolon separated. Only needed when the SPA is served from a
    # different origin than the API (local dev); production serves both
    # behind one reverse proxy.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_base_url: str = "http://localhost:5173"
    cookie_secure: bool = False

    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "NexaDesk AI <no-reply@nexadesk.local>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Attachment storage: "local" (a directory / mounted volume) or "s3"
    # (any S3-compatible object store: AWS S3, Cloudflare R2, MinIO, ...).
    storage_backend: Literal["local", "s3"] = "local"
    attachment_dir: str = "./var/attachments"
    attachment_max_bytes: int = 10 * 1024 * 1024
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # inline: the API process runs the SLA sweep and delivers email itself
    #         (single-process development).
    # worker: a separate `python -m app.worker` process does both; required
    #         whenever the API runs more than one process.
    background_mode: Literal["inline", "worker"] = "inline"
    sla_sweep_enabled: bool = True
    sla_sweep_interval_seconds: int = 60
    email_poll_interval_seconds: int = 5

    rate_limit_default: str = "300/minute"
    # "memory://" is per process; use redis:// whenever there is more than one.
    rate_limit_storage_uri: str = "memory://"

    # AI. EMBEDDING_MODEL is chosen from the P4 benchmarks; "test-hashing" is a
    # deterministic offline stand-in used only by the test suite.
    ai_enabled: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_cache_dir: str = ""
    job_poll_interval_seconds: int = 2
    # Run queued jobs inside the API process when BACKGROUND_MODE=inline. The
    # test suite turns this off and drives jobs explicitly.
    job_runner_enabled: bool = True
    # Bearer token Prometheus must present on /metrics (required when deployed).
    metrics_token: str = ""
    # Dashboard aggregates cache (seconds; 0 = off). See routers/analytics.py.
    analytics_cache_seconds: int = 30
    # Prometheus metrics port of the worker process (0 = off).
    worker_metrics_port: int = 9101

    # Generative features (summaries, reply drafts). Off unless both a provider
    # and a key are set explicitly — see app/ai/llm.py. Prices are USD per
    # million tokens from the provider's price list; unset = cost not recorded.
    # Knowledge-base cross-encoder reranker (FastEmbed name, or "none").
    kb_rerank_model: str = "none"
    kb_max_upload_bytes: int = 20 * 1024 * 1024

    llm_provider: Literal["none", "anthropic", "openai"] = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_price_input_per_mtok: float | None = None
    llm_price_output_per_mtok: float | None = None

    # Error monitoring (Sentry-compatible DSN). Disabled when empty.
    sentry_dsn: str = ""
    release: str = "dev"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, url: str) -> str:
        # Hosted databases (Neon, Render, Heroku-style) hand out postgres:// or
        # postgresql:// URLs, which SQLAlchemy maps to psycopg2; the image ships psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def is_production(self) -> bool:
        return self.environment in ("production", "staging")

    @property
    def cors_origin_list(self) -> list[str]:
        parts = [p.strip().rstrip("/") for p in self.cors_origins.replace(";", ",").split(",")]
        return [p for p in parts if p]

    def validate_for_environment(self) -> None:
        """Refuse to boot a deployed environment with development-grade secrets."""
        if not self.is_production:
            return
        problems = []
        if self.secret_key == _DEV_SECRET_KEY or len(self.secret_key) < _MIN_PROD_SECRET_LENGTH:
            problems.append(
                f"SECRET_KEY must be set to a random value of at least {_MIN_PROD_SECRET_LENGTH} characters"
            )
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if self.bcrypt_rounds < 12:
            problems.append("BCRYPT_ROUNDS must be at least 12")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point at PostgreSQL")
        if len(self.metrics_token) < 24:
            problems.append("METRICS_TOKEN must be set (at least 24 characters) so /metrics is not public")
        if self.ai_enabled and self.embedding_model == "test-hashing":
            problems.append("EMBEDDING_MODEL=test-hashing is a test stand-in; use a real embedding model")
        if problems:
            raise RuntimeError(f"Unsafe configuration for {self.environment}: {'; '.join(problems)}")


settings = Settings()

# Normalize relative SQLite paths to the backend directory so running from
# different working directories uses the same DB file.
if settings.database_url.startswith("sqlite:///./"):
    relative_path = settings.database_url.replace("sqlite:///./", "", 1)
    settings.database_url = f"sqlite:///{(BACKEND_DIR / relative_path).resolve().as_posix()}"

if settings.attachment_dir.startswith("./"):
    settings.attachment_dir = str((BACKEND_DIR / settings.attachment_dir[2:]).resolve())
