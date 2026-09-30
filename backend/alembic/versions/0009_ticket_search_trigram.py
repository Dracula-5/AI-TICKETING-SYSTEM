"""Trigram indexes for ticket search (P11, PostgreSQL only).

Ticket search filters with lower(title|description) LIKE '%term%', which scans
every row of the organization. pg_trgm GIN indexes on the same expressions let
PostgreSQL answer it from the index (terms of 3+ characters). Measured before/
after in reports/scale/ and reports/load/.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

INDEXES = {
    "ix_tickets_title_trgm": "lower(title) gin_trgm_ops",
    "ix_tickets_description_trgm": "lower(description) gin_trgm_ops",
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, expr in INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON tickets USING gin ({expr})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
