"""vendor category lock: one vendor per marketplace category per tenant

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("category", sa.String(), nullable=True))
    op.create_index("ux_vendors_tenant_category", "vendors", ["tenant_id", "category"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_vendors_tenant_category", table_name="vendors")
    op.drop_column("vendors", "category")
