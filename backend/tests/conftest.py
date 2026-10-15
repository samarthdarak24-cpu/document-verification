"""Shared pytest fixtures for the DocuTrace backend test suite.

Isolation strategy
------------------
The application reads its database URL from :class:`app.core.config.Settings`,
which is memoised by ``functools.lru_cache``. To get a *pristine* database per
test session we therefore:

1. Point ``DATABASE_URL`` (and the storage directories) at a throwaway
   directory under the OS temp folder **before** the settings object is first
   built, and
2. Clear the settings cache so the first ``get_settings()`` call picks the
   overrides up.

A *file-based* SQLite database is used rather than ``:memory:`` because the
pipeline and the FastAPI thread-pool both open connections; a file lets every
connection share one database without relying on ``StaticPool`` semantics, and
it lets a test inspect the database directly if it needs to.

Every test gets a fresh schema (``drop_all`` + ``create_all``) via the
``client`` fixture, so tests never see each other's rows.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


# --------------------------------------------------------------------------- #
# Environment overrides must happen before app.core.config is imported.
# --------------------------------------------------------------------------- #
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="docutrace-tests-"))
_DB_PATH = _TMP_ROOT / "test.db"
_UPLOAD_DIR = _TMP_ROOT / "uploads"
_REPORT_DIR = _TMP_ROOT / "reports"

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["UPLOAD_DIR"] = str(_UPLOAD_DIR)
os.environ["REPORT_DIR"] = str(_REPORT_DIR)
os.environ["DEBUG"] = "false"
os.environ["OCR_ENABLED"] = "false"
# Deterministic DP so tests never trip the token cap.
os.environ["DP_MAX_TOKENS"] = "20000"

for _d in (_UPLOAD_DIR, _REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the throwaway tree once the whole suite has finished."""
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _configured_settings():
    """Force the settings cache to be rebuilt against the temp environment."""
    from app.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = get_settings()
    assert "docutrace-tests-" in settings.DATABASE_URL
    yield settings


@pytest.fixture()
def db_schema(_configured_settings) -> Iterator[None]:
    """Give each test a brand-new schema on the shared temp database."""
    from app.database.session import init_db, reset_engine_for_tests

    reset_engine_for_tests()
    init_db(drop_first=True)
    yield
    # Rows survive only for the duration of the test; the next test drops all.


@pytest.fixture()
def client(db_schema) -> Iterator["TestClient"]:  # noqa: F821
    """A FastAPI :class:`TestClient` bound to the isolated database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(db_schema):
    """A raw ORM session against the isolated database."""
    from app.database.session import get_session_factory

    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    """Directory holding the six synthetic certificate samples (if generated)."""
    return Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture()
def tmp_pdf(tmp_path: Path):
    """Factory building throwaway PDFs from a title + list of text lines."""

    def _make(name: str, title: str, lines: list[str]) -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        path = tmp_path / name
        c = canvas.Canvas(str(path), pagesize=A4)
        _width, height = A4
        y = height - 72
        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, y, title)
        y -= 32
        c.setFont("Helvetica", 11)
        for line in lines:
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 11)
            c.drawString(72, y, line)
            y -= 16
        c.showPage()
        c.save()
        return path

    return _make
