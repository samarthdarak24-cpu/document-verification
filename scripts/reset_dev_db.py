"""Reset the development database to a pristine, demo-ready state.

Deletes every row from every table, then re-seeds the documented defaults.
Also clears the generated document/report storage so a demo starts from zero.

Usage (backend must be stopped):
    python scripts/reset_dev_db.py            # tables only
    python scripts/reset_dev_db.py --storage  # also delete stored files
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.database.session import get_session_factory, init_db  # noqa: E402
from app.models.models import (  # noqa: E402
    AlgorithmRun,
    ApplicationSetting,
    BenchmarkResult,
    Document,
    DocumentTemplate,
    DuplicateGroup,
    ExtractedField,
    GeneratedReport,
    SimilarityMatch,
    TemplateField,
    VerificationFinding,
    VerificationRun,
)
from app.models import seed_defaults  # noqa: E402

# Children first so foreign keys stay satisfied.
TABLES = [
    AlgorithmRun,
    BenchmarkResult,
    SimilarityMatch,
    VerificationFinding,
    DuplicateGroup,
    ExtractedField,
    GeneratedReport,
    VerificationRun,
    Document,
    TemplateField,
    DocumentTemplate,
    ApplicationSetting,
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storage",
        action="store_true",
        help="also delete uploaded documents and generated reports",
    )
    args = parser.parse_args()

    init_db()
    db = get_session_factory()()
    try:
        for model in TABLES:
            deleted = db.query(model).delete()
            print(f"  cleared {model.__name__:18} ({deleted} row(s))")
        db.commit()
    finally:
        db.close()

    # Re-seed the six settings groups and the six starter templates.
    #
    # ``init_db()`` only runs ``create_all`` — it does NOT insert any seed data.
    # Calling it here previously printed "re-seeded" while leaving both tables
    # empty, so a reset backend resolved every document against the empty
    # "custom" template: no template fields, no rule findings and
    # ``validation_status = not_run``. Seed exactly what the app lifespan seeds.
    session = get_session_factory()()
    try:
        seeded = seed_defaults(session)
        print(
            f"  re-seeded {seeded['settings']} setting group(s) and "
            f"{seeded['templates']} template(s)"
        )
    finally:
        session.close()

    if args.storage:
        from app.core.config import get_settings

        settings = get_settings()
        for name, path in (
            ("documents", settings.upload_root),
            ("reports", settings.report_root),
        ):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                print(f"  removed storage/{name}")
            path.mkdir(parents=True, exist_ok=True)

    print("\nDevelopment database reset to a pristine state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
