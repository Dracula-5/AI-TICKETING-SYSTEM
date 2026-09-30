"""The Alembic chain must build exactly the schema the ORM models describe —
otherwise production (migrated) and tests (create_all) silently diverge."""

import os
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db.database import Base, EmbeddingVector

BACKEND = Path(__file__).resolve().parents[1]


PG_ONLY_INDEXES = {
    "ix_ticket_embeddings_hnsw",
    "ix_kb_chunks_hnsw",
    "ix_kb_chunks_tsv",
    "ix_tickets_title_trgm",
    "ix_tickets_description_trgm",
}


def _include(obj, name, type_, reflected, compare_to):
    # Vector (HNSW) and full-text (GIN over a generated tsvector column) objects
    # are PostgreSQL-only and live in migrations 0003/0005, not in the models.
    if type_ == "index" and name in PG_ONLY_INDEXES:
        return False
    return not (type_ == "column" and name == "tsv")


def _compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    # EmbeddingVector is pgvector `vector(n)` on PostgreSQL and JSON elsewhere by
    # design (migration 0003); every other column gets Alembic's default check.
    if isinstance(metadata_column.type, EmbeddingVector):
        return False
    return None


def test_upgrade_head_matches_models(tmp_path):
    url = os.environ.get("TEST_MIGRATIONS_DATABASE_URL") or f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": _compare_type, "include_object": _include})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == [], diff
