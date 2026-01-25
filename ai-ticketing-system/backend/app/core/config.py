# backend/app/core/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./tickets.db"
    secret_key: str = "TDwXmO7vcIeybQPYU8UNXYLtIGdqeP-yxcQKRTreR4WIzfIqwFW2z_WOkjSfUQP2"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
