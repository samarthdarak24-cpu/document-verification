"""Change-detection endpoints (``/api/changes``).

These endpoints answer "what changed between these two documents?" using the
span-level PDF metadata from :mod:`app.services.pdf_metadata` and the LCS /
edit-distance change analysis from
:mod:`app.services.document_change_detector`. Both are pure services; this
router only resolves document ids to files and shapes the response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import bad_request, get_db, not_found
from app.core.config import get_settings
from app.models import Document
from app.schemas import (
    ChangeDetectRequest,
    ChangeDetectResponse,
    TextChangeRequest,
    TextChangeResponse,
)
from app.services import ServiceError
from app.services.document_change_detector import (
    detect_document_changes,
    detect_text_changes,
)
from app.services.extraction import extract
from app.services.pdf_metadata import extract_pdf_metadata, is_pdf

router = APIRouter(prefix="/changes", tags=["changes"])


def _require_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise not_found("Document", document_id)
    return document


def _stored_path(document: Document):
    settings = get_settings()
    path = settings.upload_root / document.stored_name
    if not path.exists():
        raise not_found("Document file", document.id)
    return path


def _document_meta(document: Document) -> Dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.filename,
        "doc_type": document.doc_type,
        "file_size": document.file_size,
        "page_count": document.page_count,
        "file_sha256": document.file_sha256,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


def _load_source(document: Document) -> Tuple[Any, bool]:
    """Return ``(source, has_span_metadata)`` for a stored document.

    PDFs are read with the span-level metadata extractor so typography can be
    compared; every other format falls back to plain text extraction, in which
    case only the text changes are available.
    """
    path = _stored_path(document)
    if is_pdf(path):
        try:
            return extract_pdf_metadata(path), True
        except ServiceError:
            # A PDF that PyMuPDF cannot open as a layout still has extractable
            # text; fall through to the generic extractor rather than failing.
            pass
    try:
        extraction = extract(path)
    except ServiceError as exc:
        raise bad_request(
            f"Could not read '{document.filename}': {exc.message}"
        ) from None
    return extraction, False


@router.post("/detect", response_model=ChangeDetectResponse)
def detect_changes(payload: ChangeDetectRequest, db: Session = Depends(get_db)):
    """Compare two stored documents and report what changed."""
    if payload.source_document_id == payload.target_document_id:
        raise bad_request("Source and target must be two different documents.")

    source_doc = _require_document(db, payload.source_document_id)
    target_doc = _require_document(db, payload.target_document_id)

    source, source_has_spans = _load_source(source_doc)
    target, target_has_spans = _load_source(target_doc)

    report = detect_document_changes(
        source,
        target,
        compare_metadata=payload.compare_metadata and source_has_spans and target_has_spans,
        max_tokens=payload.max_tokens,
    )
    if payload.compare_metadata and not (source_has_spans and target_has_spans):
        report.warnings.append(
            "At least one document is not a PDF, so only text changes were "
            "compared (no layout metadata)."
        )

    return ChangeDetectResponse(
        source_document=_document_meta(source_doc),
        target_document=_document_meta(target_doc),
        report=report.to_dict(),
        compared_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/text", response_model=TextChangeResponse)
def detect_text(payload: TextChangeRequest):
    """Compare two raw texts (no stored file required)."""
    report = detect_text_changes(
        payload.original_text,
        payload.modified_text,
        max_tokens=payload.max_tokens,
    )
    return TextChangeResponse(
        report=report.to_dict(),
        compared_at=datetime.now(timezone.utc).isoformat(),
    )


__all__ = ["router"]
