"""bargaining: negotiation sessions/messages, orders, product negotiation config

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("floor_price", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("auto_negotiate_enabled", sa.Boolean(), server_default=sa.false()))

    op.create_table(
        "negotiation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("status", sa.String(), server_default="open"),
        sa.Column("current_offer_price", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_negotiation_sessions_tenant_id", "negotiation_sessions", ["tenant_id"])
    op.create_index("ix_negotiation_sessions_product_id", "negotiation_sessions", ["product_id"])
    op.create_index("ix_negotiation_sessions_customer_id", "negotiation_sessions", ["customer_id"])
    op.create_index("ix_negotiation_sessions_vendor_id", "negotiation_sessions", ["vendor_id"])

    op.create_table(
        "negotiation_messages",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("negotiation_sessions.id"), nullable=False),
        sa.Column("sender_role", sa.String(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("message_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_negotiation_messages_session_id", "negotiation_messages", ["session_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("negotiation_session_id", sa.Integer(), sa.ForeignKey("negotiation_sessions.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default="1"),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("total_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])
    op.create_index("ix_orders_product_id", "orders", ["product_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_vendor_id", "orders", ["vendor_id"])


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("negotiation_messages")
    op.drop_table("negotiation_sessions")
    op.drop_column("products", "auto_negotiate_enabled")
    op.drop_column("products", "floor_price")
