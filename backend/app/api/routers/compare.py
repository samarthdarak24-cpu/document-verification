"""Comparison endpoints (``/api/compare``)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import pymupdf
from app.integrations.pdf_diff.analyzer import run_pdf_diff_analysis
from app.integrations.pdf_diff.report_generator import render_pdf_diff_report

from app.api.deps import bad_request, get_db, not_found
from app.core.config import get_settings
from app.models import Document
from app.algorithms import count_inversions, edit_distance, lcs_dp, merge_sort
from app.schemas import CompareExportRequest, CompareRequest
from app.services import ServiceError
from app.services.extraction import extract
from app.services.normalization import normalize_text, normalize_for_comparison
from app.services.reporting import (
    comparison_report_json,
    persist_report_row,
    render_comparison_report,
)
from app.services.similarity import compare_documents, overall_score, similarity_label
from app.services.structure import analyze_structure, compare_document_structures

router = APIRouter(prefix="/compare", tags=["compare"])


def _document_tokens(db: Session, document_id: str) -> tuple[Document, List[str]]:
    """Load a document and rebuild its token list from the stored file."""
    document = db.get(Document, document_id)
    if document is None:
        raise not_found("Document", document_id)
    settings = get_settings()
    path = settings.upload_root / document.stored_name
    if not path.exists():
        raise not_found("Document file", document_id)
    try:
        extraction = extract(path)
    except ServiceError as exc:
        raise bad_request(f"Could not read '{document.filename}': {exc.message}") from None
    normalized = normalize_text(extraction.full_text)
    return document, list(normalized.comparison_tokens)


def _document_meta(document: Optional[Document]) -> Dict[str, Any]:
    if document is None:
        return {}
    return {
        "id": document.id,
        "filename": document.filename,
        "doc_type": document.doc_type,
        "file_size": document.file_size,
        "page_count": document.page_count,
        "file_sha256": document.file_sha256,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


def _section_rank_reordering(
    source_sections: List[str], target_sections: List[str], max_sections: int = 200
) -> Optional[Dict[str, Any]]:
    """Quantify section reordering with inversion counting (Unit II).

    Only sections with established correspondence are compared: the shared
    section names are ranked in the order they appear in the source document,
    and the target's ordering of those same sections is scored.
    """
    if not source_sections or not target_sections:
        return None
    shared = [name for name in source_sections if name in set(target_sections)]
    if len(shared) < 2:
        return None
    if len(shared) > max_sections:
        shared = shared[:max_sections]
    rank = {name: index for index, name in enumerate(shared)}
    target_ranks = [rank[name] for name in target_sections if name in rank]
    result = count_inversions(target_ranks, trace=False)
    return {
        "matched_sections": shared,
        "section_count": len(shared),
        "original_order": list(range(len(shared))),
        "observed_order": target_ranks,
        "inversion_count": result.inversion_count,
        "normalized_reorder_score": round(result.normalized_reorder_score, 4),
        "comparisons": result.comparisons,
    }


@router.post("")
def compare(payload: CompareRequest, db: Session = Depends(get_db)):
    """Compare two documents (by id or raw text) with the full algorithm stack."""
    source_doc = target_doc = None
    source_sections: List[str] = []
    target_sections: List[str] = []
    source_analysis = target_analysis = None

    if payload.source_document_id:
        source_doc, source_tokens = _document_tokens(db, payload.source_document_id)
        source_extraction = extract(get_settings().upload_root / source_doc.stored_name)
        source_analysis = analyze_structure(source_extraction)
        source_sections = [s.get("section", "") for s in source_analysis.sections]
        source_label = payload.source_label or source_doc.filename
    elif payload.source_text is not None:
        source_tokens = normalize_for_comparison(payload.source_text)
        source_label = payload.source_label or "Source text"
    else:
        raise bad_request("Provide 'source_document_id' or 'source_text'.")

    if payload.target_document_id:
        target_doc, target_tokens = _document_tokens(db, payload.target_document_id)
        target_extraction = extract(get_settings().upload_root / target_doc.stored_name)
        target_analysis = analyze_structure(target_extraction)
        target_sections = [s.get("section", "") for s in target_analysis.sections]
        target_label = payload.target_label or target_doc.filename
    elif payload.target_text is not None:
        target_tokens = normalize_for_comparison(payload.target_text)
        target_label = payload.target_label or "Target text"
    else:
        raise bad_request("Provide 'target_document_id' or 'target_text'.")

    source_fields: Dict[str, str] = {}
    target_fields: Dict[str, str] = {}
    if source_doc is not None:
        source_fields = {
            field.field_name.lower(): field.field_value or ""
            for field in source_doc.fields
        }
    if target_doc is not None:
        target_fields = {
            field.field_name.lower(): field.field_value or ""
            for field in target_doc.fields
        }

    comparison = compare_documents(
        source_tokens,
        target_tokens,
        max_tokens=get_settings().DP_MAX_TOKENS,
        source_fields=source_fields or None,
        target_fields=target_fields or None,
    )

    structure_payload: Optional[Dict[str, Any]] = None
    reordering: Optional[Dict[str, Any]] = None
    if (
        payload.compare_structure
        and source_analysis is not None
        and target_analysis is not None
    ):
        structure_payload = compare_document_structures(source_analysis, target_analysis)
        reordering = _section_rank_reordering(source_sections, target_sections)

    payload_out = comparison.to_dict()
    if structure_payload is not None:
        payload_out["structure"] = structure_payload
    if reordering is not None:
        payload_out["structure_reordering"] = reordering

    algorithms_executed = ["lcs_dp", "edit_distance", "normalize"]
    if payload.compare_structure:
        algorithms_executed.extend(["build_tree", "compare_structures", "dfs", "bfs"])
    if reordering is not None:
        algorithms_executed.append("count_inversions")

    crit_mismatches = [
        fd for fd in (comparison.field_differences or [])
        if fd.get("critical") and (fd.get("mismatch") or not fd.get("equal"))
    ]
    return {
        "source_document": _document_meta(source_doc) if source_doc else {"label": source_label},
        "target_document": _document_meta(target_doc) if target_doc else {"label": target_label},
        "comparison": payload_out,
        "overall_score": comparison.overall_score,
        "text_similarity": comparison.text_similarity,
        "edit_similarity": comparison.edit_similarity,
        "critical_mismatches": crit_mismatches,
        "field_differences": comparison.field_differences,
        "verdict": similarity_label(comparison.overall_score),
        "explanation": f"Algorithm verdict: {similarity_label(comparison.overall_score)}. Measured text similarity: {round(comparison.text_similarity * 100, 1)}%, edit similarity: {round(comparison.edit_similarity * 100, 1)}%.",
        "algorithms_executed": algorithms_executed,
        "compared_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/export")
def export_comparison(payload: CompareExportRequest):
    """Render a comparison PDF from a previously computed comparison payload."""
    settings = get_settings()
    settings.ensure_directories()
    body = payload.payload.model_dump()
    json_payload = comparison_report_json(body)
    artifact = render_comparison_report(json_payload, comparison_id=payload.comparison_id)
    return FileResponse(
        artifact.absolute_path,
        media_type="application/pdf",
        filename=f"docutrace-comparison-{artifact.report_uuid[:8]}.pdf",
    )


@router.post("/field-diff")
def field_diff(payload: dict, db: Session = Depends(get_db)):
    """Field-level difference detail for two documents, ranked by impact."""
    source_id = payload.get("source_document_id")
    target_id = payload.get("target_document_id")
    if not source_id or not target_id:
        raise bad_request("Both 'source_document_id' and 'target_document_id' are required.")
    source = db.get(Document, source_id)
    target = db.get(Document, target_id)
    if source is None or target is None:
        raise not_found("Document", source_id if source is None else target_id)

    source_fields = {f.field_name.lower(): f.field_value or "" for f in source.fields}
    target_fields = {f.field_name.lower(): f.field_value or "" for f in target.fields}
    names = sorted(set(source_fields) | set(target_fields))
    differences = []
    for name in names:
        left = source_fields.get(name, "")
        right = target_fields.get(name, "")
        result = edit_distance(left, right, with_operations=True)
        differences.append({
            "field": name,
            "source_value": left or None,
            "target_value": right or None,
            "equal": left == right,
            "edit_distance": result.distance,
            "similarity": round(result.similarity, 4),
            "operations": result.operations[:20],
        })
    # Rank the most-changed fields first (Unit II merge sort on similarity).
    ranked = merge_sort(differences, key=lambda item: item["similarity"]).sorted_items
    return {
        "fields": ranked,
        "field_differences": ranked,
        "changed": sum(1 for d in ranked if not d["equal"]),
    }


# --------------------------------------------------------------------------- #
# Extended pdf-diff integration endpoints
# --------------------------------------------------------------------------- #
@router.post("/pdf-diff")
async def compare_pdf_diff(
    request: Request,
    db: Session = Depends(get_db),
):
    """Run the extended pdf-diff analysis on two PDFs (by DB ID or direct file upload)."""
    settings = get_settings()
    settings.ensure_directories()
    temp_dir = settings.storage_root / "temp_compare"
    temp_dir.mkdir(parents=True, exist_ok=True)

    content_type = request.headers.get("content-type", "")

    p1: Optional[Path] = None
    p2: Optional[Path] = None
    orig_label: str = "Original Document"
    mod_label: str = "Modified Document"
    source_doc_id: Optional[str] = None
    target_doc_id: Optional[str] = None
    render_image: bool = True

    if "multipart/form-data" in content_type:
        form = await request.form()
        orig_file = form.get("original_file")
        mod_file = form.get("modified_file")
        source_id = form.get("source_document_id")
        target_id = form.get("target_document_id")
        render_flag = form.get("render_image")
        if render_flag is not None:
            render_image = str(render_flag).lower() in ("true", "1", "yes")

        # Resolve original document
        if orig_file and hasattr(orig_file, "filename") and orig_file.filename:
            token1 = f"temp_orig_{uuid.uuid4().hex[:10]}_{Path(orig_file.filename).name}"
            p1 = temp_dir / token1
            contents = await orig_file.read()
            p1.write_bytes(contents)
            orig_label = orig_file.filename
            source_doc_id = token1
        elif source_id:
            doc = db.get(Document, str(source_id))
            if not doc:
                raise not_found("Document", str(source_id))
            p1 = settings.upload_root / doc.stored_name
            orig_label = doc.filename
            source_doc_id = doc.id

        # Resolve modified document
        if mod_file and hasattr(mod_file, "filename") and mod_file.filename:
            token2 = f"temp_mod_{uuid.uuid4().hex[:10]}_{Path(mod_file.filename).name}"
            p2 = temp_dir / token2
            contents = await mod_file.read()
            p2.write_bytes(contents)
            mod_label = mod_file.filename
            target_doc_id = token2
        elif target_id:
            doc = db.get(Document, str(target_id))
            if not doc:
                raise not_found("Document", str(target_id))
            p2 = settings.upload_root / doc.stored_name
            mod_label = doc.filename
            target_doc_id = doc.id
    else:
        # JSON body
        body = await request.json()
        source_id = body.get("source_document_id")
        target_id = body.get("target_document_id")
        render_image = body.get("render_image", True)

        if not source_id or not target_id:
            raise bad_request("Provide both 'source_document_id' and 'target_document_id'.")

        doc1 = db.get(Document, source_id)
        if not doc1:
            raise not_found("Document", source_id)
        p1 = settings.upload_root / doc1.stored_name
        orig_label = doc1.filename
        source_doc_id = doc1.id

        doc2 = db.get(Document, target_id)
        if not doc2:
            raise not_found("Document", target_id)
        p2 = settings.upload_root / doc2.stored_name
        mod_label = doc2.filename
        target_doc_id = doc2.id

    if not p1 or not p1.exists():
        raise bad_request("Original document file is missing or unreadable.")
    if not p2 or not p2.exists():
        raise bad_request("Modified document file is missing or unreadable.")

    analysis = run_pdf_diff_analysis(
        p1,
        p2,
        source_label=orig_label,
        target_label=mod_label,
        render_image=render_image,
    )
    analysis["source_document"]["id"] = source_doc_id
    analysis["target_document"]["id"] = target_doc_id
    return analysis


@router.get("/diff-image/{comparison_id}")
def get_diff_image(comparison_id: str):
    """Retrieve the rasterized side-by-side diff comparison image."""
    settings = get_settings()
    img_path = settings.storage_root / "diff_images" / f"{comparison_id}.png"
    if not img_path.exists():
        raise not_found("Diff image", comparison_id)
    return FileResponse(img_path, media_type="image/png")


@router.get("/page-render/{doc_or_temp_id}/{page}")
def render_document_page(
    doc_or_temp_id: str,
    page: int,
    dpi: int = 150,
    db: Session = Depends(get_db),
):
    """Render a single page of an original or modified PDF as a high-resolution PNG."""
    settings = get_settings()
    file_path: Optional[Path] = None

    if doc_or_temp_id.startswith("temp_"):
        candidate = settings.storage_root / "temp_compare" / doc_or_temp_id
        if candidate.exists():
            file_path = candidate
    else:
        doc = db.get(Document, doc_or_temp_id)
        if doc is not None:
            candidate = settings.upload_root / doc.stored_name
            if candidate.exists():
                file_path = candidate

    if file_path is None or not file_path.exists():
        raise not_found("Document or temporary file", doc_or_temp_id)

    try:
        doc_pdf = pymupdf.open(str(file_path))
        if page < 1 or page > len(doc_pdf):
            doc_pdf.close()
            raise bad_request(f"Page {page} out of range (1-{len(doc_pdf)})")
        p = doc_pdf[page - 1]
        pix = p.get_pixmap(dpi=dpi)
        data = pix.tobytes("png")
        doc_pdf.close()
        return Response(content=data, media_type="image/png")
    except Exception as exc:
        raise bad_request(f"Could not render page {page}: {exc}")


@router.post("/pdf-diff/report")
def export_pdf_diff_report(payload: Dict[str, Any]):
    """Generate and return a downloadable Document Comparison & Modification Analysis Report."""
    analysis_data = payload.get("analysis") or payload
    report_file = render_pdf_diff_report(analysis_data)
    report_id = analysis_data.get("comparison_id", "diff")
    return FileResponse(
        report_file,
        media_type="application/pdf",
        filename=f"docutrace-diff-report-{report_id}.pdf",
    )

