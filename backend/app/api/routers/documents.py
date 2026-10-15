"""Document management endpoints (``/api/documents``)."""

from __future__ import annotations

import math
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import bad_request, get_db, not_found
from app.core.config import get_settings
from app.core.security import safe_filename, validate_magic_bytes
from app.models import Document, VerificationRun
from app.pipeline import process_document
from app.schemas import (
    DocumentDetailOut,
    DocumentOut,
    DocumentTextOut,
    VerificationRunOut,
)

router = APIRouter(prefix="/documents", tags=["documents"])

SORT_KEYS = {
    "uploaded_at": Document.uploaded_at,
    "filename": Document.filename,
    "file_size": Document.file_size,
    "doc_type": Document.doc_type,
    "processing_duration_ms": Document.processing_duration_ms,
}

_SORT_PATTERN = "^(uploaded_at|filename|file_size|doc_type|processing_duration_ms)$"


def _doc_query():
    return select(Document).options(
        selectinload(Document.fields),
        selectinload(Document.verification_runs),
    )


def _require_document(db: Session, document_id: str) -> Document:
    document = db.execute(
        _doc_query().where(Document.id == document_id)
    ).unique().scalar_one_or_none()
    if document is None:
        raise not_found("Document", document_id)
    return document


def _stored_path(document: Document):
    """Absolute path of a stored file, guaranteed to be inside the upload root."""
    settings = get_settings()
    root = settings.upload_root.resolve()
    path = (settings.upload_root / document.stored_name).resolve()
    if root not in path.parents and path != root:
        raise not_found("Document file", document.id)
    return path


@router.post("/upload", status_code=201)
def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("unknown"),
    template_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload one document and run the full verification pipeline.

    The file is validated (name, size, magic bytes) before being staged, then
    handed to the pipeline which extracts, normalizes, validates, fingerprints,
    matches, decides and reports — recording real measurements throughout.
    """
    settings = get_settings()
    original = safe_filename(file.filename or "")
    if not original:
        raise bad_request("The uploaded file has no usable filename.")

    payload = file.file.read()
    if not payload:
        raise bad_request("The uploaded file is empty.")
    if len(payload) > settings.MAX_UPLOAD_BYTES:
        raise bad_request(
            f"File is {len(payload) / 1024 / 1024:.1f} MB; "
            f"the limit is {settings.MAX_UPLOAD_MB} MB."
        )
    if not validate_magic_bytes(original, payload):
        raise bad_request(
            f"'{original}' does not look like a supported PDF, DOCX, PNG or JPG "
            "file (its contents do not match its extension)."
        )

    settings.ensure_directories()
    staging = settings.upload_root / f"_incoming_{uuid.uuid4().hex}.bin"
    staging.write_bytes(payload)
    try:
        result = process_document(
            db,
            file_path=staging,
            original_filename=original,
            mime_type=file.content_type or "application/octet-stream",
            doc_type=doc_type or "unknown",
            template_id=template_id,
            generate_report=True,
        )
    finally:
        staging.unlink(missing_ok=True)

    db.flush()
    return {
        "document": DocumentOut.model_validate(result.document),
        "run": VerificationRunOut.model_validate(result.run),
        "stage_timings": [s.to_dict() for s in result.stage_timings],
        "pipeline_order": result.pipeline_order,
        "warnings": result.warnings,
        "extraction_warnings": result.extraction_warnings,
    }


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Substring match on filename"),
    doc_type: Optional[str] = None,
    validation_status: Optional[str] = None,
    duplicate_status: Optional[str] = None,
    upload_status: Optional[str] = None,
    sort: str = Query("uploaded_at", pattern=_SORT_PATTERN),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """Paginated, searchable, sortable document list with status filters."""
    stmt = _doc_query()
    count_stmt = select(func.count(Document.id))

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Document.filename.ilike(pattern))
        count_stmt = count_stmt.where(Document.filename.ilike(pattern))
    for column, value in (
        (Document.doc_type, doc_type),
        (Document.validation_status, validation_status),
        (Document.duplicate_status, duplicate_status),
        (Document.upload_status, upload_status),
    ):
        if value:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)

    total = db.execute(count_stmt).scalar_one() or 0
    column = SORT_KEYS[sort]
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    documents = db.execute(stmt).unique().scalars().all()

    return {
        "items": [DocumentOut.model_validate(d) for d in documents],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)) if total else 1,
    }


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Full document detail: metadata, extracted fields and run count."""
    document = _require_document(db, document_id)
    detail = DocumentDetailOut.model_validate(document)
    detail.verification_run_count = len(document.verification_runs)
    return detail


@router.get("/{document_id}/text")
def get_document_text(document_id: str, db: Session = Depends(get_db)):
    """Return the stored extracted-text preview (never the raw file bytes).

    Extraction notes (OCR unavailable, a page that is a bitmap scan, an
    unreadable page) are recorded as R008 findings on the latest run rather than
    as a column on the document, so they are read back from there. The previous
    implementation hardcoded ``warnings=[]``, which silently dropped the reason a
    document could not be read.
    """
    document = _require_document(db, document_id)

    warnings: List[str] = []
    latest = db.execute(
        select(VerificationRun)
        .where(VerificationRun.document_id == document.id)
        .order_by(VerificationRun.started_at.desc())
        .limit(1)
    ).scalars().first()
    if latest is not None:
        for finding in latest.findings:
            if finding.category != "extraction":
                continue
            notes = (finding.details_json or {}).get("warnings") or []
            for note in notes:
                text = str(note).strip()
                if text and text not in warnings:
                    warnings.append(text)

    return DocumentTextOut(
        document_id=document.id,
        filename=document.filename,
        original_excerpt=document.text_excerpt,
        page_count=document.page_count,
        extraction_method=document.extraction_method,
        extraction_confidence=document.extraction_confidence,
        ocr_used=bool(document.ocr_used),
        warnings=warnings,
    )


@router.get("/{document_id}/preview")
def preview_document(
    document_id: str,
    db: Session = Depends(get_db),
    inline: bool = Query(True),
):
    """Serve the stored original file for preview/download.

    The path is reconstructed from the database and re-validated against the
    storage root, so a client-supplied path can never escape the upload
    directory.
    """
    document = _require_document(db, document_id)
    path = _stored_path(document)
    if not path.exists():
        raise not_found("Document file", document_id)
    return FileResponse(
        path,
        media_type=document.mime_type or "application/octet-stream",
        filename=document.filename,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)):
    """Download the stored original file as an attachment."""
    return preview_document(document_id, db=db, inline=False)


@router.get("/{document_id}/structure")
def get_document_structure(document_id: str, db: Session = Depends(get_db)):
    """Re-derive the document section hierarchy on demand (with BFS/DFS trace).

    Returns ``uncertain: true`` when extraction yields no reliable headings
    rather than inventing a structure.
    """
    document = _require_document(db, document_id)
    path = _stored_path(document)
    if not path.exists():
        raise not_found("Document file", document_id)

    from app.services.extraction import extract
    from app.services.structure import analyze_structure

    extraction = extract(path)
    analysis = analyze_structure(extraction)
    payload = analysis.to_dict() if hasattr(analysis, "to_dict") else dict(analysis)
    return payload


@router.get("/{document_id}/pdf-metadata")
def get_document_pdf_metadata(
    document_id: str,
    include_spans: bool = Query(
        False, description="Include the full per-span layout detail (capped)."
    ),
    max_spans: int = Query(
        2000, ge=1, le=20_000, description="Cap on returned spans when included."
    ),
    db: Session = Depends(get_db),
):
    """Span-level PDF layout metadata (font, size, style, colour, position).

    Returns 400 for non-PDF documents — this endpoint reads the PDF content
    stream directly and has no meaning for a DOCX or an image. The summary
    (fonts, sizes, colour palette, style counts) is always returned; the full
    span list is opt-in via ``include_spans`` and bounded by ``max_spans``.
    """
    from app.services.pdf_metadata import extract_pdf_metadata, is_pdf
    from app.services import ServiceError

    document = _require_document(db, document_id)
    path = _stored_path(document)
    if not path.exists():
        raise not_found("Document file", document_id)
    if not is_pdf(path):
        raise bad_request(
            "Span-level metadata is only available for PDF documents "
            f"('{document.filename}' is not a PDF)."
        )

    try:
        result = extract_pdf_metadata(path)
    except ServiceError as exc:
        raise bad_request(
            f"Could not read layout metadata from '{document.filename}': {exc.message}"
        ) from None

    payload = result.to_dict(include_spans=include_spans, max_spans=max_spans)
    payload["document_id"] = document.id
    payload["filename"] = document.filename
    return payload


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Delete a document, its stored file, its reports and cascade-owned rows."""
    document = _require_document(db, document_id)
    settings = get_settings()

    path = settings.upload_root / document.stored_name
    root = settings.upload_root.resolve()
    if root in path.resolve().parents or path.resolve() == root:
        path.unlink(missing_ok=True)

    for run in document.verification_runs:
        for report in run.reports:
            report_path = settings.report_root / report.relative_path
            if settings.report_root.resolve() in report_path.resolve().parents:
                report_path.unlink(missing_ok=True)

    filename = document.filename
    db.delete(document)
    db.flush()
    return {"deleted": document_id, "filename": filename}
