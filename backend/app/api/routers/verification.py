"""Verification endpoints (``/api/verification`` and ``/api/verify``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, not_found
from app.models import Document, VerificationRun
from app.pipeline import recheck_document
from app.schemas import (
    DocumentOut,
    VerificationRunDetailOut,
    VerificationRunOut,
)

router = APIRouter(tags=["verification"])


def _runs_with_children():
    return select(VerificationRun).options(
        selectinload(VerificationRun.findings),
        selectinload(VerificationRun.similarity_matches),
        selectinload(VerificationRun.reports),
    )


@router.post("/verify/{document_id}")
def verify_document(
    document_id: str,
    db: Session = Depends(get_db),
    template_id: str | None = Query(None),
    generate_report: bool = Query(True),
):
    """Run (or re-run) the verification pipeline for an existing document.

    Re-verification re-reads the stored file, re-extracts and re-runs every
    algorithm, so the new run's metrics are real measurements of the current
    code — never a copy of the previous run.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise not_found("Document", document_id)

    result = recheck_document(
        db,
        document_id=document_id,
        template_id=template_id,
        generate_report=generate_report,
    )
    db.flush()
    return {
        "document": DocumentOut.model_validate(result.document),
        "run": VerificationRunOut.model_validate(result.run),
        "warnings": result.warnings,
    }


@router.get("/verifications")
def list_verifications(
    db: Session = Depends(get_db),
    document_id: str | None = None,
    outcome: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """Paginated verification run history, newest first."""
    stmt = select(VerificationRun)
    count_stmt = select(func.count(VerificationRun.id))
    if document_id:
        stmt = stmt.where(VerificationRun.document_id == document_id)
        count_stmt = count_stmt.where(VerificationRun.document_id == document_id)
    if outcome:
        stmt = stmt.where(VerificationRun.outcome == outcome)
        count_stmt = count_stmt.where(VerificationRun.outcome == outcome)

    total = db.execute(count_stmt).scalar_one() or 0
    stmt = (
        stmt.order_by(VerificationRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    runs = db.execute(stmt).scalars().all()
    return {
        "items": [VerificationRunOut.model_validate(r) for r in runs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/verifications/{run_id}")
def get_verification(run_id: str, db: Session = Depends(get_db)):
    """Full verification run detail: findings, similarity matches, thresholds."""
    run = db.execute(
        _runs_with_children().where(VerificationRun.id == run_id)
    ).unique().scalar_one_or_none()
    if run is None:
        raise not_found("Verification run", run_id)
    return VerificationRunDetailOut.model_validate(run)
