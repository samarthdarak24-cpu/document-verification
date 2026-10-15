"""pdf-diff integration package for DocuTrace.

Incorporates and extends `JoshData/pdf-diff` (CC0 1.0 Universal) with:
- Cross-platform PyMuPDF text & bbox extraction
- High-res PyMuPDF page rasterization
- OpenCV diagram, figure, and stamp visual modification detection
- Research paper section identification & inversion counting
- Semantic entity classification (numbers, dates, registration IDs, names)
- DocuTrace DAA algorithmic similarity analysis (LCS DP, Levenshtein edit distance)
- Automated citable report generation
"""

from app.integrations.pdf_diff.analyzer import run_pdf_diff_analysis
from app.integrations.pdf_diff.core import (
    compute_changes,
    pdf_to_bboxes,
    pdftopng,
    render_changes,
    simplify_changes,
)
from app.integrations.pdf_diff.license import PDF_DIFF_ATTRIBUTION
from app.integrations.pdf_diff.report_generator import render_pdf_diff_report
from app.integrations.pdf_diff.section_analyzer import (
    analyze_section_modifications,
    extract_document_sections,
    find_enclosing_section,
)
from app.integrations.pdf_diff.semantic_classifier import classify_modification
from app.integrations.pdf_diff.visual_diff import detect_visual_modifications

__all__ = [
    "PDF_DIFF_ATTRIBUTION",
    "analyze_section_modifications",
    "classify_modification",
    "compute_changes",
    "detect_visual_modifications",
    "extract_document_sections",
    "find_enclosing_section",
    "pdf_to_bboxes",
    "pdftopng",
    "render_changes",
    "render_pdf_diff_report",
    "run_pdf_diff_analysis",
    "simplify_changes",
]
