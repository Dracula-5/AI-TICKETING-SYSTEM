from datetime import datetime, timezone

import anyio
from sqlalchemy import JSON, DateTime, create_engine, event
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


EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 / bge-small-en-v1.5


class EmbeddingVector(TypeDecorator):
    """pgvector `vector(n)` on PostgreSQL; a JSON array elsewhere (SQLite test
    tier, where similarity search falls back to NumPy). Values in and out are
    float lists / numpy arrays."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]


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
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # Fail fast when saturated instead of holding a request thread for 30 s.
        pool_timeout=settings.db_pool_timeout,
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


# Session teardown runs on its own small thread limiter. With a sync `yield`
# dependency FastAPI closes the session on the shared request threadpool; under
# load every thread can be busy waiting for a pool connection while the
# connections are held by finished requests waiting for a thread to close them —
# a deadlock (P10: 30 connections "idle in transaction", /health hung).
_teardown_limiter: anyio.CapacityLimiter | None = None


def _limiter() -> anyio.CapacityLimiter:
    global _teardown_limiter
    if _teardown_limiter is None:
        _teardown_limiter = anyio.CapacityLimiter(8)
    return _teardown_limiter


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        await anyio.to_thread.run_sync(db.close, limiter=_limiter())
