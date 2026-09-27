"""Database engine/session setup with MySQL primary and SQLite fallback.

The app prefers MySQL. If the MySQL server is unreachable at startup (common
on a laptop where MySQL isn't installed/configured), it transparently falls
back to SQLite so the demo still runs -- and records which backend it chose
so `/health` can report it honestly.
"""

import logging
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DatabaseState:
    """Holds the resolved engine + which backend actually got used."""

    def __init__(self) -> None:
        self.engine: Engine | None = None
        self.url: str = ""
        self.backend: str = "uninitialized"
        self.fallback_reason: str | None = None


db_state = DatabaseState()


def _make_engine(url: str) -> Engine:
    # Render and Heroku provide PostgreSQL URLs starting with postgres://, which SQLAlchemy 1.4+ requires as postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


def _try_connect(engine: Engine) -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _ensure_mysql_database(url: str) -> None:
    """CREATE DATABASE IF NOT EXISTS, so a fresh MySQL server works out of the box."""
    from sqlalchemy import text

    server_url, _, _ = url.rpartition(f"/{settings.MYSQL_DATABASE}")
    server_url = f"{server_url}/"
    tmp_engine = create_engine(server_url, future=True, connect_args={"connect_timeout": 2})
    try:
        with tmp_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        tmp_engine.dispose()


def init_engine() -> Engine:
    """Resolve the database engine once, with MySQL -> SQLite fallback."""
    if db_state.engine is not None:
        return db_state.engine

    explicit_url = settings.DATABASE_URL.strip()
    if explicit_url:
        engine = _make_engine(explicit_url)
        try:
            _try_connect(engine)
        except SQLAlchemyError as exc:
            if not settings.DB_ALLOW_SQLITE_FALLBACK or explicit_url.startswith("sqlite"):
                raise
            logger.warning("DATABASE_URL unreachable (%s); falling back to SQLite.", exc)
            engine.dispose()
            engine = _make_engine(settings.sqlite_url)
            _try_connect(engine)
            db_state.backend = "sqlite"
            db_state.fallback_reason = f"DATABASE_URL unreachable: {type(exc).__name__}"
            db_state.url = settings.sqlite_url
            db_state.engine = engine
            return engine
        if "postgres" in explicit_url:
            db_state.backend = "postgresql"
        elif explicit_url.startswith("sqlite"):
            db_state.backend = "sqlite"
        else:
            db_state.backend = "mysql"
        db_state.url = explicit_url
        db_state.engine = engine
        return engine

    # In production without an external database configured, use SQLite directly
    if settings.is_production and settings.MYSQL_HOST in ("localhost", "127.0.0.1"):
        engine = _make_engine(settings.sqlite_url)
        _try_connect(engine)
        db_state.backend = "sqlite"
        db_state.fallback_reason = "SQLite used in single-server production"
        db_state.url = settings.sqlite_url
        db_state.engine = engine
        return engine

    # No explicit URL: try MySQL from parts, then fall back.
    mysql_url = settings.mysql_url
    try:
        _ensure_mysql_database(mysql_url)
        engine = _make_engine(mysql_url)
        _try_connect(engine)
        db_state.backend = "mysql"
        db_state.url = mysql_url
        db_state.engine = engine
        logger.info("Connected to MySQL at %s:%s", settings.MYSQL_HOST, settings.MYSQL_PORT)
        return engine
    except Exception as exc:  # noqa: BLE001 - any driver/connection problem triggers fallback
        if not settings.DB_ALLOW_SQLITE_FALLBACK:
            raise
        logger.warning(
            "MySQL unavailable (%s: %s); falling back to SQLite at %s.",
            type(exc).__name__,
            exc,
            settings.SQLITE_PATH,
        )
        engine = _make_engine(settings.sqlite_url)
        _try_connect(engine)
        db_state.backend = "sqlite"
        db_state.fallback_reason = f"MySQL unavailable: {type(exc).__name__}"
        db_state.url = settings.sqlite_url
        db_state.engine = engine
        return engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, future=True)


def create_all() -> None:
    """Create tables directly (used for tests/dev; Alembic owns real migrations)."""
    from app import models  # noqa: F401 - ensures every model is registered

    engine = init_engine()
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    engine = init_engine()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_scope() -> Session:
    """Standalone session for background tasks / scripts (caller must close)."""
    engine = init_engine()
    SessionLocal.configure(bind=engine)
    return SessionLocal()
