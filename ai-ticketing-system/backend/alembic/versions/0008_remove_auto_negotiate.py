"""remove the auto-negotiate AI engine: drop products.floor_price and products.auto_negotiate_enabled

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("products", "auto_negotiate_enabled")
    op.drop_column("products", "floor_price")


def downgrade() -> None:
    op.add_column("products", sa.Column("floor_price", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("auto_negotiate_enabled", sa.Boolean(), server_default=sa.false()))
