from pathlib import Path
from typing import Literal

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

    attachment_dir: str = "./var/attachments"
    attachment_max_bytes: int = 10 * 1024 * 1024

    sla_sweep_enabled: bool = True
    sla_sweep_interval_seconds: int = 60

    rate_limit_default: str = "300/minute"

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
