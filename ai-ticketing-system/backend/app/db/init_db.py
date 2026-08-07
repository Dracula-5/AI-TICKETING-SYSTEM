import logging

from sqlalchemy import text
from app.db.database import engine, SessionLocal
from app.db import models
from app.services.seed_users import create_default_users

logger = logging.getLogger(__name__)

def _ensure_ticket_columns():
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(tickets)")).mappings().all()
        existing = {r["name"] for r in rows}

        # Add missing columns for older SQLite files.
        if "updated_at" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN updated_at DATETIME"))
        if "category" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN category VARCHAR"))
        if "sla_due" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN sla_due DATETIME"))
        if "is_escalated" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN is_escalated BOOLEAN DEFAULT 0"))
        if "pricing_status" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN pricing_status VARCHAR DEFAULT 'pending'"))
        if "final_price" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN final_price FLOAT"))
        if "price_finalized_at" not in existing:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN price_finalized_at DATETIME"))


def _ensure_vendor_columns():
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(vendors)")).mappings().all()
        existing = {r["name"] for r in rows}

        # Add missing columns for older SQLite files.
        if "category" not in existing:
            conn.execute(text("ALTER TABLE vendors ADD COLUMN category VARCHAR"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_vendors_tenant_category "
            "ON vendors (tenant_id, category)"
        ))

def init_db():
    models.Base.metadata.create_all(bind=engine)
    _ensure_ticket_columns()
    _ensure_vendor_columns()
    db = SessionLocal()
    try:
        create_default_users(db)
    except Exception:
        logger.exception("Error seeding users")
    finally:
        db.close()
