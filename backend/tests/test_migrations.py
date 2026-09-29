"""The Alembic chain must build exactly the schema the ORM models describe —
otherwise production (migrated) and tests (create_all) silently diverge."""

import os
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db.database import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_upgrade_head_matches_models(tmp_path):
    url = os.environ.get("TEST_MIGRATIONS_DATABASE_URL") or f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == [], diff
