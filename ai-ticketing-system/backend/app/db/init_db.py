from app.db.database import engine, SessionLocal
from app.db import models
from app.services.seed_users import create_default_users

def init_db():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        create_default_users(db)
    except Exception as e:
        print(f"Error seeding users: {e}")
    finally:
        db.close()
