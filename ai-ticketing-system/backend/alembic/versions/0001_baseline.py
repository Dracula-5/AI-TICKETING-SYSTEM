"""baseline schema (tenants, users, tickets, comments, providers, price_negotiations)

Revision ID: 0001
Revises:
Create Date: 2026-08-07

Reflects the schema as it existed before Alembic was introduced into this
project. Applying this migration against a fresh database reproduces exactly
what `Base.metadata.create_all()` already produces, so it is safe to run
against both brand-new databases and (via `alembic stamp head`) existing
ones that were created the old way.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=True),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=True)
    op.create_index("ix_tenants_domain", "tenants", ["domain"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="open"),
        sa.Column("pricing_status", sa.String(), server_default="pending"),
        sa.Column("final_price", sa.Float(), nullable=True),
        sa.Column("price_finalized_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sla_due", sa.DateTime(), nullable=True),
        sa.Column("is_escalated", sa.Boolean(), server_default=sa.false()),
    )

    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=True),
    )

    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("contact", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
    )

    op.create_table(
        "price_negotiations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender_role", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("is_final", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_price_negotiations_ticket_id", "price_negotiations", ["ticket_id"])
    op.create_index("ix_price_negotiations_sender_user_id", "price_negotiations", ["sender_user_id"])


def downgrade() -> None:
    op.drop_table("price_negotiations")
    op.drop_table("providers")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_tenants_domain", table_name="tenants")
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
