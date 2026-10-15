"""Duplicate detection endpoints (``/api/duplicates``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, not_found
from app.models import Document, DuplicateGroup, GroupType
from app.schemas import (
    DuplicateDocumentRef,
    DuplicateGroupDetailOut,
    DuplicateGroupOut,
    DuplicateSummaryOut,
)

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


def _document_refs(db: Session, ids: list[str]) -> list[DuplicateDocumentRef]:
    """Resolve group member ids into document references (missing ids skipped)."""
    if not ids:
        return []
    rows = db.execute(select(Document).where(Document.id.in_(ids))).scalars().all()
    by_id = {row.id: row for row in rows}
    refs: list[DuplicateDocumentRef] = []
    for doc_id in ids:
        document = by_id.get(doc_id)
        if document is None:
            continue
        refs.append(
            DuplicateDocumentRef(
                id=document.id,
                filename=document.filename,
                doc_type=document.doc_type,
                duplicate_status=document.duplicate_status,
                uploaded_at=document.uploaded_at,
            )
        )
    return refs


@router.get("")
def list_duplicates(
    db: Session = Depends(get_db),
    group_type: str | None = Query(None, pattern="^(exact|content)$"),
    limit: int = Query(100, ge=1, le=500),
):
    """Return exact-duplicate and content-duplicate groups.

    Grouping is by SHA-256 fingerprints only. Two documents are never labelled
    duplicates merely because their filenames or layouts match.
    """
    stmt = select(DuplicateGroup).order_by(DuplicateGroup.created_at.desc())
    if group_type:
        stmt = stmt.where(DuplicateGroup.group_type == group_type)
    groups = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "items": [DuplicateGroupOut.model_validate(group) for group in groups]
    }


@router.get("/summary")
def duplicate_summary(db: Session = Depends(get_db)):
    """Aggregate duplicate counts computed in SQL."""
    by_status = {
        status: count
        for status, count in db.execute(
            select(Document.duplicate_status, func.count(Document.id))
            .group_by(Document.duplicate_status)
        ).all()
    }
    exact = db.execute(
        select(func.count(DuplicateGroup.id)).where(
            DuplicateGroup.group_type == GroupType.EXACT
        )
    ).scalar_one() or 0
    content = db.execute(
        select(func.count(DuplicateGroup.id)).where(
            DuplicateGroup.group_type == GroupType.CONTENT
        )
    ).scalar_one() or 0
    total = db.execute(select(func.count(DuplicateGroup.id))).scalar_one() or 0
    flagged = sum(
        count
        for status, count in by_status.items()
        if status in {"exact_duplicate", "content_duplicate", "near_duplicate"}
    )
    return DuplicateSummaryOut(
        total_groups=total,
        exact_groups=exact,
        content_groups=content,
        documents_flagged=flagged,
        by_status=by_status,
    )


@router.get("/{group_id}")
def get_duplicate_group(group_id: str, db: Session = Depends(get_db)):
    """Full detail of one duplicate group, including resolved member documents."""
    group = db.get(DuplicateGroup, group_id)
    if group is None:
        raise not_found("Duplicate group", group_id)
    detail = DuplicateGroupDetailOut.model_validate(group)
    detail.documents = _document_refs(db, list(group.document_ids_json or []))
    return detail
