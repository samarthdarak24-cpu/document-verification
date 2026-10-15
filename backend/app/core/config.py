"""Application configuration.

Every setting is read from an environment variable (12-factor style) with a
sensible default so the project runs out of the box for local development:

===========================  =============================================  ==========================
Variable                     Default                                        Meaning
===========================  =============================================  ==========================
``DATABASE_URL``             ``sqlite:///./backend/docutrace.db``           SQLAlchemy database URL.
``UPLOAD_DIR``               ``backend/storage/documents``                  Stored uploads root.
``REPORT_DIR``               ``backend/storage/reports``                    Generated report root.
``MAX_UPLOAD_MB``            ``25``                                         Upload size limit.
``CORS_ORIGINS``             ``http://localhost:5173,...``                  Comma separated allow-list.
``OCR_ENABLED``              ``true``                                       Master switch for OCR.
``OCR_MIN_CHARS_PER_PAGE``   ``100``                                        Sparse-page OCR threshold.
``TESSERACT_CMD``            *(unset)*                                      Explicit path to the Tesseract binary.
``DP_MAX_TOKENS``            ``2000``                                       LCS/edit-distance cap.
===========================  =============================================  ==========================

Relative paths are documented relative to the *repository root* (the directory
that contains ``backend/``), so they resolve to the same location no matter
which working directory the server or the test-suite is started from.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

#: Semantic API version reported by ``GET /api/health``.
APP_VERSION = "1.0.0"

APP_NAME = "DocuTrace"

#: Repository root = ``<repo>/backend/app/core/config.py`` -> parents[3].
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Directory names that, when they lead a relative path, anchor at REPO_ROOT.
_ANCHORED_SEGMENTS = {"backend", "app", "docs", "frontend", "tests"}


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def resolve_path(raw: str) -> Path:
    """Resolve a configured path to an absolute :class:`~pathlib.Path`.

    Absolute values are returned as-is. Relative values that begin with a
    repository-level segment (``backend/``, ``app/``, ...) are anchored at the
    repository root; anything else is anchored at the current working
    directory. This keeps the documented defaults stable when uvicorn or
    pytest is launched from either the repo root or from ``backend/``.
    """
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] in _ANCHORED_SEGMENTS:
        return REPO_ROOT / path
    return Path.cwd() / path


def _resolve_sqlite_url(url: str) -> str:
    """Rewrite a *relative* sqlite URL into an absolute, portable URL.

    SQLite's URL form is ``sqlite:///relative/path.db`` or
    ``sqlite:////absolute/path.db``. Rewriting to an absolute URL guarantees the
    database file lands next to the project rather than in whatever directory
    the process happened to start in (a common source of "where did my rows
    go?" bugs, and of tests writing into the developer's real database).
    """
    if not url.startswith("sqlite"):
        return url
    # Strip any of the accepted sqlite prefixes.
    for prefix in ("sqlite+pysqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            remainder = url[len(prefix):]
            break
    else:  # pragma: no cover - defensive
        return url

    if not remainder or remainder == ":memory:":
        return "sqlite://"
    if remainder.startswith("file:"):  # already a URI form
        return url

    path = Path(remainder)
    if path.is_absolute():
        # Normalise separators: sqlalchemy accepts forward slashes everywhere.
        return "sqlite:///" + str(path).replace("\\", "/")
    return "sqlite:///" + str(resolve_path(remainder)).replace("\\", "/")


class Settings:
    """Runtime configuration resolved once from the process environment."""

    def __init__(self) -> None:
        # --- Application --------------------------------------------------- #
        self.APP_NAME: str = _env_str("APP_NAME", APP_NAME)
        self.VERSION: str = _env_str("APP_VERSION", APP_VERSION)

        # --- Persistence --------------------------------------------------- #
        self.DATABASE_URL: str = _resolve_sqlite_url(
            _env_str("DATABASE_URL", "sqlite:///./backend/docutrace.db")
        )
        #: Raw (unresolved) value, useful for tests and diagnostics.
        self.RAW_DATABASE_URL: str = _env_str(
            "DATABASE_URL", "sqlite:///./backend/docutrace.db"
        )
        self.DATABASE_ECHO: bool = _env_bool("DATABASE_ECHO", False)

        # --- Storage ------------------------------------------------------- #
        self.UPLOAD_DIR: str = str(
            resolve_path(_env_str("UPLOAD_DIR", "backend/storage/documents"))
        )
        self.REPORT_DIR: str = str(
            resolve_path(_env_str("REPORT_DIR", "backend/storage/reports"))
        )

        # --- Upload limits ------------------------------------------------- #
        self.MAX_UPLOAD_MB: int = _env_int("MAX_UPLOAD_MB", 25)
        #: ``MAX_UPLOAD_MB`` expressed in bytes (the value actually enforced).
        self.MAX_UPLOAD_BYTES: int = self.MAX_UPLOAD_MB * 1024 * 1024

        # --- CORS ---------------------------------------------------------- #
        cors_raw = _env_str(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        self.CORS_ORIGINS: List[str] = [
            origin.strip() for origin in cors_raw.split(",") if origin.strip()
        ]

        # --- OCR ----------------------------------------------------------- #
        self.OCR_ENABLED: bool = _env_bool("OCR_ENABLED", True)
        self.OCR_MIN_CHARS_PER_PAGE: int = _env_int("OCR_MIN_CHARS_PER_PAGE", 100)
        #: Explicit path to the Tesseract binary. Set this when the binary is
        #: not on PATH (a fresh Windows install only adds PATH entries for
        #: *new* shells, so a server started before the install will not see
        #: it). Empty => whatever ``pytesseract`` finds on PATH.
        self.TESSERACT_CMD: str = _env_str("TESSERACT_CMD", "")

        # --- Algorithm bounds ---------------------------------------------- #
        #: Hard cap on the token count fed to the O(n*m) DP algorithms
        #: (LCS / edit distance). Inputs are truncated and the truncation is
        #: reported in the result, never silently ignored.
        self.DP_MAX_TOKENS: int = _env_int("DP_MAX_TOKENS", 2000)

        # --- Extraction ---------------------------------------------------- #
        #: Chars kept in the ``documents.text_excerpt`` preview column.
        self.TEXT_EXCERPT_CHARS: int = _env_int("TEXT_EXCERPT_CHARS", 2000)

    @property
    def storage_root(self) -> Path:
        """Absolute :class:`~pathlib.Path` of the storage directory."""
        return self.upload_root.parent

    @property
    def upload_root(self) -> Path:
        """Absolute :class:`~pathlib.Path` of the document storage root."""
        return Path(self.UPLOAD_DIR)

    @property
    def report_root(self) -> Path:
        """Absolute :class:`~pathlib.Path` of the report storage root."""
        return Path(self.REPORT_DIR)

    def ensure_directories(self) -> None:
        """Create the storage roots if they do not exist yet."""
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.report_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "temp_compare").mkdir(parents=True, exist_ok=True)
        (self.storage_root / "diff_images").mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        """JSON-serialisable snapshot (secrets are not stored here, so all safe)."""
        return {
            "app_name": self.APP_NAME,
            "version": self.VERSION,
            "database_url": self.RAW_DATABASE_URL,
            "upload_dir": self.UPLOAD_DIR,
            "report_dir": self.REPORT_DIR,
            "max_upload_mb": self.MAX_UPLOAD_MB,
            "cors_origins": list(self.CORS_ORIGINS),
            "ocr_enabled": self.OCR_ENABLED,
            "ocr_min_chars_per_page": self.OCR_MIN_CHARS_PER_PAGE,
            "tesseract_cmd": self.TESSERACT_CMD,
            "dp_max_tokens": self.DP_MAX_TOKENS,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton (memoised)."""
    return Settings()


def reload_settings() -> Settings:
    """Clear the memoised settings and re-read the environment (used by tests)."""
    get_settings.cache_clear()
    return get_settings()
