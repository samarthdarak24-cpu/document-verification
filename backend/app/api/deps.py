"""FastAPI dependencies and shared helpers for all API routers."""

from __future__ import annotations

from typing import Generator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import session_scope

__all__ = ["get_db", "not_found", "bad_request", "ServerTiming"]


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session.

    Delegates to :func:`app.database.session.session_scope`, which commits on
    success, rolls back on any exception and always closes the session.
    """
    with session_scope() as session:
        yield session


def not_found(resource: str, identifier: str) -> HTTPException:
    """Build a 404 with a stable, non-leaking message."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' was not found.",
    )


def bad_request(message: str) -> HTTPException:
    """Build a 400 with the caller's message."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class ServerTiming:
    """Tiny context manager that records elapsed milliseconds."""

    def __init__(self) -> None:
        import time

        self._time = time
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ServerTiming":
        self._start = self._time.perf_counter()
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed_ms = (self._time.perf_counter() - self._start) * 1000.0
