"""API routers, one module per resource area."""

from app.api.routers import (
    algorithms,
    analytics,
    benchmarks,
    changes,
    compare,
    documents,
    duplicates,
    reports,
    settings,
    templates,
    verification,
)

__all__ = [
    "documents",
    "verification",
    "compare",
    "changes",
    "duplicates",
    "templates",
    "algorithms",
    "benchmarks",
    "reports",
    "settings",
    "analytics",
]
