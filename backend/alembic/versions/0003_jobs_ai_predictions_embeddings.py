"""Background jobs, AI predictions, ticket embeddings (pgvector).

On PostgreSQL: enables the `vector` extension, stores embeddings as vector(384)
and builds an HNSW cosine index. Elsewhere (SQLite test tier) the column is JSON.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 18:00:18.281005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_DIM = 384


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _embedding_type():
    if _is_postgres():
        from pgvector.sqlalchemy import Vector

        return Vector(EMBEDDING_DIM)
    return sa.JSON()


def upgrade() -> None:
    """Upgrade schema."""
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
    sa.Column('dedupe_key', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Double(), nullable=True),
    sa.Column('result', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index('ix_jobs_dedupe_key', ['dedupe_key'], unique=False)
        batch_op.create_index('ix_jobs_status_run_after', ['status', 'run_after'], unique=False)

    op.create_table('ai_predictions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('model_version', sa.String(length=64), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
    sa.Column('confidence', sa.Double(), nullable=True),
    sa.Column('evidence', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('latency_ms', sa.Double(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('final_value', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('decided_by_user_id', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('input_sha256', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_predictions', schema=None) as batch_op:
        batch_op.create_index('ix_ai_predictions_tenant_created', ['tenant_id', 'created_at'], unique=False)
        batch_op.create_index('ix_ai_predictions_ticket_kind', ['ticket_id', 'kind'], unique=False)

    op.create_table('ticket_embeddings',
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('embedding', _embedding_type(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ticket_id')
    )
    with op.batch_alter_table('ticket_embeddings', schema=None) as batch_op:
        batch_op.create_index('ix_ticket_embeddings_tenant', ['tenant_id'], unique=False)
    if _is_postgres():
        op.execute(
            "CREATE INDEX ix_ticket_embeddings_hnsw ON ticket_embeddings "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_ticket_embeddings_hnsw")
    with op.batch_alter_table('ticket_embeddings', schema=None) as batch_op:
        batch_op.drop_index('ix_ticket_embeddings_tenant')

    op.drop_table('ticket_embeddings')
    with op.batch_alter_table('ai_predictions', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_predictions_ticket_kind')
        batch_op.drop_index('ix_ai_predictions_tenant_created')

    op.drop_table('ai_predictions')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_status_run_after')
        batch_op.drop_index('ix_jobs_dedupe_key')

    op.drop_table('jobs')
    # ### end Alembic commands ###
