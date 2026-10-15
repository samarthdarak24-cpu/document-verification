"""Generate sample original and modified research papers for testing pdf-diff integration."""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def create_research_paper(
    filepath: Path,
    *,
    accuracy: str = "98.4%",
    reg_id: str = "ARXIV-2024-8841",
    date_str: str = "October 15, 2024",
    author: str = "Dr. Alan Turing, Dr. Ada Lovelace",
    font_name: str = "Helvetica",
    body_size: float = 10.0,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    extra_paragraph: str | None = None,
    draw_diagram: bool = True,
    diagram_accent: tuple[float, float, float] = (0.2, 0.5, 0.8),
    diagram_box: tuple[float, float, float, float] = (100, 220, 260, 60),
    diagram_label: str = "Figure 1: Original DAA Architecture",
):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(filepath), pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.08, 0.22, 0.45)
    c.drawString(50, height - 55, "Deep Learning and Deterministic Algorithms for Document Verification")

    # Metadata
    c.setFont("Helvetica", 8.5)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(50, height - 75, f"Authors: {author} | Document Registration ID: {reg_id} | Published: {date_str}")

    y = height - 110

    # Section 1: Abstract
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "1. Abstract")
    y -= 16

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, f"We present a robust verification engine pairing DP token alignment with visual differencing.")
    y -= 14
    c.drawString(50, y, f"Across benchmark tests on multi-source documents, our model yields an empirical accuracy of {accuracy}.")
    y -= 26

    # Section 2: Introduction
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "2. Introduction")
    y -= 16

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, "Document tampering represents a substantial threat across academic admissions and audit workflows.")
    y -= 14
    c.drawString(50, y, "Traditional text-only extraction frequently ignores micro-typographic shifts, font changes, and layout variance.")
    y -= 26

    # Section 3: Methodology
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "3. Methodology")
    y -= 16

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, "Our architecture combines the open-source pdf-diff bounding box tracker with PyMuPDF layout analysis.")
    y -= 14
    c.drawString(50, y, "Computer vision differencing with OpenCV captures altered diagram contours and embedded imagery.")
    if extra_paragraph:
        y -= 14
        c.drawString(50, y, extra_paragraph)
    y -= 26

    # Section 4: Results
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "4. Results")
    y -= 16

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, f"Rigorous empirical evaluation demonstrates measured precision of {accuracy} with sub-second latency.")
    y -= 30

    # Section 5: Conclusion
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(50, y, "5. Conclusion")
    y -= 16

    c.setFont(font_name, body_size)
    c.setFillColorRGB(*fill_color)
    c.drawString(50, y, "The integrated pipeline effectively pinpoints both typographic variance and visual document modifications.")
    y -= 45

    # Visual Diagram / Architectural Flow
    if draw_diagram:
        bx, by, bw, bh = diagram_box
        c.setFillColorRGB(*diagram_accent)
        c.roundRect(bx, by, bw, bh, 6, fill=1, stroke=1)
        c.setFillColorRGB(1.0, 1.0, 1.0)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(bx + bw / 2, by + bh / 2 - 3, diagram_label)

    c.showPage()
    c.save()


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parents[1] / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    orig_path = out_dir / "07_research_paper_original.pdf"
    mod_path = out_dir / "08_research_paper_modified.pdf"

    print("Generating original research paper:", orig_path)
    create_research_paper(
        orig_path,
        accuracy="98.4%",
        reg_id="ARXIV-2024-8841",
        date_str="October 15, 2024",
        author="Dr. Alan Turing, Dr. Ada Lovelace",
        font_name="Helvetica",
        body_size=10.0,
        fill_color=(0.0, 0.0, 0.0),
        diagram_accent=(0.15, 0.45, 0.75),
        diagram_box=(120, 140, 240, 48),
        diagram_label="Figure 1: Original DAA Architecture",
    )

    print("Generating modified research paper:", mod_path)
    create_research_paper(
        mod_path,
        accuracy="72.1%",  # Changed numerical value
        reg_id="ARXIV-2024-9999",  # Changed registration ID
        date_str="November 20, 2025",  # Changed date
        author="Dr. Alan Turing, Dr. John von Neumann",  # Changed name
        font_name="Times-Roman",  # Changed font family
        body_size=11.0,  # Changed font size
        fill_color=(0.1, 0.1, 0.4),  # Changed color
        extra_paragraph="An additional experimental paragraph was appended to Methodology in the revision.",
        diagram_accent=(0.75, 0.25, 0.25),  # Changed diagram visual color & position
        diagram_box=(140, 130, 280, 56),  # Changed diagram size
        diagram_label="Figure 1: Modified Pipeline Architecture",
    )

    print("Research paper samples generated successfully!")
