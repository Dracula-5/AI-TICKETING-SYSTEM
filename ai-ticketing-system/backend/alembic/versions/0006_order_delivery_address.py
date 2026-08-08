"""order delivery address

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_address", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "delivery_address")
