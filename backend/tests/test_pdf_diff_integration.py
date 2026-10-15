"""Integration and unit tests for pdf-diff integration in DocuTrace.

Tests:
1. End-to-end PDF diff analysis between original and modified research paper.
2. Identical text with modified typography / font (Instruction 11).
3. Section modification & reordering detection.
4. Numerical, date, and registration number changes.
5. Visual / diagram modification detection via OpenCV.
6. ReportLab Document Comparison & Modification Analysis Report generation.
7. API endpoints: /api/compare/pdf-diff, page-render, diff-image, and report export.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.integrations.pdf_diff import (
    PDF_DIFF_ATTRIBUTION,
    compute_changes,
    detect_visual_modifications,
    extract_document_sections,
    render_changes,
    render_pdf_diff_report,
    run_pdf_diff_analysis,
)
from app.main import app


def _create_sample_paper(
    filepath: Path,
    *,
    title: str = "Deep Neural Architectures for Document Verification",
    author: str = "Dr. Jane Doe, Dr. Alan Turing",
    font_name: str = "Helvetica",
    body_size: float = 10.0,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    reg_id: str = "REG-2024-8841",
    accuracy: str = "98.4%",
    date_str: str = "October 15, 2024",
    extra_paragraph: str | None = None,
    draw_diagram: bool = False,
    diagram_box: tuple[float, float, float, float] | None = None,
):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(filepath), pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.1, 0.2, 0.4)
    c.drawString(50, height - 60, title)

    # Authors & Registration ID
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(50, height - 80, f"Authors: {author} | Document ID: {reg_id} | Date: {date_str}")

    y = height - 120

    # Section 1: Abstract
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "1. Abstract")
    y -= 18

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, f"This research presents a novel verification framework achieving an accuracy of {accuracy}.")
    y -= 15
    c.drawString(50, y, "The methodology is tested extensively across diverse multi-page datasets.")
    y -= 30

    # Section 2: Introduction
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "2. Introduction")
    y -= 18

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, "Document tampering presents substantial operational risk across academic and financial workflows.")
    y -= 15
    c.drawString(50, y, "Standard OCR approaches often discard formatting and typographic anomalies.")
    y -= 30

    # Section 3: Methodology
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "3. Methodology")
    y -= 18

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, "Our system combines dynamic programming token alignment with computer vision visual diffing.")
    y -= 15
    c.drawString(50, y, "We compute character-level Levenshtein edit scripts for each replaced region.")
    if extra_paragraph:
        y -= 15
        c.drawString(50, y, extra_paragraph)
    y -= 30

    # Section 4: Results
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "4. Results")
    y -= 18

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, f"Experimental evaluation confirms high consistency and measured precision of {accuracy}.")
    y -= 40

    # Optional visual diagram/drawing
    if draw_diagram:
        c.setFillColorRGB(0.2, 0.5, 0.8)
        bx, by, bw, bh = diagram_box or (100, y - 60, 200, 50)
        c.rect(bx, by, bw, bh, fill=1, stroke=1)
        c.setFillColorRGB(1.0, 1.0, 1.0)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(bx + 15, by + 20, "Figure 1: Architectural Flow")

    c.showPage()
    c.save()


class TestPdfDiffIntegration:
    @pytest.fixture
    def test_dir(self, tmp_path):
        return tmp_path / "pdf_diff_test"

    def test_license_attribution(self):
        assert PDF_DIFF_ATTRIBUTION["name"] == "pdf-diff"
        assert "CC0" in PDF_DIFF_ATTRIBUTION["license"]
        assert len(PDF_DIFF_ATTRIBUTION["docutrace_extensions"]) >= 5

    def test_text_and_value_differences(self, test_dir):
        orig_pdf = test_dir / "paper_original.pdf"
        mod_pdf = test_dir / "paper_modified.pdf"

        # Create original with 98.4% accuracy and original ID
        _create_sample_paper(
            orig_pdf,
            accuracy="98.4%",
            reg_id="REG-2024-8841",
            date_str="October 15, 2024",
        )
        # Create modified with 72.1% accuracy and altered ID/date
        _create_sample_paper(
            mod_pdf,
            accuracy="72.1%",
            reg_id="REG-2024-9999",
            date_str="November 20, 2025",
            extra_paragraph="An additional paragraph was appended in the revised paper.",
        )

        result = run_pdf_diff_analysis(orig_pdf, mod_pdf)

        assert result["summary"]["total_changes"] > 0
        assert result["verdict"] in ("critical_data_modified", "content_modified")
        assert result["summary"]["numerical_changes"] >= 1
        assert result["summary"]["date_changes"] >= 1

        # Check section analysis
        sec_names = [s["section"] for s in result["section_analysis"]["sections"]]
        assert "Abstract" in sec_names
        assert "Methodology" in sec_names

        # DAA metrics
        assert result["daa_algorithms"]["lcs_similarity"] > 0.0
        assert result["daa_algorithms"]["edit_similarity"] > 0.0
        assert "lcs_dp" in result["daa_algorithms"]["algorithms_executed"]
        assert "edit_distance" in result["daa_algorithms"]["algorithms_executed"]

    def test_identical_text_different_font(self, test_dir):
        """Instruction 11: text remains identical but font changes."""
        orig_pdf = test_dir / "font_original.pdf"
        mod_pdf = test_dir / "font_modified.pdf"

        # Both PDFs have exactly the same text, but different font family and size
        _create_sample_paper(
            orig_pdf,
            font_name="Helvetica",
            body_size=10.0,
            fill_color=(0.0, 0.0, 0.0),
        )
        _create_sample_paper(
            mod_pdf,
            font_name="Times-Roman",
            body_size=12.0,
            fill_color=(0.1, 0.1, 0.6),  # Also altered color
        )

        result = run_pdf_diff_analysis(orig_pdf, mod_pdf)

        # Content is textually identical or has font modifications
        assert result["summary"]["font_changes"] > 0
        font_changes = [c for c in result["changes"] if c["category"] == "font_only"]
        assert len(font_changes) > 0

        # Check that font diff contains font family or size details
        first_font_change = font_changes[0]
        assert first_font_change["font_diff"] is not None

    def test_visual_diagram_modification(self, test_dir):
        orig_pdf = test_dir / "diagram_orig.pdf"
        mod_pdf = test_dir / "diagram_mod.pdf"

        _create_sample_paper(orig_pdf, draw_diagram=True, diagram_box=(100, 300, 200, 60))
        # Modify diagram position and dimensions
        _create_sample_paper(mod_pdf, draw_diagram=True, diagram_box=(150, 280, 250, 90))

        vis = detect_visual_modifications(str(orig_pdf), str(mod_pdf))
        assert vis["visual_modifications_detected"] is True
        assert vis["region_count"] > 0

    def test_report_generation(self, test_dir):
        orig_pdf = test_dir / "report_orig.pdf"
        mod_pdf = test_dir / "report_mod.pdf"

        _create_sample_paper(orig_pdf, accuracy="95.0%")
        _create_sample_paper(mod_pdf, accuracy="89.5%")

        analysis = run_pdf_diff_analysis(orig_pdf, mod_pdf)
        out_report = test_dir / "test_diff_report.pdf"

        generated_path = render_pdf_diff_report(analysis, output_path=out_report)
        assert generated_path.exists()
        assert generated_path.stat().st_size > 1000

    def test_api_pdf_diff_direct_upload(self, test_dir):
        client = TestClient(app)
        orig_pdf = test_dir / "api_orig.pdf"
        mod_pdf = test_dir / "api_mod.pdf"

        _create_sample_paper(orig_pdf, accuracy="99.1%")
        _create_sample_paper(mod_pdf, accuracy="88.2%")

        with open(orig_pdf, "rb") as f1, open(mod_pdf, "rb") as f2:
            response = client.post(
                "/api/compare/pdf-diff",
                files={
                    "original_file": ("api_orig.pdf", f1, "application/pdf"),
                    "modified_file": ("api_mod.pdf", f2, "application/pdf"),
                },
                data={"render_image": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "comparison_id" in data
        assert "summary" in data
        assert "changes" in data
        assert "section_analysis" in data
        assert "daa_algorithms" in data
        assert data["summary"]["total_changes"] > 0

        # Test page render endpoint
        source_id = data["source_document"]["id"]
        res_page = client.get(f"/api/compare/page-render/{source_id}/1")
        assert res_page.status_code == 200
        assert res_page.headers["content-type"] == "image/png"

        # Test diff report export endpoint
        res_report = client.post("/api/compare/pdf-diff/report", json=data)
        assert res_report.status_code == 200
        assert res_report.headers["content-type"] == "application/pdf"
