"""Generate six synthetic certificate samples for the DocuTrace demo.

The six files deliberately exercise every branch of the duplicate-detection and
field-validation logic. Running this script and then uploading the files in
order produces a fully reproducible end-to-end demonstration.

    python scripts/create_sample_documents.py [--outdir samples]

Variants produced
-----------------
1. ``01_certificate_original.pdf``      — the baseline record.
2. ``02_certificate_copy.pdf``          — a byte-identical copy (exact duplicate).
3. ``03_certificate_modified_reg.pdf``  — one character changed in the register
   number (a *critical* field), which makes the document internally
   inconsistent rather than a mere copy.
4. ``04_certificate_missing_date.pdf``  — the issue date is removed (a required
   field is absent).
5. ``05_certificate_reordered.pdf``     — the same sections in a different order
   (structure deviation, no field change).
6. ``06_certificate_alt_labels.pdf``    — alternate but approved field labels
   (exercises the alias table and bipartite matching).

Every value is synthetic. No real person, institution or registration number is
represented.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 22 * mm

# --------------------------------------------------------------------------- #
# Content blocks
# --------------------------------------------------------------------------- #
# Each block is (section_title, [lines]). Keeping the content in a structured
# form (rather than one flat string) is what lets the reordered variant move
# whole sections around while keeping every value identical.
BASE_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Header",
        [
            "CERTIFICATE OF REGISTRATION",
            "Issued under the Societies Registration Act",
        ],
    ),
    (
        "HolderDetails",
        [
            "Holder Name: Ananya R. Deshmukh",
            "Registration Number: MH/2024/008421",
            "Date of Issue: 2024-04-12",
            "Valid Until: 2027-04-11",
        ],
    ),
    (
        "IssuingAuthority",
        [
            "Issuing Authority: State Registrar of Societies",
            "Office: Pune Division, Maharashtra",
            "Contact Number: +91 20 2555 0100",
            "Email: registrar.pune@example.gov.in",
        ],
    ),
    (
        "Declarations",
        [
            "Status: Active",
            "Category: Educational Trust",
            "Purpose: Skill development and vocational training",
        ],
    ),
    (
        "Footer",
        [
            "This certificate is issued electronically and requires no signature.",
            "Verify authenticity at the official portal using the registration number.",
        ],
    ),
]


def _render_sections(
    path: Path,
    sections: list[tuple[str, list[str]]],
    *,
    title: str = "Certificate of Registration",
) -> None:
    """Render one PDF from a list of section blocks."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle(title)
    pdf.setAuthor("DocuTrace sample generator")
    pdf.setSubject("Synthetic sample document — not a real certificate")

    y = PAGE_H - MARGIN
    for section, lines in sections:
        if y < MARGIN + 60:
            pdf.showPage()
            y = PAGE_H - MARGIN
        # Section heading (kept as a heading so structure detection can see it).
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(MARGIN, y, section)
        y -= 15
        pdf.setFont("Helvetica", 10)
        for line in lines:
            pdf.drawString(MARGIN + 10, y, line)
            y -= 14
        y -= 8  # gap between sections

    pdf.showPage()
    pdf.save()


def _without_section(
    sections: list[tuple[str, list[str]]], name: str
) -> list[tuple[str, list[str]]]:
    return [(s, lines) for s, lines in sections if s != name]


def _drop_line(
    sections: list[tuple[str, list[str]]], needle: str
) -> list[tuple[str, list[str]]]:
    """Remove every line containing ``needle`` from every section."""
    cleaned: list[tuple[str, list[str]]] = []
    for section, lines in sections:
        kept = [line for line in lines if needle not in line]
        if kept:
            cleaned.append((section, kept))
    return cleaned


def _replace_line(
    sections: list[tuple[str, list[str]]], old: str, new: str
) -> list[tuple[str, list[str]]]:
    return [
        (section, [new if old in line else line for line in lines])
        for section, lines in sections
    ]


def _reorder(
    sections: list[tuple[str, list[str]]], order: list[str]
) -> list[tuple[str, list[str]]]:
    """Return the sections in ``order``, keeping each block intact.

    The lookup maps a section name to the *whole block* (name + lines), so the
    rendered section keeps its heading.
    """
    index = {section_name: (section_name, lines) for section_name, lines in sections}
    return [index[name] for name in order if name in index]


def _relabel(labels: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Produce the alternate-label variant using the approved alias table."""
    sections = [("Header", BASE_SECTIONS[0][1])]
    holder = []
    for line in BASE_SECTIONS[1][1]:
        for old, new in labels.items():
            if line.startswith(old):
                line = line.replace(old, new, 1)
        holder.append(line)
    sections.append(("HolderDetails", holder))
    authority = []
    for line in BASE_SECTIONS[2][1]:
        for old, new in labels.items():
            if line.startswith(old):
                line = line.replace(old, new, 1)
        authority.append(line)
    sections.append(("IssuingAuthority", authority))
    sections.append(BASE_SECTIONS[3])
    sections.append(BASE_SECTIONS[4])
    return sections


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def create_samples(outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # 1. Original
    original = outdir / "01_certificate_original.pdf"
    _render_sections(original, BASE_SECTIONS)
    created.append(original)

    # 2. Byte-identical copy — copied, not re-rendered, so the SHA-256 matches.
    copy = outdir / "02_certificate_copy.pdf"
    shutil.copyfile(original, copy)
    created.append(copy)

    # 3. One-character change in the critical registration number.
    #    A change inside an *identifier* is what makes a document a modified
    #    record rather than a duplicate, so the engine must not call it a copy.
    modified = outdir / "03_certificate_modified_reg.pdf"
    _render_sections(
        modified,
        _replace_line(BASE_SECTIONS, "MH/2024/008421", "MH/2024/008422"),
    )
    created.append(modified)

    # 4. Missing required field — the issue date is removed entirely.
    missing = outdir / "04_certificate_missing_date.pdf"
    _render_sections(missing, _drop_line(BASE_SECTIONS, "Date of Issue"))
    created.append(missing)

    # 5. Reordered sections — identical values, different structure.
    reordered = outdir / "05_certificate_reordered.pdf"
    _render_sections(
        reordered,
        _reorder(
            BASE_SECTIONS,
            [
                "Header",
                "IssuingAuthority",
                "HolderDetails",
                "Footer",
                "Declarations",
            ],
        ),
    )
    created.append(reordered)

    # 6. Alternate labels that exist in the approved alias table.
    alt = outdir / "06_certificate_alt_labels.pdf"
    _render_sections(
        alt,
        _relabel(
            {
                "Holder Name": "Name of Holder",
                "Registration Number": "Registration No",
                "Date of Issue": "Issue Date",
                "Issuing Authority": "Issued By",
                "Contact Number": "Phone",
            }
        ),
    )
    created.append(alt)

    return created


def describe(paths: list[Path]) -> str:
    lines = ["Generated sample documents:", ""]
    notes = [
        "baseline record — expected: unique",
        "byte-identical copy — expected: exact_duplicate",
        "critical field changed — expected: modified record, not a copy",
        "required field removed — expected: validation failure",
        "sections reordered — expected: structure deviation",
        "approved alternate labels — expected: fields still matched via aliases",
    ]
    for path, note in zip(paths, notes):
        lines.append(f"  {path.name:38} {note}")
    lines.append("")
    lines.append(f"Total: {len(paths)} files in {paths[0].parent}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "samples",
        help="Directory to write the sample PDFs into (default: ./samples).",
    )
    args = parser.parse_args()

    paths = create_samples(args.outdir.resolve())
    print(describe(paths))


if __name__ == "__main__":
    main()
