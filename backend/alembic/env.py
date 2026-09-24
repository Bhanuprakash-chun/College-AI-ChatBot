"""Alembic environment.

The database URL comes from the application settings rather than alembic.ini,
so migrations always target the same database the app is configured for --
including the SQLite fallback when MySQL is unavailable.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.database.session import Base  # noqa: E402
from app import models  # noqa: F401,E402  - registers every table on Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    if settings.DATABASE_URL.strip():
        return settings.DATABASE_URL.strip()

    # With fallback disabled (e.g. in Docker), target MySQL and let an outage
    # fail loudly rather than silently migrating a local SQLite file.
    if not settings.DB_ALLOW_SQLITE_FALLBACK:
        return settings.mysql_url

    # Probe MySQL; fall back to SQLite exactly as the app does.
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.mysql_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return settings.mysql_url
    except Exception:  # noqa: BLE001
        return settings.sqlite_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # required for SQLite ALTER support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
