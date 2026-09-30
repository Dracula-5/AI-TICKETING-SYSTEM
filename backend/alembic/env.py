import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Make "app" importable when alembic is invoked from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db import models  # noqa: E402, F401 -- registers all model classes on Base
from app.db.database import Base, EmbeddingVector, UTCDateTime  # noqa: E402

config = context.config

# Always migrate the same database the app itself is configured to use.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Arbitrary constant identifying "NexaDesk schema migration" in pg_advisory_lock.
MIGRATION_LOCK_KEY = 7_424_150_301


def render_item(type_, obj, autogen_context):
    """Render app-specific column types as portable SQLAlchemy types so
    migration files never import application code."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    if type_ == "type" and isinstance(obj, EmbeddingVector):
        # Placeholder; migrations that add vector columns pick the dialect type
        # explicitly (pgvector on PostgreSQL, JSON elsewhere).
        return "sa.JSON()"
    if type_ == "type" and obj.__class__.__name__ == "JSON" and getattr(obj, "_variant_mapping", None):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            # Serialize concurrent `alembic upgrade` runs (e.g. two containers
            # starting together): the second waits, then finds nothing to do.
            connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
            connection.commit()
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_item=render_item,
                render_as_batch=connection.dialect.name == "sqlite",
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if postgres:
                connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
                connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
