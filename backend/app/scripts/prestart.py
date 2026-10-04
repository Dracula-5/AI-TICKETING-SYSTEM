"""
Start-up tasks of the API container, in one Python process.

    python -m app.scripts.prestart

* MIGRATE_ON_START=true (default): `alembic upgrade head`.
* PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD set: create the platform
  administrator, or give the existing one that password.

One process for both: each fresh Python start re-imports SQLAlchemy and the
models, which on a 0.1-CPU host (Render free tier) costs about a minute. Demo
data (SEED_DEMO_ON_START) is not seeded here but by the API in the background
after it has started (app/main.py), so a deploy never waits for it.
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


def main() -> None:
    if _flag("MIGRATE_ON_START", "true"):
        from alembic.config import Config

        from alembic import command

        print("Running database migrations...", flush=True)
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    if os.environ.get("PLATFORM_ADMIN_EMAIL") and os.environ.get("PLATFORM_ADMIN_PASSWORD"):
        from app.scripts import platform_admin

        platform_admin.run()


if __name__ == "__main__":
    main()
