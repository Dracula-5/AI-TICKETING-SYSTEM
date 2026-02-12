# backend/app/core/config.py

from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./tickets.db"
    secret_key: str = "TDwXmO7vcIeybQPYU8UNXYLtIGdqeP-yxcQKRTreR4WIzfIqwFW2z_WOkjSfUQP2"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 30
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()

# Normalize relative SQLite paths to the backend directory so running from
# different working directories uses the same DB file.
if settings.database_url.startswith("sqlite:///./"):
    relative_path = settings.database_url.replace("sqlite:///./", "", 1)
    backend_dir = Path(__file__).resolve().parents[2]
    db_path = (backend_dir / relative_path).resolve()
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
