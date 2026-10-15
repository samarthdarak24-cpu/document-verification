"""Engine / session plumbing.

Highlights
----------
* **SQLite** is used for the reference deployment (zero-setup, single file), so
  the engine is created with ``check_same_thread=False``: FastAPI serves requests
  from a thread-pool, and without that flag SQLite raises
  ``ProgrammingError: SQLite objects created in a thread can only be used in that
  same thread`` the first time a request touches the session in a worker thread.
* **In-memory** SQLite (``sqlite://``) additionally gets a ``StaticPool`` so that
  every session/connection sees the *same* underlying database — otherwise each
  new connection would get a fresh, empty schema.
* The parent directory of an on-disk SQLite file is created eagerly: a missing
  directory is the most common cause of ``unable to open database file``.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.base import Base

#: Replaced by :func:`_configure_engine` on first use.
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _is_memory_sqlite(url: str) -> bool:
    return url in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in url


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Create the directory that will hold an on-disk SQLite database."""
    try:
        parsed = make_url(url)
    except Exception:  # pragma: no cover - defensive
        return
    if not parsed.drivername.startswith("sqlite") or _is_memory_sqlite(url):
        return
    database = parsed.database
    if not database or database == ":memory:":
        return
    parent = Path(database).expanduser().resolve().parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - read-only filesystem etc.
        pass


def _configure_engine() -> Engine:
    settings = get_settings()
    url = settings.DATABASE_URL
    echo = settings.DATABASE_ECHO

    if url.startswith("sqlite"):
        _ensure_sqlite_parent_dir(url)
        connect_args = {"check_same_thread": False}
        if _is_memory_sqlite(url):
            engine = create_engine(
                url,
                echo=echo,
                connect_args=connect_args,
                poolclass=StaticPool,
                future=True,
            )
        else:
            engine = create_engine(
                url,
                echo=echo,
                connect_args=connect_args,
                future=True,
            )
        # Enforce foreign keys on every connection (SQLite defaults them OFF,
        # which would silently orphan ``extracted_fields`` rows on delete).
        _install_sqlite_pragmas(engine)
        return engine

    return create_engine(url, echo=echo, pool_pre_ping=True, future=True)


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_engine() -> Engine:
    """Return the process-wide engine (created lazily on first call)."""
    global _engine
    if _engine is None:
        _engine = _configure_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory (created lazily)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            class_=Session,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionFactory


def reset_engine_for_tests() -> None:
    """Drop the memoised engine/session factory (test-suite only)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped :class:`Session`."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for code that needs a session outside a request."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_session() -> Iterator[Session]:
    """Alias of :func:`session_scope` for readability at call sites."""
    with session_scope() as session:
        yield session


def init_db(drop_first: bool = False) -> None:
    """Create every ORM table.

    Importing ``app.models.models`` registers all mappers on ``Base.metadata``
    before ``create_all`` runs; the import is local so that ``session`` does not
    depend on the model layer at import time (keeps the dependency graph acyclic
    and avoids circular imports with the routers).
    """
    import app.models.models  # noqa: F401  (registers the mappers)

    engine = get_engine()
    if drop_first:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
