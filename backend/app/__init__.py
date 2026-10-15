"""DocuTrace backend application package.

The package is intentionally thin at the top level: it only re-exports the
application version so tooling (health checks, seed scripts, tests) does not
have to import the FastAPI app just to learn the API version.

Subpackages
-----------
``app.algorithms``  Pure-Python DAA algorithm core (pre-existing, tested, frozen).
``app.core``        Configuration + security helpers.
``app.database``    SQLAlchemy 2.0 engine/session plumbing.
``app.models``      ORM models (documents, templates, runs, ...).
``app.schemas``     Pydantic v2 request/response models.
``app.services``    Extraction, normalization, similarity, verification, reports.
``app.pipeline``    Upload orchestration.
``app.api``         FastAPI routers and dependencies.
``app.main``        Application factory / FastAPI instance.
"""

from app.core.config import APP_VERSION

__version__ = APP_VERSION

__all__ = ["__version__"]
