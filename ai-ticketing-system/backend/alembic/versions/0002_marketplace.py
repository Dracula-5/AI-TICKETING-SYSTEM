"""marketplace: vendors, products, product_images

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("shop_name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("shop_address", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("rating_avg", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_vendors_user_id", "vendors", ["user_id"], unique=True)
    op.create_index("ix_vendors_tenant_id", "vendors", ["tenant_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), server_default="INR"),
        sa.Column("stock_quantity", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(), server_default="active"),
        sa.Column("views_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index("ix_products_vendor_id", "products", ["vendor_id"])
    op.create_index("ix_products_title", "products", ["title"])
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_images")
    op.drop_table("products")
    op.drop_table("vendors")
