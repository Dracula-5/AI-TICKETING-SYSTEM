"""notifications, provider category preferences

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "provider_categories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
    )
    op.create_index("ix_provider_categories_user_id", "provider_categories", ["user_id"])


def downgrade() -> None:
    op.drop_table("provider_categories")
    op.drop_table("notifications")
