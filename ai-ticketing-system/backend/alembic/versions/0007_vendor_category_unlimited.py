"""remove one-vendor-per-category cap: any number of vendors may share a category

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ux_vendors_tenant_category", table_name="vendors")
    op.create_index("ix_vendors_category", "vendors", ["category"])


def downgrade() -> None:
    op.drop_index("ix_vendors_category", table_name="vendors")
    op.create_index("ux_vendors_tenant_category", "vendors", ["tenant_id", "category"], unique=True)
