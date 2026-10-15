"""DocuTrace FastAPI application.

Mounts every router under ``/api``, initialises the database on startup (creating
tables and seeding the default settings/templates) and exposes a health probe.

Run locally with::

    uvicorn app.main:app --reload --port 8000

The app is a local academic prototype: there is no authentication and CORS is
restricted to the local Vite dev server. Uploaded files never leave the machine.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Load ``backend/.env`` so local configuration (e.g. ``TESSERACT_CMD``) is present
# in the process environment *before* the first ``get_settings()`` call. This is
# what lets the app find the Tesseract binary even when it is not on the shell
# PATH — without it, ``TESSERACT_CMD`` stays empty and OCR silently degrades.
from dotenv import load_dotenv

# This file is ``backend/app/main.py``; the project ``.env`` lives one level up in
# ``backend/.env`` (the directory uvicorn is launched from). Load it explicitly so
# we never depend on the current working directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routers import (
    algorithms,
    analytics,
    benchmarks,
    changes,
    compare,
    documents,
    duplicates,
    reports,
    settings as settings_router,
    templates,
    verification,
)
from app.core.config import get_settings
from app.database.session import init_db, session_scope
from app.schemas import HealthResponse
from app.services import ServiceError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("docutrace")

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, storage directories and seed default data on startup."""
    settings = get_settings()
    settings.ensure_directories()
    init_db()

    # Seed default settings and the built-in templates (idempotent: existing
    # rows are never overwritten, so a user's edits survive a restart).
    try:
        from app.models import seed_defaults

        with session_scope() as session:
            seeded = seed_defaults(session)
        logger.info(
            "Seeded %s setting(s) and %s template(s).",
            seeded.get("settings", 0),
            seeded.get("templates", 0),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Seeding default data failed: %s", exc)

    logger.info("DocuTrace %s ready (db=%s)", settings.VERSION, settings.RAW_DATABASE_URL)

    # Surface OCR availability once at boot rather than per request.
    try:
        from app.services.extraction import ocr_available

        if not ocr_available():
            logger.warning(
                "Tesseract OCR is not installed: scanned PDFs and images will be "
                "reported as unreadable instead of being OCR'd. See README."
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not probe OCR availability: %s", exc)

    yield


app = FastAPI(
    title="DocuTrace API",
    description=(
        "Intelligent document verification and similarity detection. "
        "Every verification result is produced by deterministic algorithms whose "
        "measurements are recorded and exposed."
    ),
    version=get_settings().VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    """Turn expected service failures into 400s with safe messages."""
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "code": exc.code},
    )


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
def health():
    """Liveness probe with version, database and OCR capability reporting."""
    settings = get_settings()
    try:
        from app.services.extraction import ocr_available

        # Probe only for the side effect of logging availability; the value
        # itself is recomputed per request by the health endpoint.
        ocr_available()
    except Exception:  # pragma: no cover - defensive
        pass
    database = "ok"
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        database = "unavailable"
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        app=settings.APP_NAME,
        database=database,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": "DocuTrace API",
        "version": get_settings().VERSION,
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }


app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(verification.router, prefix=API_PREFIX)
app.include_router(compare.router, prefix=API_PREFIX)
app.include_router(changes.router, prefix=API_PREFIX)
app.include_router(duplicates.router, prefix=API_PREFIX)
app.include_router(templates.router, prefix=API_PREFIX)
app.include_router(algorithms.router, prefix=API_PREFIX)
app.include_router(benchmarks.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)


__all__ = ["app"]
