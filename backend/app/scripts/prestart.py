"""
Start-up tasks of the API container, in one Python process.

    python -m app.scripts.prestart

* MIGRATE_ON_START=true (default): `alembic upgrade head`.
* SEED_DEMO_ON_START=true and DEMO_PASSWORD set: create the demo organizations
  if missing or seeded by an older version (idempotent). Without DEMO_PASSWORD
  it is skipped, so no generated password ends up in platform logs.
* PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD set: create the platform
  administrator, or give the existing one that password.

One process instead of separate `alembic` and seed commands: each fresh Python
start re-imports SQLAlchemy and the models, which on a 0.1-CPU host (Render
free tier) costs about a minute per process.
"""

import os
import sys
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

    if _flag("SEED_DEMO_ON_START", "false"):
        if os.environ.get("DEMO_PASSWORD"):
            from app.scripts import seed_demo

            print("Seeding demo organizations (if missing or outdated)...", flush=True)
            try:
                seed_demo.run()
            except Exception:  # demo content must never keep the API from starting
                import traceback

                traceback.print_exc()
                print("Demo seed failed; starting without (re)seeding.", file=sys.stderr)
        else:
            print("SEED_DEMO_ON_START=true but DEMO_PASSWORD is empty; skipping demo seed.", file=sys.stderr)

    if os.environ.get("PLATFORM_ADMIN_EMAIL") and os.environ.get("PLATFORM_ADMIN_PASSWORD"):
        from app.scripts import platform_admin

        platform_admin.run()


if __name__ == "__main__":
    main()
