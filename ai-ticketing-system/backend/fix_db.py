from app.db.database import engine

# This connects to your existing database
with engine.connect() as conn:
    conn.exec_driver_sql("DROP TABLE IF EXISTS tickets;")
    print("Tickets table dropped successfully")
