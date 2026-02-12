from sqlalchemy import text
from app.db.database import engine, SessionLocal
from app.db import models
from app.services.seed_users import create_default_users

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

def init_db():
    models.Base.metadata.create_all(bind=engine)
    _ensure_ticket_columns()
    db = SessionLocal()
    try:
        create_default_users(db)
    except Exception as e:
        print(f"Error seeding users: {e}")
    finally:
        db.close()
