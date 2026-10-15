"""Unit tests for :mod:`app.services.pdf_metadata`.

These tests build throwaway PDFs with ReportLab (via the ``tmp_pdf`` fixture) so
the expected typography is known exactly: the fixture draws a 16pt
``Helvetica-Bold`` title and 11pt ``Helvetica`` body lines. Any assertion about
font names, sizes or style flags therefore has a ground truth to check against.
"""

from __future__ import annotations

import pytest

from app.services import ServiceError
from app.services.pdf_metadata import (
    DEFAULT_MAX_SPANS,
    FLAG_BOLD,
    FLAG_ITALIC,
    FLAG_MONOSPACE,
    FLAG_SERIF,
    FLAG_SUPERSCRIPT,
    TextSpan,
    color_to_hex,
    color_to_rgb,
    decode_flags,
    extract_pdf_metadata,
    is_pdf,
)

LINES = [
    "Registration Number: MH/2024/008421",
    "Holder Name: Ananya R. Deshmukh",
    "Date of Issue: 2024-04-12",
]


# --------------------------------------------------------------------------- #
# Flag decoding
# --------------------------------------------------------------------------- #
class TestDecodeFlags:
    def test_all_bits_off(self):
        style = decode_flags(0)
        assert style == {
            "superscript": False,
            "italic": False,
            "serif": False,
            "monospace": False,
            "bold": False,
        }

    def test_bold_only(self):
        # 16 is the bit PyMuPDF sets for bold; the fixture's Helvetica-Bold
        # spans report exactly this value.
        assert decode_flags(FLAG_BOLD)["bold"] is True

    def test_every_individual_bit(self):
        assert decode_flags(FLAG_SUPERSCRIPT)["superscript"] is True
        assert decode_flags(FLAG_ITALIC)["italic"] is True
        assert decode_flags(FLAG_SERIF)["serif"] is True
        assert decode_flags(FLAG_MONOSPACE)["monospace"] is True
        assert decode_flags(FLAG_BOLD)["bold"] is True

    def test_combined_bits(self):
        style = decode_flags(FLAG_BOLD | FLAG_ITALIC)
        assert style["bold"] and style["italic"]
        assert not style["serif"] and not style["monospace"]

    def test_none_is_treated_as_zero(self):
        assert decode_flags(None)["bold"] is False  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
class TestColour:
    def test_black_is_zero_not_none(self):
        # The sentinel -1 means "no colour"; 0 is a real colour (black) and the
        # two must never be conflated.
        assert color_to_hex(0) == "#000000"
        assert color_to_rgb(0) == (0, 0, 0)

    def test_no_colour_sentinel(self):
        assert color_to_hex(-1) is None
        assert color_to_rgb(-1) is None

    def test_rgb_round_trip(self):
        assert color_to_hex(0xFF8800) == "#ff8800"
        assert color_to_rgb(0xFF8800) == (255, 136, 0)

    def test_high_byte_ignored(self):
        # Only the low 24 bits are sRGB; a stray alpha byte must not leak in.
        assert color_to_rgb(0xFF112233) == (0x11, 0x22, 0x33)


# --------------------------------------------------------------------------- #
# Extension gate
# --------------------------------------------------------------------------- #
def test_is_pdf():
    assert is_pdf("a.pdf") and is_pdf("A.PDF")
    assert not is_pdf("a.docx") and not is_pdf("a.png")


# --------------------------------------------------------------------------- #
# Extraction against a real (generated) PDF
# --------------------------------------------------------------------------- #
class TestExtraction:
    def test_page_and_span_counts(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        result = extract_pdf_metadata(path)
        assert result.page_count == 1
        assert result.span_count > 0
        assert len(result.pages) == 1

    def test_fonts_and_sizes_match_the_fixture(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        summary = extract_pdf_metadata(path).style_summary()
        fonts = {item["value"] for item in summary["fonts"]}
        sizes = {item["value"] for item in summary["sizes"]}
        assert "Helvetica-Bold" in fonts
        assert "Helvetica" in fonts
        assert "16" in sizes
        assert "11" in sizes

    def test_bold_span_is_detected(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        result = extract_pdf_metadata(path)
        bold_spans = [span for span in result.all_spans() if span.bold]
        assert bold_spans, "the 16pt Helvetica-Bold title must be flagged bold"
        assert all(span.font == "Helvetica-Bold" for span in bold_spans)

    def test_style_summary_shape(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        summary = extract_pdf_metadata(path).style_summary()
        assert set(summary) == {
            "span_count", "fonts", "sizes", "colors", "styles",
        }
        assert set(summary["styles"]) == {
            "bold", "italic", "serif", "monospace", "superscript",
        }
        assert summary["span_count"] == sum(
            item["count"] for item in summary["fonts"]
        )

    def test_span_carries_position_and_colour(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        result = extract_pdf_metadata(path)
        span = next(s for s in result.all_spans() if s.text.strip())
        assert len(span.bbox) == 4
        assert span.bbox[2] > span.bbox[0]  # x1 > x0
        assert span.bbox[3] > span.bbox[1]  # y1 > y0
        assert span.color_hex is not None
        assert span.page == 1

    def test_text_is_line_aware(self, tmp_pdf):
        # Two adjacent fields on different lines must not fuse into one token.
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        text = extract_pdf_metadata(path).pages[0].text
        assert "Registration Number: MH/2024/008421" in text
        assert "MH/2024/008421Holder" not in text

    def test_to_dict_without_spans_omits_block_detail(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        payload = extract_pdf_metadata(path).to_dict(include_spans=False)
        assert payload["truncated"] is False
        assert "blocks" not in payload["pages"][0]
        assert payload["style_summary"]["span_count"] == payload["span_count"]

    def test_to_dict_with_spans_respects_the_cap(self, tmp_pdf):
        path = tmp_pdf("doc.pdf", "Certificate of Registration", LINES)
        payload = extract_pdf_metadata(path).to_dict(
            include_spans=True, max_spans=2
        )
        emitted = sum(
            len(block["spans"])
            for page in payload["pages"]
            for block in page.get("blocks", [])
        )
        assert emitted <= 2
        assert payload["truncated"] is True

    def test_default_max_spans_is_positive(self):
        assert DEFAULT_MAX_SPANS > 0


# --------------------------------------------------------------------------- #
# Failure modes
# --------------------------------------------------------------------------- #
class TestFailureModes:
    def test_missing_file_raises_service_error(self, tmp_path):
        with pytest.raises(ServiceError) as excinfo:
            extract_pdf_metadata(tmp_path / "nope.pdf")
        assert excinfo.value.code == "file_not_found"

    def test_corrupt_pdf_raises_service_error(self, tmp_path):
        path = tmp_path / "broken.pdf"
        path.write_bytes(b"%PDF-1.4 this is not really a pdf")
        with pytest.raises(ServiceError):
            extract_pdf_metadata(path)


# --------------------------------------------------------------------------- #
# TextSpan helpers
# --------------------------------------------------------------------------- #
def _span(text: str, font="Helvetica", size=10.0, bold=False, **kwargs) -> TextSpan:
    return TextSpan(
        text=text,
        font=font,
        size=size,
        flags=FLAG_BOLD if bold else 0,
        bold=bold,
        italic=kwargs.get("italic", False),
        serif=kwargs.get("serif", False),
        monospace=kwargs.get("monospace", False),
        superscript=kwargs.get("superscript", False),
        color_hex=kwargs.get("color_hex", "#000000"),
        color_rgb=kwargs.get("color_rgb", (0, 0, 0)),
        bbox=kwargs.get("bbox", [0.0, 0.0, 10.0, 10.0]),
        origin=kwargs.get("origin", [0.0, 0.0]),
        page=kwargs.get("page", 1),
        block=kwargs.get("block", 0),
        line=kwargs.get("line", 0),
    )


class TestTextSpan:
    def test_style_signature_excludes_text(self):
        # Two spans with different text but identical appearance must produce
        # the same signature -- that is what makes it usable for comparison.
        a = _span("Registration Number: MH/2024/008421")
        b = _span("Registration Number: MH/2024/008422")
        assert a.style_signature() == b.style_signature()

    def test_style_signature_tracks_appearance(self):
        assert _span("x", bold=True).style_signature() != _span("x").style_signature()
        assert (
            _span("x", font="Courier").style_signature()
            != _span("x", font="Helvetica").style_signature()
        )

    def test_to_dict_is_json_safe(self):
        import json

        payload = _span("hello").to_dict()
        json.dumps(payload)  # must not raise
        assert payload["text"] == "hello"
