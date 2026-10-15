"""Report rendering: verification PDFs, comparison PDFs and JSON exports.

Rules the renderer follows
--------------------------
1. **Reports are rendered from stored run data only.** :func:`render_verification_report`
   takes a ``VerificationRun`` row (plus its findings/matches/algorithm rows)
   and never re-runs an algorithm, re-extracts text or re-opens the document.
   The same run id therefore always yields byte-identical content, which is what
   makes the report a citable artifact.
2. **Every claim is traceable.** The "Algorithms executed" section lists the real
   measured timings and operation counts recorded in ``algorithm_runs`` — not
   decorative descriptions.
3. **No authenticity verdict.** Every page footer and every report ends with the
   same limitation paragraph: DocuTrace produces an automated similarity and
   consistency assessment, never a determination of authenticity or forgery.
4. **The comparison export is stateless.** :func:`render_comparison_report`
   accepts an arbitrary comparison payload (the response of ``POST /api/compare``)
   and renders it; it needs no database access at all.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.config import get_settings
from app.models.models import (
    AlgorithmRun,
    Document,
    GeneratedReport,
    ReportType,
    VerificationFinding,
    VerificationRun,
    SimilarityMatch,
    generate_uuid,
)

#: Section order used in every verification report.
REPORT_SECTIONS: Tuple[str, ...] = (
    "branding",
    "document_metadata",
    "verification_summary",
    "required_field_validation",
    "missing_and_inconsistent_fields",
    "exact_duplicate_results",
    "similarity_candidates",
    "field_level_differences",
    "structural_verification",
    "algorithms_executed",
    "explanation",
    "limitations_and_recommendation",
)

#: The mandatory limitation paragraph (never omitted).
LIMITATION_TEXT = (
    "Limitations. This report is an automated similarity and consistency "
    "assessment produced by deterministic algorithms (KMP label search, SHA-256 "
    "hashing, LCS, Levenshtein edit distance, Jaccard shingle indexing, "
    "bipartite field alignment, DFS/BFS structure validation). It compares "
    "extracted text and declared template fields; it does not assess visual "
    "appearance, signatures, seals, letterheads or legal validity, and it cannot "
    "determine whether a document is genuine or forged. OCR-derived text is "
    "inherently uncertain. A qualified human reviewer must interpret every "
    "finding below in the context of the submitting organisation's policies."
)


@dataclass
class ReportArtifact:
    """A rendered report plus where it was written."""

    report_uuid: str
    relative_path: str
    absolute_path: Path
    report_type: str
    byte_size: int
    section_titles: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_uuid": self.report_uuid,
            "relative_path": self.relative_path,
            "report_type": self.report_type,
            "byte_size": self.byte_size,
        }


# --------------------------------------------------------------------------- #
# PDF plumbing
# --------------------------------------------------------------------------- #
def _styles() -> Dict[str, Any]:
    """Build the paragraph styles used by every report."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    accent = colors.HexColor("#1F3A5F")
    return {
        "title": ParagraphStyle(
            "DocuTraceTitle", parent=base["Title"], fontSize=20,
            textColor=accent, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DocuTraceSubtitle", parent=base["Normal"], fontSize=10,
            textColor=colors.HexColor("#4A5568"), spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "DocuTraceH1", parent=base["Heading1"], fontSize=13,
            textColor=accent, spaceBefore=12, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "DocuTraceH2", parent=base["Heading2"], fontSize=11,
            textColor=colors.HexColor("#2D3748"), spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "DocuTraceBody", parent=base["Normal"], fontSize=9, leading=12.5,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "DocuTraceSmall", parent=base["Normal"], fontSize=7.5, leading=10,
            textColor=colors.HexColor("#5A6472"),
        ),
        "bullet": ParagraphStyle(
            "DocuTraceBullet", parent=base["Normal"], fontSize=9, leading=12.5,
            leftIndent=12, bulletIndent=2, spaceAfter=2,
        ),
        "mono": ParagraphStyle(
            "DocuTraceMono", parent=base["Normal"], fontName="Courier",
            fontSize=7.5, leading=10, backColor=colors.HexColor("#F4F6F8"),
            borderPadding=4, spaceAfter=4,
        ),
    }


def _escape(text: Any) -> str:
    """Escape text for ReportLab's XML-ish paragraph markup."""
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _kv_table(rows: Sequence[Tuple[str, Any]], styles: Dict[str, Any], width: int = 460):
    """Render a two-column key/value table."""
    from reportlab.lib import colors
    from reportlab.platypus import Table

    data = [[_escape(key), _escape(value)] for key, value in rows]
    if not data:
        return None
    table = Table(data, colWidths=[150, width - 150], hAlign="LEFT")
    table.setStyle(
        _table_style(
            header=False,
            grid=colors.HexColor("#DDE3EA"),
            background=colors.HexColor("#F7F9FB"),
        )
    )
    return table


def _table_style(
    header: bool = True,
    grid=None,
    background=None,
):
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    commands: List[Tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, grid or colors.HexColor("#DDE3EA")),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
        ]
    elif background is not None:
        commands.append(("BACKGROUND", (0, 0), (0, -1), background))
    return TableStyle(commands)


def _grid(
    header_row: Sequence[str],
    body_rows: Sequence[Sequence[Any]],
    styles: Dict[str, Any],
    col_widths: Optional[Sequence[int]] = None,
):
    from reportlab.platypus import Table

    data = [[_escape(cell) for cell in header_row]]
    data += [[_escape(cell) for cell in row] for row in body_rows]
    if len(data) == 1:
        return None
    table = Table(data, colWidths=list(col_widths) if col_widths else None, hAlign="LEFT")
    table.setStyle(_table_style(header=True))
    return table


def _bullets(items: Iterable[str], styles: Dict[str, Any]):
    from reportlab.platypus import ListFlowable, ListItem, Paragraph

    flowables: List[Any] = []
    for item in items:
        flowables.append(
            ListItem(Paragraph(_escape(item), styles["bullet"]), leftIndent=12)
        )
    if not flowables:
        return None
    return ListFlowable(flowables, bulletType="bullet", start="circle", leftIndent=10)


# --------------------------------------------------------------------------- #
# Verification report
# --------------------------------------------------------------------------- #
def _gather_verification_data(db: Any, run: VerificationRun) -> Dict[str, Any]:
    """Collect everything needed for the report from stored rows only."""
    from sqlalchemy import select

    document: Optional[Document] = run.document
    if document is None:
        document = db.get(Document, run.document_id)

    findings: List[VerificationFinding] = list(
        db.execute(
            select(VerificationFinding)
            .where(VerificationFinding.run_id == run.id)
            .order_by(VerificationFinding.rule_id)
        ).scalars()
    )
    matches: List[SimilarityMatch] = list(
        db.execute(
            select(SimilarityMatch)
            .where(SimilarityMatch.run_id == run.id)
            .order_by(SimilarityMatch.overall_score.desc())
        ).scalars()
    )
    algorithm_runs: List[AlgorithmRun] = list(
        db.execute(
            select(AlgorithmRun)
            .where(AlgorithmRun.run_id == run.id)
            .order_by(AlgorithmRun.created_at)
        ).scalars()
    )
    fields = list(document.fields) if document is not None else []
    return {
        "document": document,
        "findings": findings,
        "matches": matches,
        "algorithm_runs": algorithm_runs,
        "fields": fields,
        # The structure stage is persisted as an algorithm-run row (the tree, the
        # DFS/BFS counters and the validation verdict), so the report can render
        # it without re-analysing the document.
        "structure": _structure_payload(algorithm_runs),
    }


def _structure_payload(algorithm_runs: Sequence[AlgorithmRun]) -> Optional[Dict[str, Any]]:
    """Return the structure analysis recorded by the pipeline, if any."""
    for item in algorithm_runs:
        if "structure" in item.algorithm.lower():
            payload = _load_json(item.result_summary_json)
            if isinstance(payload, dict):
                return payload
    return None


def verification_report_json(db: Any, run: VerificationRun) -> Dict[str, Any]:
    """Return the JSON export of a verification run (same content as the PDF)."""
    data = _gather_verification_data(db, run)
    document: Optional[Document] = data["document"]
    findings: List[VerificationFinding] = data["findings"]
    matches: List[SimilarityMatch] = data["matches"]

    return {
        "report_type": "verification",
        "report_uuid": generate_uuid(),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sections": list(REPORT_SECTIONS),
        "branding": _branding(),
        "run": _run_summary(run),
        "document": _document_metadata(document),
        "fields": [
            {
                "field_name": item.field_name,
                "field_value": item.field_value,
                "field_type": item.field_type,
                "status": item.status,
                "confidence": item.confidence,
                "source": item.source,
                "location": _load_json(item.location),
            }
            for item in data["fields"]
        ],
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "category": finding.category,
                "message": finding.message,
                "details": _load_json(finding.details_json),
            }
            for finding in findings
        ],
        "similarity_candidates": [
            {
                "target_document_id": match.target_document_id,
                "text_similarity": match.text_similarity,
                "edit_similarity": match.edit_similarity,
                "overall_score": match.overall_score,
                "match_type": match.match_type,
                "explanation": match.explanation,
                "field_differences": _load_json(match.field_differences_json),
            }
            for match in matches
        ],
        "structure": data["structure"],
        "algorithms_executed": [
            {
                "algorithm": item.algorithm,
                "input_summary": item.input_summary,
                "execution_time_ms": round(item.execution_time_ms, 4),
                "operation_count": item.operation_count,
                "result_summary": _load_json(item.result_summary_json),
                "created_at": item.created_at.isoformat() + "Z",
            }
            for item in data["algorithm_runs"]
        ],
        "explanation": run.explanation,
        "limitations": LIMITATION_TEXT,
    }


def _branding() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "title": "DocuTrace",
        "subtitle": "Document Verification & Similarity Detection Report",
        "app_version": settings.VERSION,
        "generated_by": "DocuTrace verification pipeline",
    }


def _run_summary(run: VerificationRun) -> Dict[str, Any]:
    return {
        "run_id": run.id,
        "started_at": run.started_at.isoformat() + "Z",
        "completed_at": run.completed_at.isoformat() + "Z" if run.completed_at else None,
        "outcome": run.outcome,
        "validation_status": run.validation_status,
        "duplicate_status": run.duplicate_status,
        "review_recommendation": run.review_recommendation,
        "similarity_score": run.similarity_score,
        "processing_ms": run.processing_ms,
        "template_id": run.template_id,
    }


def _document_metadata(document: Optional[Document]) -> Dict[str, Any]:
    if document is None:
        return {}
    return {
        "document_id": document.id,
        "filename": document.filename,
        "stored_name": document.stored_name,
        "mime_type": document.mime_type,
        "file_size_bytes": document.file_size,
        "file_sha256": document.file_sha256,
        "normalized_text_hash": document.normalized_text_hash,
        "doc_type": document.doc_type,
        "upload_status": document.upload_status,
        "validation_status": document.validation_status,
        "duplicate_status": document.duplicate_status,
        "similarity_score": document.similarity_score,
        "page_count": document.page_count,
        "extraction_method": document.extraction_method,
        "extraction_confidence": document.extraction_confidence,
        "ocr_used": document.ocr_used,
        "processing_duration_ms": document.processing_duration_ms,
        "uploaded_at": document.uploaded_at.isoformat() + "Z",
    }


def _load_json(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _is_critical(fields: Sequence[Any], name: str) -> bool:
    """A field is critical when the template marked it critical.

    The pipeline records this on the extracted-field source side; when the
    information is unavailable the field is reported as non-critical rather than
    guessed at.
    """
    for item in fields:
        if getattr(item, "field_name", "") == name:
            details = _load_json(getattr(item, "location", None)) or {}
            return bool(details.get("critical", False))
    return False


def render_verification_report(
    db: Any, run: VerificationRun, *, filename: Optional[str] = None
) -> ReportArtifact:
    """Render the verification PDF for ``run`` and return its artifact."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    settings = get_settings()
    styles = _styles()
    data = _gather_verification_data(db, run)
    document: Optional[Document] = data["document"]
    findings: List[VerificationFinding] = data["findings"]
    matches: List[SimilarityMatch] = data["matches"]
    fields = data["fields"]
    algorithm_runs: List[AlgorithmRun] = data["algorithm_runs"]
    structure: Optional[Dict[str, Any]] = data["structure"]

    report_uuid = generate_uuid()
    relative_path = f"verification/{run.id}/{report_uuid}.pdf"
    absolute = settings.report_root / relative_path
    absolute.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(absolute),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"DocuTrace verification report {report_uuid}",
        author="DocuTrace",
        subject=f"Verification of {document.filename if document else run.document_id}",
    )

    story: List[Any] = []

    # ---- 1. Branding ------------------------------------------------------ #
    story.append(Paragraph("DocuTrace", styles["title"]))
    story.append(
        Paragraph(
            "Document Verification &amp; Similarity Detection Report",
            styles["subtitle"],
        )
    )
    story.append(
        _kv_table(
            [
                ("Report ID", report_uuid),
                ("Run ID", run.id),
                ("Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")),
                ("Application", f"DocuTrace {settings.VERSION}"),
                ("Subject", document.filename if document else run.document_id),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))

    # ---- 2. Document metadata --------------------------------------------- #
    story.append(Paragraph("1. Document metadata", styles["h1"]))
    if document is not None:
        story.append(
            _kv_table(
                [
                    ("Filename", document.filename),
                    ("Stored as", document.stored_name),
                    ("Document type", document.doc_type),
                    ("MIME type", document.mime_type or "-"),
                    ("Size", f"{document.file_size:,} bytes"),
                    ("Pages", document.page_count if document.page_count else "-"),
                    ("Extraction", document.extraction_method or "-"),
                    (
                        "Extraction confidence",
                        f"{document.extraction_confidence:.2f}" if document.extraction_confidence is not None else "-",
                    ),
                    ("OCR used", "yes" if document.ocr_used else "no"),
                    ("SHA-256", document.file_sha256 or "-"),
                    ("Normalized-text SHA-256", document.normalized_text_hash or "-"),
                    ("Uploaded", document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
                ],
                styles,
            )
        )
    else:  # pragma: no cover - defensive
        story.append(Paragraph("The source document row is no longer available.", styles["body"]))

    # ---- 3. Verification summary ------------------------------------------ #
    story.append(Paragraph("2. Verification summary", styles["h1"]))
    story.append(
        _kv_table(
            [
                ("Outcome", run.outcome),
                ("Validation status", run.validation_status),
                ("Duplicate status", run.duplicate_status),
                ("Review recommendation", run.review_recommendation),
                (
                    "Similarity score",
                    f"{run.similarity_score:.4f}" if run.similarity_score is not None else "-",
                ),
                ("Processing time", f"{run.processing_ms} ms" if run.processing_ms else "-"),
                ("Rules fired", ", ".join(sorted({f.rule_id for f in findings})) or "none"),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    # ---- 4. Required-field validation ------------------------------------- #
    story.append(Paragraph("3. Required-field validation", styles["h1"]))
    if fields:
        body_rows = [
            (
                item.field_name,
                item.field_type,
                _truncate(item.field_value, 48),
                item.status,
                f"{item.confidence:.2f}",
                item.source,
            )
            for item in fields
        ]
        table = _grid(
            ["Field", "Type", "Value", "Status", "Conf.", "Source"],
            body_rows,
            styles,
            col_widths=[105, 52, 140, 52, 33, 56],
        )
        if table is not None:
            story.append(table)
        else:  # pragma: no cover - defensive
            story.append(Paragraph("No fields were extracted.", styles["body"]))
    else:
        story.append(
            Paragraph(
                "No fields were extracted: no template was applied to this document.",
                styles["body"],
            )
        )
    story.append(Spacer(1, 6))

    # ---- 5. Missing / inconsistent fields --------------------------------- #
    story.append(Paragraph("4. Missing &amp; inconsistent fields", styles["h1"]))
    missing = [item for item in fields if item.status == "missing"]
    invalid = [item for item in fields if item.status == "invalid"]
    not_checked = [item for item in fields if item.status == "not_checked"]
    missing_text = (
        "Missing required fields: "
        + ", ".join(item.field_name for item in missing)
        if missing
        else "Missing required fields: none."
    )
    invalid_text = (
        "Invalid field values: " + ", ".join(item.field_name for item in invalid)
        if invalid
        else "Invalid field values: none."
    )
    not_checked_text = (
        f"Not checked (no template rule): {len(not_checked)} field(s)."
        if not_checked
        else ""
    )
    bullets = _bullets([missing_text, invalid_text, *([not_checked_text] if not_checked_text else [])], styles)
    story.append(bullets if bullets is not None else Paragraph("None.", styles["body"]))

    # ---- 6. Exact duplicate results --------------------------------------- #
    story.append(Paragraph("5. Exact duplicate results", styles["h1"]))
    duplicate_findings = [
        finding for finding in findings if finding.rule_id in {"R003", "R004"}
    ]
    if duplicate_findings:
        story.append(
            _grid(
                ["Rule", "Severity", "Detail"],
                [
                    (finding.rule_id, finding.severity, finding.message)
                    for finding in duplicate_findings
                ],
                styles,
                col_widths=[45, 55, 340],
            )
        )
    else:
        story.append(
            Paragraph(
                "No exact or normalized-text duplicate was found for this document.",
                styles["body"],
            )
        )

    # ---- 7. Similarity candidates ----------------------------------------- #
    story.append(Paragraph("6. Similarity candidates", styles["h1"]))
    if matches:
        story.append(
            _grid(
                ["Target document", "LCS", "Edit", "Overall", "Type"],
                [
                    (
                        match.target_document_id,
                        f"{match.text_similarity:.4f}",
                        f"{match.edit_similarity:.4f}",
                        f"{match.overall_score:.4f}",
                        match.match_type,
                    )
                    for match in matches
                ],
                styles,
                col_widths=[170, 65, 65, 65, 75],
            )
        )
        first = matches[0]
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"Top candidate explanation: {_escape(first.explanation or 'n/a')}",
                styles["body"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No candidate reached the configured similarity threshold.",
                styles["body"],
            )
        )

    # ---- 8. Field-level differences --------------------------------------- #
    story.append(Paragraph("7. Field-level differences", styles["h1"]))
    difference_rows: List[Tuple[Any, ...]] = []
    for match in matches:
        for entry in _load_json(match.field_differences_json) or []:
            difference_rows.append(
                (
                    match.target_document_id,
                    entry.get("field", "?"),
                    _truncate(entry.get("source_value"), 24),
                    _truncate(entry.get("target_value"), 24),
                    "yes" if entry.get("equal") else "no",
                )
            )
    table = _grid(
        ["Against", "Field", "This document", "Matched document", "Equal"],
        difference_rows,
        styles,
        col_widths=[105, 80, 105, 105, 25],
    )
    if table is not None:
        story.append(table)
    else:
        story.append(
            Paragraph("No field-level differences were recorded.", styles["body"])
        )

    # ---- 9. Structural verification --------------------------------------- #
    story.append(Paragraph("8. Structural verification", styles["h1"]))
    if structure:
        validation = structure.get("validation") or {}
        rows = [
            ("Sections present", ", ".join(validation.get("present", [])) or "none"),
            ("Sections missing", ", ".join(validation.get("missing", [])) or "none"),
            (
                "Sections not verified (unreadable structure)",
                ", ".join(structure.get("not_verified_sections", [])) or "none",
            ),
            ("Section order matches template", "yes" if validation.get("order_ok") else "no"),
            ("Detected headings", str(structure.get("node_count", 0))),
            (
                "DFS visited / max depth",
                f"{(structure.get('dfs') or {}).get('visited_count', 0)} / "
                f"{(structure.get('dfs') or {}).get('max_depth', 0)}",
            ),
            (
                "BFS visited / max breadth depth",
                f"{(structure.get('bfs') or {}).get('visited_count', 0)} / "
                f"{(structure.get('bfs') or {}).get('max_depth', 0)}",
            ),
        ]
        story.append(_kv_table(rows, styles))
    else:
        story.append(
            Paragraph(
                "No structural analysis was recorded for this run.", styles["body"]
            )
        )

    # ---- 10. Algorithms executed ------------------------------------------ #
    story.append(Paragraph("9. Algorithms executed (measured)", styles["h1"]))
    if algorithm_runs:
        story.append(
            _grid(
                ["Algorithm", "Input", "Time (ms)", "Operations", "Result"],
                [
                    (
                        item.algorithm,
                        _truncate(item.input_summary, 40),
                        f"{item.execution_time_ms:.4f}",
                        f"{item.operation_count:,}",
                        _truncate(_summarise_json(_load_json(item.result_summary_json)), 40),
                    )
                    for item in algorithm_runs
                ],
                styles,
                col_widths=[95, 110, 55, 60, 100],
            )
        )
        total_ms = sum(item.execution_time_ms for item in algorithm_runs)
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"Total measured algorithm time: {total_ms:.3f} ms across "
                f"{len(algorithm_runs)} recorded executions (time.perf_counter_ns).",
                styles["small"],
            )
        )
    else:
        story.append(
            Paragraph("No algorithm executions were recorded.", styles["body"])
        )

    # ---- 11. Explanation -------------------------------------------------- #
    story.append(Paragraph("10. Explanation", styles["h1"]))
    story.append(
        Paragraph(
            _escape(run.explanation or "No explanation was recorded."),
            styles["body"],
        )
    )

    # ---- 12. Limitations -------------------------------------------------- #
    story.append(Paragraph("11. Limitations &amp; review recommendation", styles["h1"]))
    story.append(Paragraph(_escape(LIMITATION_TEXT), styles["body"]))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"<b>Recommended action:</b> {_escape(run.review_recommendation)}",
            styles["body"],
        )
    )

    def _on_page(canvas, doc_ref) -> None:  # pragma: no cover - rendering hook
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColorRGB(0.35, 0.39, 0.45)
        canvas.drawString(
            18 * mm,
            10 * mm,
            f"DocuTrace {settings.VERSION} | report {report_uuid} | "
            f"automated assessment only — not a determination of authenticity",
        )
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=_on_page,
        onLaterPages=_on_page,
    )
    return ReportArtifact(
        report_uuid=report_uuid,
        relative_path=relative_path,
        absolute_path=absolute,
        report_type=ReportType.VERIFICATION,
        byte_size=absolute.stat().st_size,
        section_titles=list(REPORT_SECTIONS),
    )


def _truncate(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _summarise_json(payload: Any) -> str:
    if payload is None:
        return "-"
    if isinstance(payload, dict):
        return ", ".join(f"{key}={value}" for key, value in list(payload.items())[:3])
    return str(payload)


def save_json_payload(payload: Dict[str, Any], relative_path: str) -> Path:
    """Write a JSON payload under the report root and return its absolute path."""
    settings = get_settings()
    absolute = settings.report_root / relative_path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return absolute


def persist_report_row(
    db: Any,
    artifact: ReportArtifact,
    *,
    run_id: Optional[str] = None,
    document_id: Optional[str] = None,
    comparison_id: Optional[str] = None,
    report_type: str = ReportType.VERIFICATION,
) -> GeneratedReport:
    """Insert the ``generated_reports`` row for a rendered artifact."""
    row = GeneratedReport(
        run_id=run_id,
        document_id=document_id,
        comparison_id=comparison_id,
        report_uuid=artifact.report_uuid,
        report_type=report_type,
        relative_path=artifact.relative_path,
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# Comparison report (stateless)
# --------------------------------------------------------------------------- #
def comparison_report_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the JSON export of a comparison payload (no database access)."""
    comparison = payload.get("comparison") or payload
    return {
        "report_type": "comparison",
        "report_uuid": generate_uuid(),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sections": list(COMPARISON_SECTIONS),
        "branding": _branding(),
        "source_document": payload.get("source_document"),
        "target_document": payload.get("target_document"),
        "comparison": comparison,
        "limitations": LIMITATION_TEXT,
    }


def render_comparison_report(
    payload: Dict[str, Any], *, comparison_id: Optional[str] = None
) -> ReportArtifact:
    """Render a comparison PDF from a client-supplied comparison payload.

    This function is **stateless**: everything it needs is in ``payload`` (the
    response of ``POST /api/compare``). That is what makes the comparison export
    usable from a front-end that holds the comparison result but has not stored
    it, and it also means the export cannot accidentally re-run an algorithm and
    disagree with the comparison the user is looking at.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    settings = get_settings()
    styles = _styles()
    comparison = payload.get("comparison") or payload
    source = payload.get("source_document") or {}
    target = payload.get("target_document") or {}

    report_uuid = generate_uuid()
    relative_path = f"comparison/{report_uuid}.pdf"
    absolute = settings.report_root / relative_path
    absolute.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(absolute),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"DocuTrace comparison report {report_uuid}",
        author="DocuTrace",
        subject="Document-to-document comparison report",
    )

    story: List[Any] = []
    story.append(Paragraph("DocuTrace", styles["title"]))
    story.append(
        Paragraph("Document Comparison Report", styles["subtitle"])
    )
    story.append(
        _kv_table(
            [
                ("Report ID", report_uuid),
                ("Comparison ID", comparison_id or "-"),
                ("Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")),
                (
                    "Documents",
                    f"{source.get('filename', source.get('id', '?'))} vs "
                    f"{target.get('filename', target.get('id', '?'))}",
                ),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))

    # ---- Similarity summary ------------------------------------------------ #
    story.append(Paragraph("1. Similarity summary", styles["h1"]))
    story.append(
        _kv_table(
            [
                ("LCS similarity", _score(comparison, "text_similarity")),
                ("Edit similarity", _score(comparison, "edit_similarity")),
                ("Overall score", _score(comparison, "overall_score")),
                ("LCS length (tokens)", _value(comparison, "lcs_length")),
                ("Edit distance (tokens)", _value(comparison, "edit_distance")),
                ("Words added", _value(comparison, "words_added")),
                ("Words removed", _value(comparison, "words_removed")),
                ("Words unchanged", _value(comparison, "words_unchanged")),
                ("Substitutions", _value(comparison, "substitutions")),
                ("Verdict", _similarity_verdict(comparison)),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    # ---- Documents -------------------------------------------------------- #
    story.append(Paragraph("2. Documents", styles["h1"]))
    story.append(
        _grid(
            ["", "Document A", "Document B"],
            [
                ("Filename", source.get("filename"), target.get("filename")),
                ("Document type", source.get("doc_type"), target.get("doc_type")),
                ("Pages", source.get("page_count"), target.get("page_count")),
                (
                    "Extraction confidence",
                    source.get("extraction_confidence"),
                    target.get("extraction_confidence"),
                ),
                ("OCR used", source.get("ocr_used"), target.get("ocr_used")),
                (
                    "SHA-256",
                    _truncate(source.get("file_sha256"), 24),
                    _truncate(target.get("file_sha256"), 24),
                ),
            ],
            styles,
            col_widths=[130, 155, 155],
        )
    )
    story.append(Spacer(1, 6))

    # ---- Token diff ------------------------------------------------------- #
    story.append(Paragraph("3. Token differences", styles["h1"]))
    insertions = comparison.get("insertions") or []
    deletions = comparison.get("deletions") or []
    replacements = comparison.get("replacements") or []
    story.append(
        Paragraph(
            f"<b>Words added</b> ({len(insertions)}): "
            f"{_escape(', '.join(str(token) for token in insertions[:40]) or 'none')}",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Words removed</b> ({len(deletions)}): "
            f"{_escape(', '.join(str(token) for token in deletions[:40]) or 'none')}",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Replacements</b> ({len(replacements)}): "
            f"{_escape(_format_replacements(replacements[:20]) or 'none')}",
            styles["body"],
        )
    )

    # ---- Field differences ------------------------------------------------ #
    story.append(Paragraph("4. Field-level differences", styles["h1"]))
    field_rows = [
        (
            entry.get("field", "?"),
            _truncate(entry.get("source_value"), 28),
            _truncate(entry.get("target_value"), 28),
            "yes" if entry.get("equal") else "no",
            "yes" if entry.get("critical") else "no",
        )
        for entry in (comparison.get("field_differences") or [])
    ]
    table = _grid(
        ["Field", "Document A", "Document B", "Equal", "Critical"],
        field_rows,
        styles,
        col_widths=[105, 130, 130, 45, 45],
    )
    if table is not None:
        story.append(table)
    else:
        story.append(Paragraph("No shared fields were compared.", styles["body"]))

    # ---- Structure -------------------------------------------------------- #
    story.append(Paragraph("5. Structure comparison", styles["h1"]))
    structure = comparison.get("structure")
    if structure:
        story.append(
            _kv_table(
                [
                    ("Identical", "yes" if structure.get("identical") else "no"),
                    ("Only in A", ", ".join(structure.get("only_in_a", [])) or "none"),
                    ("Only in B", ", ".join(structure.get("only_in_b", [])) or "none"),
                    ("Common sections", ", ".join(structure.get("common", [])) or "none"),
                    (
                        "Reordered sections (inversions)",
                        _value(structure, "inversion_count"),
                    ),
                    (
                        "Normalized reorder score",
                        _value(structure, "normalized_reorder_score"),
                    ),
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph("No structural comparison was performed.", styles["body"])
        )

    story.append(Spacer(1, 8))
    story.append(Paragraph(_escape(LIMITATION_TEXT), styles["body"]))

    def _on_page(canvas, doc_ref) -> None:  # pragma: no cover - rendering hook
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColorRGB(0.35, 0.39, 0.45)
        canvas.drawString(
            18 * mm,
            10 * mm,
            f"DocuTrace {settings.VERSION} | comparison report {report_uuid} | "
            f"automated assessment only",
        )
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return ReportArtifact(
        report_uuid=report_uuid,
        relative_path=relative_path,
        absolute_path=absolute,
        report_type=ReportType.COMPARISON,
        byte_size=absolute.stat().st_size,
        section_titles=list(COMPARISON_SECTIONS),
    )


#: Section order of the comparison report.
COMPARISON_SECTIONS: Tuple[str, ...] = (
    "branding",
    "similarity_summary",
    "documents",
    "token_differences",
    "field_level_differences",
    "structure_comparison",
    "limitations",
)


def _score(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return "-"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return "-" if value is None else str(value)


def _format_replacements(replacements: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in replacements:
        old = item.get("old")
        new = item.get("new")
        if old is None and new is None:
            continue
        parts.append(f"{old} -> {new}")
    return "; ".join(parts)


def _similarity_verdict(comparison: Dict[str, Any]) -> str:
    from app.services.similarity import similarity_label

    score = comparison.get("overall_score")
    try:
        return similarity_label(float(score))
    except (TypeError, ValueError):
        return "unknown"


def list_reports(db: Any, limit: int = 100) -> List[GeneratedReport]:
    """Return the most recently generated reports."""
    from sqlalchemy import select

    return list(
        db.execute(
            select(GeneratedReport).order_by(GeneratedReport.created_at.desc()).limit(limit)
        ).scalars()
    )


def resolve_report_path(relative_path: str) -> Path:
    """Resolve a stored ``relative_path`` inside the report root (path-safe)."""
    from app.core.security import resolve_safe_path

    return resolve_safe_path(get_settings().report_root, relative_path)
