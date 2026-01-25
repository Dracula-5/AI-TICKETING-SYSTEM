from app.db.database import engine
from app.db import models

def init_db():
    models.Base.metadata.create_all(bind=engine)
