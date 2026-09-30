from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on both PostgreSQL and SQLite.

    PostgreSQL stores `timestamptz`; SQLite has no timezone support, so values
    are stored as naive UTC and re-tagged as UTC on the way out. Application
    code therefore only ever sees aware UTC datetimes, whichever DB is in use.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def build_engine(url: str):
    if url.startswith("sqlite"):
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        sqlite_engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            # One shared connection, so every session sees the same in-memory DB.
            poolclass=StaticPool if in_memory else None,
            future=True,
        )

        @event.listens_for(sqlite_engine, "connect")
        def _enforce_foreign_keys(dbapi_connection, _record):
            # SQLite ignores FOREIGN KEY / ON DELETE unless asked; PostgreSQL
            # always enforces them, so tests must too.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return sqlite_engine
    return create_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        # All date bucketing in analytics assumes the session runs in UTC.
        connect_args={"options": "-c timezone=utc"},
        future=True,
    )


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
