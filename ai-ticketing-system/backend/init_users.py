#!/usr/bin/env python
from sqlalchemy.orm import Session
from app.db.database import SessionLocal, engine
from app.db import models
from app.services.seed_users import create_default_users

# Create all tables
models.Base.metadata.create_all(bind=engine)

# Seed default users
db = SessionLocal()
try:
    created = create_default_users(db)
    print(f"✓ Database initialized. {created} default users created.")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
