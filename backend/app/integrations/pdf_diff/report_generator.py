"""Document Comparison & Modification Analysis Report generator using ReportLab.

Produces a citable, audit-ready PDF report detailing:
- Executive summary & comparison verdict
- Document metadata & cryptographic hashes
- Modified research paper sections
- Granular text additions, deletions, and replacements
- Numerical values, names, dates, and registration numbers altered
- Font family, size, bold, italic, and color differences
- OpenCV-detected visual figure and diagram modifications
- DAA algorithm execution metrics (LCS DP, Levenshtein, Inversion counting)
- Formal compliance and limitation disclaimer
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import get_settings


def _escape(text: Any) -> str:
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    accent = colors.HexColor("#1E293B")
    brand = colors.HexColor("#0284C7")
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            textColor=accent,
            fontName="Helvetica-Bold",
            alignment=0,
            spaceAfter=3,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            textColor=brand,
            fontName="Helvetica-Bold",
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "ReportH1",
            parent=base["Heading1"],
            fontSize=12,
            leading=15,
            textColor=accent,
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "ReportH2",
            parent=base["Heading2"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#334155"),
            fontName="Helvetica-Bold",
            spaceBefore=6,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=base["Normal"],
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#64748B"),
        ),
        "badge": ParagraphStyle(
            "ReportBadge",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.white,
        ),
        "mono": ParagraphStyle(
            "ReportMono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#0F172A"),
        ),
    }


def render_pdf_diff_report(analysis_result: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
    """Render a comprehensive Document Comparison & Modification Analysis Report."""
    settings = get_settings()
    settings.ensure_directories()

    report_id = analysis_result.get("comparison_id") or str(uuid.uuid4())[:8]
    if output_path is None:
        relative_path = f"comparison_reports/docutrace-diff-report-{report_id}.pdf"
        output_path = settings.report_root / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"DocuTrace Document Comparison Report - {report_id}",
        author="DocuTrace Verification Engine",
        subject="Document Comparison & Modification Analysis",
    )

    story: List[Any] = []

    # Title & Header
    story.append(Paragraph("DocuTrace Verification Engine", styles["subtitle"]))
    story.append(
        Paragraph("Document Comparison & Modification Analysis Report", styles["title"])
    )
    story.append(
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | "
            f"Report ID: <b>{report_id}</b> | Engine: pdf-diff + PyMuPDF + OpenCV + DAA",
            styles["small"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

    # Executive Summary & Verdict
    story.append(Paragraph("1. Executive Summary & Verdict", styles["h1"]))
    verdict = analysis_result.get("verdict", "unknown").upper().replace("_", " ")
    summary = analysis_result.get("summary", {})
    daa = analysis_result.get("daa_algorithms", {})

    verdict_color = colors.HexColor("#059669") if "IDENTICAL" in verdict else colors.HexColor("#DC2626")
    if "TYPOGRAPHY" in verdict or "VISUAL" in verdict:
        verdict_color = colors.HexColor("#D97706")

    summary_table_data = [
        [
            Paragraph(f"<b>Overall Assessment Verdict</b>", styles["body"]),
            Paragraph(f"<b><font color='{verdict_color.hexval()}'>{verdict}</font></b>", styles["body"]),
            Paragraph("<b>Total Changes Detected</b>", styles["body"]),
            Paragraph(f"<b>{summary.get('total_changes', 0)}</b>", styles["body"]),
        ],
        [
            Paragraph("LCS Text Similarity", styles["body"]),
            Paragraph(f"{round(daa.get('lcs_similarity', 0.0) * 100, 1)}%", styles["body"]),
            Paragraph("Text Add/Del/Replace", styles["body"]),
            Paragraph(f"{summary.get('text_changes', 0)}", styles["body"]),
        ],
        [
            Paragraph("Edit Similarity (Levenshtein)", styles["body"]),
            Paragraph(f"{round(daa.get('edit_similarity', 0.0) * 100, 1)}%", styles["body"]),
            Paragraph("Numerical / Date Changes", styles["body"]),
            Paragraph(f"{summary.get('numerical_changes', 0) + summary.get('date_changes', 0)}", styles["body"]),
        ],
        [
            Paragraph("Section Inversion Score", styles["body"]),
            Paragraph(f"{daa.get('section_reorder_score', 0.0)} ({daa.get('section_inversions', 0)} inversions)", styles["body"]),
            Paragraph("Font / Visual Changes", styles["body"]),
            Paragraph(f"{summary.get('font_changes', 0)} font / {summary.get('visual_diagram_changes', 0)} diagram", styles["body"]),
        ],
    ]
    t_summary = Table(summary_table_data, colWidths=[120, 120, 140, 95])
    t_summary.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(t_summary)
    story.append(Spacer(1, 8))

    # Document Information
    story.append(Paragraph("2. Document Information", styles["h1"]))
    meta1 = analysis_result.get("source_document", {})
    meta2 = analysis_result.get("target_document", {})

    doc_info_data = [
        ["Attribute", "Original Document (Source)", "Modified Document (Target)"],
        ["Filename", meta1.get("filename", "-"), meta2.get("filename", "-")],
        ["Page Count", str(meta1.get("page_count", "-")), str(meta2.get("page_count", "-"))],
        ["File Size", f"{round(meta1.get('file_size', 0) / 1024, 1)} KB", f"{round(meta2.get('file_size', 0) / 1024, 1)} KB"],
        ["SHA-256 Hash", meta1.get("sha256", "-")[:32] + "...", meta2.get("sha256", "-")[:32] + "..."],
    ]
    t_doc = Table(
        [
            [Paragraph(f"<b>{c}</b>" if idx == 0 else str(c), styles["small"] if "Hash" in r[0] else styles["body"]) for c in r]
            for idx, r in enumerate(doc_info_data)
        ],
        colWidths=[110, 185, 185],
    )
    t_doc.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(t_doc)
    story.append(Spacer(1, 8))

    # Research Paper Sections Analysis
    story.append(Paragraph("3. Modified Research Paper Sections", styles["h1"]))
    sec_analysis = analysis_result.get("section_analysis", {})
    sections_list = sec_analysis.get("sections", [])

    if sections_list:
        sec_rows = [["Section Name", "Status", "Changes", "Words Added", "Words Removed", "Key Evidence"]]
        for s in sections_list:
            status_text = s["status"].upper()
            snippets_str = "; ".join(s["snippets"][:2]) if s["snippets"] else "-"
            sec_rows.append([
                s["section"],
                status_text,
                str(s["changes_count"]),
                str(s["words_added"]),
                str(s["words_removed"]),
                snippets_str[:50] + ("..." if len(snippets_str) > 50 else ""),
            ])
        t_sec = Table(
            [
                [Paragraph(f"<b>{cell}</b>" if r_idx == 0 else str(cell), styles["body"] if c_idx < 5 else styles["small"]) for c_idx, cell in enumerate(row)]
                for r_idx, row in enumerate(sec_rows)
            ],
            colWidths=[115, 65, 45, 55, 55, 145],
        )
        t_sec.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ])
        )
        story.append(t_sec)
    else:
        story.append(Paragraph("No specific section headings were identified.", styles["body"]))
    story.append(Spacer(1, 8))

    # Granular Modifications Table
    story.append(Paragraph("4. Granular Detected Modifications", styles["h1"]))
    changes = analysis_result.get("changes", [])
    if changes:
        mod_rows = [["Pg", "Section", "Category", "Original Text", "Modified Text", "Change Details"]]
        for c in changes[:25]:  # Bounded to top 25 for report readability
            cat = c.get("category", "text").upper()
            rem = c.get("removed_text", "")
            add = c.get("added_text", "")
            desc = c.get("description", "")
            mod_rows.append([
                str(c.get("page", 1)),
                c.get("section", "General")[:15],
                cat[:12],
                rem[:25] + ("…" if len(rem) > 25 else ""),
                add[:25] + ("…" if len(add) > 25 else ""),
                desc[:35] + ("…" if len(desc) > 35 else ""),
            ])
        t_mod = Table(
            [
                [Paragraph(f"<b>{cell}</b>" if r_idx == 0 else _escape(cell), styles["small"]) for cell in row]
                for r_idx, row in enumerate(mod_rows)
            ],
            colWidths=[20, 75, 60, 105, 105, 115],
        )
        t_mod.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ])
        )
        story.append(t_mod)
        if len(changes) > 25:
            story.append(Paragraph(f"<i>... and {len(changes) - 25} more modifications recorded in full analysis payload.</i>", styles["small"]))
    else:
        story.append(Paragraph("No modifications detected.", styles["body"]))
    story.append(Spacer(1, 8))

    # Font & Typographic Differences
    font_changes = [c for c in changes if c.get("type") == "style" or c.get("category") == "font_only"]
    if font_changes:
        story.append(Paragraph("5. Font & Formatting Differences", styles["h1"]))
        font_rows = [["Page", "Section", "Text Content", "Formatting Differences Detected"]]
        for fc in font_changes[:15]:
            fd = fc.get("font_diff") or {}
            diff_parts = []
            for k, v in fd.items():
                if isinstance(v, dict):
                    diff_parts.append(f"{k}: {v.get('original')} -> {v.get('modified')}")
                else:
                    diff_parts.append(f"{k}: {v}")
            font_rows.append([
                str(fc.get("page", 1)),
                fc.get("section", "General"),
                fc.get("removed_text", "")[:35],
                ", ".join(diff_parts)[:60],
            ])
        t_font = Table(
            [
                [Paragraph(f"<b>{cell}</b>" if r_idx == 0 else _escape(cell), styles["small"]) for cell in row]
                for r_idx, row in enumerate(font_rows)
            ],
            colWidths=[30, 90, 160, 200],
        )
        t_font.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ])
        )
        story.append(t_font)
        story.append(Spacer(1, 8))

    # OpenCV Visual & Diagram Modifications
    vis_regions = analysis_result.get("visual_modifications", {}).get("regions", [])
    if vis_regions:
        story.append(Paragraph("6. Visual Figures, Diagrams & Image Modifications (OpenCV)", styles["h1"]))
        vis_rows = [["Page", "Kind", "Severity", "Area (px)", "Description"]]
        for vr in vis_regions[:10]:
            vis_rows.append([
                str(vr.get("page", 1)),
                vr.get("kind", "diagram").upper(),
                vr.get("change_severity", "moderate").upper(),
                str(vr.get("area_pixels", 0)),
                vr.get("description", "-")[:60],
            ])
        t_vis = Table(
            [
                [Paragraph(f"<b>{cell}</b>" if r_idx == 0 else _escape(cell), styles["small"]) for cell in row]
                for r_idx, row in enumerate(vis_rows)
            ],
            colWidths=[30, 65, 65, 60, 260],
        )
        t_vis.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ])
        )
        story.append(t_vis)
        story.append(Spacer(1, 8))

    # DAA Algorithms Executed & Timings
    story.append(Paragraph("7. DAA Algorithmic Verification Details", styles["h1"]))
    alg_list = daa.get("algorithms_executed", [])
    timings = daa.get("timings_ms", {})
    daa_rows = [
        ["Algorithm", "Role / Target", "Time (ms)"],
        ["pdf-diff Bounding Box Alignment", "Text layer alignment & bounding box delta extraction", f"{timings.get('pdf_diff', '-')} ms"],
        ["PyMuPDF Span Typography Engine", "Font family, size, style flag, and hex color comparison", f"{timings.get('pymupdf_typography', '-')} ms"],
        ["OpenCV Visual Differencing", "Page rasterization, contour detection & figure diffing", f"{timings.get('opencv_visual', '-')} ms"],
        ["LCS Dynamic Programming (DAA)", "Token-level longest common subsequence alignment", f"{timings.get('lcs_dp', '-')} ms"],
        ["Levenshtein Distance with Operations", "Character-level substitution, insertion, deletion scripts", f"{timings.get('edit_distance', '-')} ms"],
        ["Inversion Counting Algorithm (DAA)", "Quantifying section order permutation & document reordering", f"{timings.get('inversions', '<1')} ms"],
    ]
    t_daa = Table(
        [
            [Paragraph(f"<b>{cell}</b>" if r_idx == 0 else str(cell), styles["small"]) for cell in row]
            for r_idx, row in enumerate(daa_rows)
        ],
        colWidths=[150, 260, 70],
    )
    t_daa.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(t_daa)
    story.append(Spacer(1, 10))

    # Disclaimer
    story.append(
        Paragraph(
            "<b>Limitations & Compliance:</b> This document comparison and modification analysis report was generated by "
            "deterministic computer algorithms combining the open-source pdf-diff framework (CC0 1.0), PyMuPDF layout analysis, "
            "OpenCV visual computer vision, and DocuTrace DAA algorithms. It measures textual, typographic, and graphic variance. "
            "It does not constitute a legal determination of document authenticity, validity, or authorial intent. A qualified "
            "reviewer must inspect all highlighted evidence.",
            styles["small"],
        )
    )

    def _page_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(14 * mm, 8 * mm, f"DocuTrace {settings.VERSION} | Report {report_id} | Automated Comparison Report")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output_path
