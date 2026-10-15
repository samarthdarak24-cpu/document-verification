"""Span-level PDF metadata extraction built on PyMuPDF.

Why this module exists
----------------------
DocuTrace's text extraction (:mod:`app.services.extraction`) answers *what does
this document say?* It deliberately throws away the typography. But a large
class of document tampering is invisible in the text alone: a date can be
overprinted in a different font, a registration number can be nudged with a
different point size, a signature block can be recoloured, or a whole field can
be pasted with a different typeface. All of those survive text extraction
untouched but are obvious in the *layout* metadata.

This module recovers that layout metadata from a PDF: for every text span it
records the font name, point size, style flags (bold / italic / serif /
monospace / superscript), colour, and the exact bounding box and origin on the
page. It is the raw material for :mod:`app.services.document_change_detector`.

Design rules (mirrored from the extraction layer)
-------------------------------------------------
1. **Never crash on a corrupt file.** Opening or parsing failures raise
   :class:`ServiceError`; a single unreadable page is downgraded to a warning
   and the remaining pages are still returned.
2. **Bounded output.** A 300-page PDF has hundreds of thousands of spans.
   Callers get a *summary* by default; the full span list is opt-in and capped
   by ``max_spans`` so an API response can never be unbounded.
3. **No interpretation.** A span is reported as a font/size/colour observation.
   This module never decides that a document is forged — that judgement belongs
   to the rule engine, and only ever as a factual "these two spans differ".

The extraction pipeline calls :func:`extract_span_metadata` with the PDF it has
*already opened*, so span metadata costs one extra pass over the pages and no
second file open.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services import ServiceError

# --------------------------------------------------------------------------- #
# PyMuPDF style-flag bitmask (``span["flags"]``)
# --------------------------------------------------------------------------- #
FLAG_SUPERSCRIPT = 1 << 0  # 1
FLAG_ITALIC = 1 << 1       # 2
FLAG_SERIF = 1 << 2        # 4
FLAG_MONOSPACE = 1 << 3    # 8
FLAG_BOLD = 1 << 4         # 16

#: Default cap on the number of spans returned in full detail. The summary is
#: always complete; only the raw span list is bounded.
DEFAULT_MAX_SPANS = 2_000

#: A colour int is 0xRRGGBB; PyMuPDF uses -1 for "no colour set".
_NO_COLOUR = -1


# --------------------------------------------------------------------------- #
# Value helpers
# --------------------------------------------------------------------------- #
def decode_flags(flags: int) -> Dict[str, bool]:
    """Decode a PyMuPDF span ``flags`` bitmask into named style booleans.

    The bit layout is documented in the PyMuPDF text-extraction reference; the
    decoder is written out rather than imported so the mapping is explicit and
    unit-testable.
    """
    flags = int(flags or 0)
    return {
        "superscript": bool(flags & FLAG_SUPERSCRIPT),
        "italic": bool(flags & FLAG_ITALIC),
        "serif": bool(flags & FLAG_SERIF),
        "monospace": bool(flags & FLAG_MONOSPACE),
        "bold": bool(flags & FLAG_BOLD),
    }


def color_to_rgb(color: int) -> Optional[Tuple[int, int, int]]:
    """Convert a PyMuPDF sRGB colour int to an ``(r, g, b)`` tuple.

    Returns ``None`` for the sentinel ``-1`` ("colour not set"), which must not
    be confused with black (``0``).
    """
    value = int(color)
    if value < 0:
        return None
    value &= 0xFFFFFF
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def color_to_hex(color: int) -> Optional[str]:
    """Convert a PyMuPDF sRGB colour int to ``"#rrggbb"`` (or ``None``)."""
    rgb = color_to_rgb(color)
    if rgb is None:
        return None
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _round_bbox(bbox: Sequence[float]) -> List[float]:
    return [round(float(value), 3) for value in bbox]


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class TextSpan:
    """One typographic run: the unit that carries font/size/colour/position."""

    text: str
    font: str
    size: float
    flags: int
    bold: bool
    italic: bool
    serif: bool
    monospace: bool
    superscript: bool
    color_hex: Optional[str]
    color_rgb: Optional[Tuple[int, int, int]]
    bbox: List[float]
    origin: Optional[List[float]]
    page: int
    block: int
    line: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "font": self.font,
            "size": round(self.size, 3),
            "flags": self.flags,
            "bold": self.bold,
            "italic": self.italic,
            "serif": self.serif,
            "monospace": self.monospace,
            "superscript": self.superscript,
            "color_hex": self.color_hex,
            "color_rgb": list(self.color_rgb) if self.color_rgb is not None else None,
            "bbox": list(self.bbox),
            "origin": list(self.origin) if self.origin is not None else None,
            "page": self.page,
            "block": self.block,
            "line": self.line,
        }

    def style_signature(self) -> str:
        """A compact, comparable fingerprint of this span's *appearance*.

        Text is deliberately excluded: the signature answers "would this look
        identical if the text were the same?", which is exactly what the change
        detector needs when comparing two versions of the same field.
        """
        return (
            f"{self.font}|{round(self.size, 2)}|"
            f"{'B' if self.bold else ''}{'I' if self.italic else ''}"
            f"{'S' if self.serif else ''}{'M' if self.monospace else ''}"
            f"{'^' if self.superscript else ''}|{self.color_hex or '-'}"
        )


@dataclass
class TextBlock:
    """A PyMuPDF text block (a paragraph-like grouping of lines/spans)."""

    number: int
    bbox: List[float]
    spans: List[TextSpan] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "bbox": list(self.bbox),
            "spans": [span.to_dict() for span in self.spans],
        }


@dataclass
class PageMetadata:
    """Layout metadata for one page."""

    page: int
    width: float
    height: float
    rotation: int
    text: str
    blocks: List[TextBlock] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def span_count(self) -> int:
        return sum(len(block.spans) for block in self.blocks)

    def to_dict(self, include_spans: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "page": self.page,
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "rotation": self.rotation,
            "block_count": len(self.blocks),
            "span_count": self.span_count,
            "warnings": list(self.warnings),
        }
        if include_spans:
            payload["blocks"] = [block.to_dict() for block in self.blocks]
        return payload


@dataclass
class PdfMetadataResult:
    """Everything the metadata stage produces for one PDF."""

    page_count: int
    metadata: Dict[str, Any]
    is_encrypted: bool
    pages: List[PageMetadata] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    span_count: int = 0
    elapsed_ms: float = 0.0

    def all_spans(self) -> List[TextSpan]:
        """Every span in document order (page, block, line)."""
        return [
            span
            for page in self.pages
            for block in page.blocks
            for span in block.spans
        ]

    def style_summary(self) -> Dict[str, Any]:
        """A bounded, JSON-safe summary of the typography actually used.

        This is what the extraction pipeline stores on every document: a set of
        distinct fonts and sizes, the style counts, and the colour palette —
        small enough to keep on every document, rich enough to spot an
        out-of-place font in the UI.
        """
        fonts: Dict[str, int] = {}
        sizes: Dict[str, int] = {}
        colors: Dict[str, int] = {}
        bold = italic = serif = monospace = superscript = 0
        for span in self.all_spans():
            if not span.text.strip():
                continue
            fonts[span.font] = fonts.get(span.font, 0) + 1
            key = f"{round(span.size, 2):g}"
            sizes[key] = sizes.get(key, 0) + 1
            if span.color_hex:
                colors[span.color_hex] = colors.get(span.color_hex, 0) + 1
            bold += span.bold
            italic += span.italic
            serif += span.serif
            monospace += span.monospace
            superscript += span.superscript

        def _ranked(counts: Dict[str, int]) -> List[Dict[str, Any]]:
            return [
                {"value": value, "count": count}
                for value, count in sorted(
                    counts.items(), key=lambda item: (-item[1], item[0])
                )
            ]

        return {
            "span_count": self.span_count,
            "fonts": _ranked(fonts),
            "sizes": _ranked(sizes),
            "colors": _ranked(colors),
            "styles": {
                "bold": bold,
                "italic": italic,
                "serif": serif,
                "monospace": monospace,
                "superscript": superscript,
            },
        }

    def to_dict(
        self, include_spans: bool = False, max_spans: int = DEFAULT_MAX_SPANS
    ) -> Dict[str, Any]:
        """JSON-serializable form.

        ``include_spans`` is capped at ``max_spans`` overall; ``truncated``
        reports whether the cap was hit so a caller never mistakes a partial
        list for the whole document.
        """
        pages: List[Dict[str, Any]] = []
        emitted = 0
        truncated = False
        for page in self.pages:
            if not include_spans:
                pages.append(page.to_dict(include_spans=False))
                continue
            remaining = max_spans - emitted
            if remaining <= 0:
                truncated = truncated or page.span_count > 0
                pages.append(page.to_dict(include_spans=False))
                continue
            page_payload = page.to_dict(include_spans=False)
            blocks: List[Dict[str, Any]] = []
            for block in page.blocks:
                block_spans = block.spans[: max(0, remaining)]
                emitted += len(block_spans)
                blocks.append(
                    {
                        "number": block.number,
                        "bbox": list(block.bbox),
                        "spans": [span.to_dict() for span in block_spans],
                    }
                )
                remaining = max_spans - emitted
                if remaining <= 0:
                    break
            if emitted < page.span_count:
                truncated = True
            page_payload["blocks"] = blocks
            pages.append(page_payload)

        return {
            "page_count": self.page_count,
            "metadata": dict(self.metadata),
            "is_encrypted": self.is_encrypted,
            "span_count": self.span_count,
            "style_summary": self.style_summary(),
            "warnings": list(self.warnings),
            "pages": pages,
            "include_spans": include_spans,
            "truncated": truncated,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _span_from_raw(
    raw: Dict[str, Any], page: int, block: int, line: int
) -> TextSpan:
    """Build a :class:`TextSpan` from one PyMuPDF span dict."""
    flags = int(raw.get("flags", 0) or 0)
    style = decode_flags(flags)
    color = int(raw.get("color", _NO_COLOUR))
    origin = raw.get("origin")
    return TextSpan(
        text=str(raw.get("text", "") or ""),
        font=str(raw.get("font", "") or ""),
        size=float(raw.get("size", 0.0) or 0.0),
        flags=flags,
        bold=style["bold"],
        italic=style["italic"],
        serif=style["serif"],
        monospace=style["monospace"],
        superscript=style["superscript"],
        color_hex=color_to_hex(color),
        color_rgb=color_to_rgb(color),
        bbox=_round_bbox(raw.get("bbox", (0.0, 0.0, 0.0, 0.0))),
        origin=_round_bbox(origin) if origin else None,
        page=page,
        block=block,
        line=line,
    )


def extract_span_metadata(
    document: Any,
    *,
    max_spans_per_page: Optional[int] = None,
) -> PdfMetadataResult:
    """Extract span metadata from an **already-open** PyMuPDF document.

    This is the entry point used by :func:`app.services.extraction.extract_pdf`,
    which has the document open already. Every page is parsed independently: a
    page whose layout cannot be read is recorded as a warning and skipped, so a
    single malformed page never costs the whole document's metadata.
    """
    started = time.perf_counter()
    warnings: List[str] = []
    pages: List[PageMetadata] = []

    try:
        raw_metadata = dict(document.metadata or {})
    except Exception:  # pragma: no cover - defensive
        raw_metadata = {}

    metadata: Dict[str, Any] = {
        "format": raw_metadata.get("format", "PDF") or "PDF",
        "title": raw_metadata.get("title", "") or "",
        "author": raw_metadata.get("author", "") or "",
        "subject": raw_metadata.get("subject", "") or "",
        "keywords": raw_metadata.get("keywords", "") or "",
        "creator": raw_metadata.get("creator", "") or "",
        "producer": raw_metadata.get("producer", "") or "",
        "creation_date": raw_metadata.get("creationDate", "") or "",
        "mod_date": raw_metadata.get("modDate", "") or "",
    }

    try:
        is_encrypted = bool(getattr(document, "is_encrypted", False))
    except Exception:  # pragma: no cover - defensive
        is_encrypted = False

    try:
        page_count = int(document.page_count)
    except Exception as exc:
        raise ServiceError(f"Could not read the PDF page count: {exc}", "corrupt_pdf")

    total_spans = 0
    for index in range(page_count):
        page_number = index + 1
        try:
            page = document[index]
        except Exception as exc:
            warnings.append(f"Page {page_number} could not be opened: {exc}")
            continue

        try:
            rect = page.rect
            width = float(rect.width)
            height = float(rect.height)
        except Exception:
            width = height = 0.0

        try:
            rotation = int(getattr(page, "rotation", 0) or 0)
        except Exception:
            rotation = 0

        page_warnings: List[str] = []
        blocks: List[TextBlock] = []
        text_lines: List[str] = []

        try:
            raw = page.get_text("dict")
        except Exception as exc:
            page_warnings.append(f"Layout extraction failed: {exc}")
            raw = {"blocks": []}

        emitted = 0
        capped = False
        for block_index, raw_block in enumerate(raw.get("blocks", []) or []):
            # type 0 == text block; type 1 == image block (no spans).
            if int(raw_block.get("type", 0) or 0) != 0:
                continue
            block_spans: List[TextSpan] = []
            for line_index, raw_line in enumerate(raw_block.get("lines", []) or []):
                if capped:
                    break
                line_spans: List[TextSpan] = []
                for raw_span in raw_line.get("spans", []) or []:
                    if max_spans_per_page is not None and emitted >= max_spans_per_page:
                        capped = True
                        break
                    span = _span_from_raw(
                        raw_span, page_number, block_index, line_index
                    )
                    line_spans.append(span)
                    block_spans.append(span)
                    emitted += 1
                if line_spans:
                    # Spans inside a line are contiguous runs, so they join with
                    # no separator; lines join with a newline so two adjacent
                    # fields never fuse into a single token.
                    text_lines.append("".join(span.text for span in line_spans))

            if block_spans:
                blocks.append(
                    TextBlock(
                        number=int(raw_block.get("number", block_index) or block_index),
                        bbox=_round_bbox(raw_block.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                        spans=block_spans,
                    )
                )

        if capped:
            page_warnings.append(
                f"Span list truncated at {max_spans_per_page} spans."
            )

        total_spans += emitted
        pages.append(
            PageMetadata(
                page=page_number,
                width=width,
                height=height,
                rotation=rotation,
                text="\n".join(text_lines),
                blocks=blocks,
                warnings=page_warnings,
            )
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return PdfMetadataResult(
        page_count=page_count,
        metadata=metadata,
        is_encrypted=is_encrypted,
        pages=pages,
        warnings=warnings,
        span_count=total_spans,
        elapsed_ms=elapsed_ms,
    )


def extract_pdf_metadata(
    path: str | Path,
    *,
    max_spans_per_page: Optional[int] = None,
) -> PdfMetadataResult:
    """Open ``path`` with PyMuPDF and extract span-level metadata.

    Raises
    ------
    ServiceError
        When PyMuPDF is unavailable, the file cannot be opened, or the file is
        not a PDF. Individual pages degrade to warnings instead.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ServiceError(f"File not found: {file_path}", "file_not_found")

    try:
        import pymupdf
    except Exception as exc:  # pragma: no cover - declared dependency
        raise ServiceError(f"PyMuPDF is unavailable: {exc}", "extractor_unavailable")

    try:
        document = pymupdf.open(str(file_path))
    except Exception as exc:
        raise ServiceError(
            f"Could not open PDF {file_path.name!r}: {exc}", "corrupt_pdf"
        )

    try:
        return extract_span_metadata(document, max_spans_per_page=max_spans_per_page)
    finally:
        try:
            document.close()
        except Exception:  # pragma: no cover - best effort
            pass


def is_pdf(path: str | Path) -> bool:
    """Cheap extension check used to gate PDF-only endpoints."""
    return Path(path).suffix.lower() == ".pdf"


__all__ = [
    "DEFAULT_MAX_SPANS",
    "FLAG_BOLD",
    "FLAG_ITALIC",
    "FLAG_MONOSPACE",
    "FLAG_SERIF",
    "FLAG_SUPERSCRIPT",
    "PageMetadata",
    "PdfMetadataResult",
    "TextBlock",
    "TextSpan",
    "color_to_hex",
    "color_to_rgb",
    "decode_flags",
    "extract_pdf_metadata",
    "extract_span_metadata",
    "is_pdf",
]
