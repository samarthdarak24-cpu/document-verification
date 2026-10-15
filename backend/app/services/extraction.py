"""Text extraction from PDF, DOCX, image and plain-text documents.

Design rules (mirrored in the pipeline contract)
------------------------------------------------
1. **Never crash on a corrupt file.** Every backend library call is wrapped; a
   failure raises :class:`ServiceError`, which the pipeline turns into
   ``upload_status="failed"`` with the message persisted.
2. **OCR is best-effort.** Tesseract is an *optional system dependency*. The
   availability probe runs once (``pytesseract.get_tesseract_version()``) and is
   memoised; when the binary is missing every OCR call degrades to a recorded
   warning instead of raising. A missing Tesseract therefore still yields a
   fully processed document, just with ``ocr_used=False`` and a warning.
3. **Honest confidence.** Native text extraction is deterministic and exact
   (``1.0``); OCR is a recognition step and is scored ``0.75``. The aggregate
   confidence is a text-length weighted mean of the per-page confidences, so a
   90%-OCR document cannot claim the confidence of a native-text one.
4. **Sparse-page detection.** A PDF page whose extracted text is shorter than
   ``OCR_MIN_CHARS_PER_PAGE`` is an OCR *candidate* — that is the signature of a
   scanned page embedded in an otherwise digital PDF.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import get_settings
from app.services import ServiceError

# --------------------------------------------------------------------------- #
# Confidence constants (see module docstring, rule 3)
# --------------------------------------------------------------------------- #
NATIVE_CONFIDENCE = 1.0
OCR_CONFIDENCE = 0.75
IMAGE_OCR_CONFIDENCE = 0.75
#: A sparse page that keeps a few native characters but could not be OCR'd. This
#: is *not* a native-text page, so it must not claim native certainty — the few
#: characters are a stray run on a scan and the rest of the page is a bitmap.
SPARSE_NATIVE_CONFIDENCE = 0.5
PLAIN_TEXT_CONFIDENCE = 1.0

#: Method labels reported per page.
METHOD_NATIVE = "native"
METHOD_OCR = "ocr"
METHOD_IMAGE_OCR = "image_ocr"
METHOD_DOCX = "docx"
METHOD_PLAIN = "plain"

#: DPI used when rasterising a PDF page for OCR.
_OCR_DPI = 200

#: Hard cap on OCR input size: a page rendered at 200dpi is ~1.7MB of pixels,
#: and OCR on a 100-page scan would otherwise block the request thread.
_MAX_OCR_PAGES = 50

#: Well-known locations for the Tesseract binary, used as a last-resort probe
#: when ``TESSERACT_CMD`` is unset and the binary is not on the shell PATH
#: (a fresh Windows install only adds PATH for *new* shells, so a running
#: server frequently cannot see it). ``shutil.which`` is tried first.
if sys.platform.startswith("win"):
    _PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")
    _PROGRAM_FILES_X86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    _TESSERACT_CANDIDATE_PATHS: List[str] = [
        str(Path(_PROGRAM_FILES) / "Tesseract-OCR" / "tesseract.exe"),
        str(Path(_PROGRAM_FILES_X86) / "Tesseract-OCR" / "tesseract.exe"),
        str(Path.home() / "AppData" / "Local" / "Tesseract-OCR" / "tesseract.exe"),
    ]
else:
    _TESSERACT_CANDIDATE_PATHS = [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ]


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class PageText:
    """One page's (or one image's) extracted text plus how it was obtained."""

    page: int
    text: str
    method: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "text": self.text,
            "method": self.method,
            "confidence": self.confidence,
        }


@dataclass
class Heading:
    """A heading detected during extraction (used by the structure service)."""

    text: str
    level: int
    page: int
    method: str  # "all_caps" | "numbered" | "docx_style"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "level": self.level,
            "page": self.page,
            "method": self.method,
        }


@dataclass
class ExtractionResult:
    """Everything the pipeline needs from the extraction stage."""

    full_text: str
    pages: List[PageText]
    method: str
    ocr_used: bool
    confidence: float
    warnings: List[str] = field(default_factory=list)
    tables: Optional[List[Dict[str, Any]]] = None
    headings: List[Heading] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    page_count: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_text": self.full_text,
            "pages": [page.to_dict() for page in self.pages],
            "method": self.method,
            "ocr_used": self.ocr_used,
            "confidence": round(self.confidence, 4),
            "warnings": list(self.warnings),
            "tables": list(self.tables) if self.tables is not None else None,
            "headings": [heading.to_dict() for heading in self.headings],
            "metadata": dict(self.metadata),
            "page_count": self.page_count,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


# --------------------------------------------------------------------------- #
# OCR availability probe
# --------------------------------------------------------------------------- #
def _discover_tesseract_cmd() -> str:
    """Locate a Tesseract binary when ``TESSERACT_CMD`` is unset.

    Tries the shell PATH first (``shutil.which``), then the well-known install
    directories from ``_TESSERACT_CANDIDATE_PATHS``. Returns the first existing
    path, or ``""`` when none is found. This is what keeps OCR working even if
    the ``.env`` was not written or the user never set ``TESSERACT_CMD`` — the
    binary is simply discovered from its standard location.
    """
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in _TESSERACT_CANDIDATE_PATHS:
        if Path(candidate).exists():
            return candidate
    return ""


def _configure_tesseract_cmd() -> str:
    """Point ``pytesseract`` at a Tesseract binary.

    Resolution order:

    1. ``TESSERACT_CMD`` from configuration (explicit, independent of PATH) — the
       value written by ``scripts/setup_ocr.py``.
    2. Otherwise, a binary discovered from the shell PATH or the standard install
       directories (a fresh Windows install only adds PATH for *new* shells).

    Returns the path that was configured (empty string when none was found, in
    which case pytesseract falls back to the bare ``"tesseract"`` on PATH).
    """
    configured = (get_settings().TESSERACT_CMD or "").strip()
    if not configured:
        configured = _discover_tesseract_cmd()
    if not configured:
        return ""
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = configured
    except Exception:  # pragma: no cover - pytesseract missing is handled elsewhere
        pass
    return configured


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    """Return ``True`` when a Tesseract binary answers on this machine."""
    return ocr_status()[0]


@lru_cache(maxsize=1)
def ocr_status() -> Tuple[bool, str]:
    """Return ``(available, reason)`` for OCR.

    The reason is what makes the rule-engine warning actionable: "the Python
    client is missing", "the Tesseract binary is not installed / not on PATH",
    or "the configured TESSERACT_CMD does not exist". Previously this probe
    returned a bare boolean, so the extractor could only say "OCR is not
    installed" no matter which of those was true.
    """
    configured = _configure_tesseract_cmd()
    if configured and not Path(configured).exists():
        return False, (
            f"TESSERACT_CMD is set to {configured!r} but that file does not "
            "exist. Install Tesseract or correct the path."
        )

    try:
        import pytesseract  # noqa: F401  (import itself can fail if not installed)
    except Exception as exc:
        return False, f"The pytesseract OCR client could not be imported: {exc}"

    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        name = type(exc).__name__
        if configured:
            return False, (
                f"Tesseract at {configured!r} did not answer ({name}). It may be "
                "corrupt or not executable."
            )
        return False, (
            "The Tesseract binary is not installed or not on PATH "
            f"({name}). Install it, or set TESSERACT_CMD to its full path."
        )
    return True, ""


def reset_ocr_cache() -> None:
    """Clear the memoised OCR probe (used by the tests that simulate both paths)."""
    ocr_available.cache_clear()
    ocr_status.cache_clear()


def ocr_warning_suffix() -> str:
    """The warning text appended when OCR is unavailable, with the reason."""
    reason = ocr_status()[1]
    if reason:
        return f"OCR unavailable: {reason}"
    return (
        "Tesseract OCR is not installed on this machine; pages/images that "
        "required OCR were processed without it. Install the Tesseract binary "
        "(e.g. 'apt install tesseract-ocr' / 'choco install tesseract') to enable "
        "text recovery for scanned documents."
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _weighted_confidence(pages: Sequence[PageText]) -> float:
    """Length-weighted mean of per-page confidences (see module docstring)."""
    total_weight = 0
    total = 0.0
    for page in pages:
        weight = len(page.text.strip())
        total_weight += weight
        total += page.confidence * weight
    if total_weight == 0:
        # No text at all: report the lowest confidence we observed rather than
        # a misleading 1.0.
        confidences = [page.confidence for page in pages]
        return min(confidences) if confidences else 0.0
    return total / total_weight


def _finalize(
    pages: List[PageText],
    pages_by_method: Dict[str, int],
    warnings: List[str],
    tables: Optional[List[Dict[str, Any]]],
    headings: List[Heading],
    metadata: Dict[str, Any],
    ocr_used: bool,
    elapsed_ms: float,
) -> ExtractionResult:
    """Assemble an :class:`ExtractionResult` from per-page pieces."""
    if ocr_used:
        method = "pdf_ocr"
    elif METHOD_IMAGE_OCR in pages_by_method:
        method = "image_ocr"
    elif METHOD_OCR in pages_by_method:
        method = "pdf_ocr"
    elif METHOD_DOCX in pages_by_method:
        method = "docx"
    elif METHOD_PLAIN in pages_by_method:
        method = "text"
    elif pages_by_method.get(METHOD_NATIVE):
        method = "pdf_native"
    else:
        method = "empty"

    full_text = "\n\n".join(
        page.text for page in pages if page.text.strip()
    ).strip()
    return ExtractionResult(
        full_text=full_text,
        pages=list(pages),
        method=method,
        ocr_used=ocr_used,
        confidence=_weighted_confidence(pages),
        warnings=list(warnings),
        tables=tables,
        headings=list(headings),
        metadata=dict(metadata),
        page_count=len(pages),
        elapsed_ms=elapsed_ms,
    )


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _looks_like_heading(line: str) -> Optional[str]:
    """Return the heuristic name if ``line`` looks like a PDF heading.

    Two conservative rules only (false positives are worse than no headings,
    because the structure service must never invent sections):

    * ALL-CAPS line of 3..60 characters with no trailing sentence punctuation;
    * a numbered section line such as ``"3. Methodology"`` or ``"IV. Results"``.

    Returns ``"all_caps"``, ``"numbered"`` or ``None``.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    letters = [ch for ch in stripped if ch.isalpha()]
    if len(letters) < 3:
        return None
    if stripped[-1] in ".,;:!?":
        return None
    if all(ch.isupper() for ch in letters) and len(letters) >= 3:
        # Ignore pure tokens like "GST" that carry no section meaning by
        # requiring at least two words or a trailing marker.
        if len(stripped.split()) >= 2 or ":" in stripped:
            return "all_caps"
    head = stripped.split(".")[0].strip()
    if head and (head.isdigit() or (len(head) <= 4 and head.upper() == head)):
        if len(stripped.split()) >= 2:
            return "numbered"
    return None


def _render_page_for_ocr(page: Any) -> Optional[Any]:
    """Rasterise a PDF page to a PIL image, or return ``None`` on failure."""
    try:
        import pymupdf
        from PIL import Image

        pixmap = page.get_pixmap(dpi=_OCR_DPI)
        if pixmap.alpha:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    except Exception:
        return None


def _ocr_image(image: Any) -> Tuple[str, Optional[str]]:
    """Run Tesseract on ``image``.

    Returns ``(text, warning)``. Any failure (missing binary, unreadable image)
    is reported as a warning with empty text — OCR must never propagate an
    exception to the caller.
    """
    try:
        import pytesseract
    except Exception as exc:  # pragma: no cover - pytesseract is a declared dep
        return "", f"pytesseract import failed: {exc}"
    if not ocr_available():
        return "", ocr_warning_suffix()
    try:
        text = pytesseract.image_to_string(image)
    except Exception as exc:
        return "", f"OCR failed on this page and was skipped ({exc})."
    return (text or ""), None


def extract_pdf(path: Path) -> ExtractionResult:
    """Extract text from a PDF with PyMuPDF, OCR-ing sparse pages."""
    started = time.perf_counter()
    settings = get_settings()
    min_chars = settings.OCR_MIN_CHARS_PER_PAGE
    warnings: List[str] = []
    pages: List[PageText] = []
    headings: List[Heading] = []
    metadata: Dict[str, Any] = {}
    tables: Optional[List[Dict[str, Any]]] = None
    ocr_used = False
    method_counts: Dict[str, int] = {}

    try:
        import pymupdf
    except Exception as exc:  # pragma: no cover - declared dependency
        raise ServiceError(f"PyMuPDF is unavailable: {exc}", "extractor_unavailable")

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        raise ServiceError(
            f"Could not open PDF {path.name!r}: {exc}", "corrupt_pdf"
        )

    try:
        metadata = {
            "title": (document.metadata or {}).get("title", "") or "",
            "author": (document.metadata or {}).get("author", "") or "",
            "producer": (document.metadata or {}).get("producer", "") or "",
            "format": "pdf",
            "is_encrypted": bool(getattr(document, "is_encrypted", False)),
        }

        # Span-level layout metadata (font / size / style flags / colour /
        # position). Bounded and best-effort: only the *summary* is attached
        # here so every document carries a typography fingerprint, while the
        # full span list is served on demand by
        # ``GET /documents/{id}/pdf-metadata``. A failure here must never affect
        # text extraction, so the whole block is guarded.
        try:
            from app.services.pdf_metadata import extract_span_metadata

            span_metadata = extract_span_metadata(document, max_spans_per_page=1000)
            summary = span_metadata.style_summary()
            metadata["pdf_metadata"] = {
                "page_count": span_metadata.page_count,
                "span_count": span_metadata.span_count,
                "fonts": summary["fonts"],
                "sizes": summary["sizes"],
                "colors": summary["colors"],
                "styles": summary["styles"],
            }
            if span_metadata.warnings:
                metadata["pdf_metadata"]["warnings"] = list(span_metadata.warnings)
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"Layout metadata extraction skipped: {exc}")

        page_count = int(document.page_count)
        ocr_enabled = settings.OCR_ENABLED
        ocr_pages = 0

        for index in range(page_count):
            try:
                page = document[index]
            except Exception as exc:
                warnings.append(f"Page {index + 1} could not be read: {exc}")
                pages.append(
                    PageText(index + 1, "", METHOD_NATIVE, 0.0)
                )
                continue

            text = ""
            try:
                text = page.get_text() or ""
            except Exception as exc:
                warnings.append(f"Text extraction failed on page {index + 1}: {exc}")

            method = METHOD_NATIVE
            confidence = NATIVE_CONFIDENCE

            if len(text.strip()) < min_chars:
                # Sparse page: try OCR (scanned image inside a digital PDF).
                #
                # The old ``elif text.strip(): keep it as native`` shortcut is
                # gone on purpose. An image-based scan almost always retains one
                # stray native text run (here: the holder's name, 13 characters),
                # so a page can be both sparse *and* non-empty. Treating that as a
                # complete native page reported the whole document as
                # ``pdf_native`` with ``confidence = 1.0`` and no warning — every
                # field then came back "missing" with no explanation. OCR is
                # attempted first, and when it cannot help the page's confidence
                # is downgraded so the shortfall surfaces in the run.
                image = None
                if ocr_pages >= _MAX_OCR_PAGES:
                    warnings.append(
                        f"OCR skipped on page {index + 1}: the per-document OCR "
                        f"page cap of {_MAX_OCR_PAGES} was reached."
                    )
                elif ocr_enabled:
                    image = _render_page_for_ocr(page)

                if image is not None:
                    ocr_text, ocr_warning = _ocr_image(image)
                    if ocr_warning:
                        warnings.append(f"Page {index + 1} OCR: {ocr_warning}")
                    if ocr_text.strip():
                        text = ocr_text
                        method = METHOD_OCR
                        confidence = OCR_CONFIDENCE
                        ocr_used = True
                        ocr_pages += 1

                if method == METHOD_NATIVE:
                    if text.strip():
                        # Stray native characters on a page OCR could not read.
                        confidence = SPARSE_NATIVE_CONFIDENCE
                        warnings.append(
                            f"Page {index + 1} yielded only "
                            f"{len(text.strip())} character(s) of text and no OCR "
                            "text was recoverable; the page looks like an "
                            "image-based scan, so extracted fields may be "
                            "incomplete."
                        )
                    elif not ocr_enabled:
                        warnings.append(
                            f"Page {index + 1} has no extractable text and OCR "
                            f"is disabled (OCR_ENABLED=false)."
                        )
                    elif not ocr_available():
                        if ocr_warning_suffix() not in warnings:
                            warnings.append(ocr_warning_suffix())
                    else:
                        warnings.append(
                            f"Page {index + 1} contains no recoverable text "
                            f"(image or empty page)."
                        )

            pages.append(PageText(index + 1, text, method, confidence))
            method_counts[method] = method_counts.get(method, 0) + 1

            for offset, line in enumerate(text.splitlines()):
                heuristic = _looks_like_heading(line)
                if heuristic:
                    headings.append(
                        Heading(
                            text=line.strip(),
                            level=1,
                            page=index + 1,
                            method=heuristic,
                        )
                    )
                    if len(headings) >= 200:  # keep the tree bounded
                        break
    finally:
        try:
            document.close()
        except Exception:  # pragma: no cover - best effort
            pass

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _finalize(
        pages, method_counts, warnings, tables, headings, metadata,
        ocr_used, elapsed_ms,
    )


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def extract_docx(path: Path) -> ExtractionResult:
    """Extract paragraphs, heading styles and tables from a DOCX file."""
    started = time.perf_counter()
    warnings: List[str] = []
    metadata: Dict[str, Any] = {"format": "docx"}
    headings: List[Heading] = []
    tables: List[Dict[str, Any]] = []
    lines: List[str] = []

    try:
        import docx  # python-docx
    except Exception as exc:  # pragma: no cover - declared dependency
        raise ServiceError(f"python-docx is unavailable: {exc}", "extractor_unavailable")

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ServiceError(
            f"Could not open DOCX {path.name!r}: {exc}", "corrupt_docx"
        )

    try:
        core = getattr(document, "core_properties", None)
        if core is not None:
            metadata["title"] = getattr(core, "title", "") or ""
            metadata["author"] = getattr(core, "author", "") or ""
            metadata["created"] = str(getattr(core, "created", "") or "")
    except Exception as exc:  # pragma: no cover - metadata is optional
        warnings.append(f"Could not read DOCX metadata: {exc}")

    # -- paragraphs (with style names, which drive heading detection) -------- #
    style_names: List[str] = []
    try:
        for paragraph in document.paragraphs:
            text = (paragraph.text or "").strip()
            if not text:
                continue
            try:
                style_name = paragraph.style.name if paragraph.style is not None else ""
            except Exception:
                style_name = ""
            style_names.append(style_name or "Normal")
            lines.append(text)
            lowered = style_name.lower()
            level = 0
            if lowered.startswith("heading") or lowered.startswith("toc"):
                try:
                    level = int(style_name.rsplit("Heading", 1)[-1].strip() or 1)
                except Exception:
                    level = 1
            elif lowered == "title":
                level = 1
            if level:
                headings.append(
                    Heading(
                        text=text,
                        level=max(1, min(level, 6)),
                        page=1,
                        method="docx_style",
                    )
                )
    except Exception as exc:
        warnings.append(f"Paragraph extraction stopped early: {exc}")

    metadata["paragraph_count"] = len(lines)
    metadata["style_counts"] = _count_styles(style_names)
    metadata["heading_styles"] = sorted(
        {name for name in style_names if name.lower().startswith("heading")}
    )

    # -- tables -------------------------------------------------------------- #
    try:
        for table_index, table in enumerate(document.tables):
            rows: List[List[str]] = []
            for row in table.rows:
                rows.append([(cell.text or "").strip() for cell in row.cells])
            if not rows:
                continue
            tables.append(
                {
                    "index": table_index,
                    "rows": rows,
                    # The first row is treated as the header when every cell in
                    # it is non-empty (an observation, not an interpretation).
                    "header": rows[0] if all(cell for cell in rows[0]) else [],
                }
            )
            # Keep tables inside the full text so they participate in
            # normalization, similarity and duplicate detection.
            lines.append("")
            for row in rows:
                lines.append(" | ".join(row))
    except Exception as exc:
        warnings.append(f"Table extraction stopped early: {exc}")

    pages = [PageText(1, "\n".join(lines), METHOD_DOCX, NATIVE_CONFIDENCE)]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _finalize(
        pages, {METHOD_DOCX: 1}, warnings, tables, headings, metadata,
        False, elapsed_ms,
    )


def _count_styles(style_names: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for name in style_names:
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def extract_image(path: Path) -> ExtractionResult:
    """OCR a standalone image (PNG/JPEG/GIF/...).

    Pipeline: PIL open -> EXIF transpose (a photo taken sideways would otherwise
    be OCR'd upside down) -> optional grayscale + autocontrast via OpenCV ->
    Tesseract. Preprocessing failures are downgraded to warnings; the raw image
    is still OCR'd.
    """
    started = time.perf_counter()
    warnings: List[str] = []
    settings = get_settings()

    try:
        from PIL import Image, ImageOps
    except Exception as exc:  # pragma: no cover - declared dependency
        raise ServiceError(f"Pillow is unavailable: {exc}", "extractor_unavailable")

    try:
        image = Image.open(str(path))
        image.load()
    except Exception as exc:
        raise ServiceError(
            f"Could not open image {path.name!r}: {exc}", "corrupt_image"
        )

    # EXIF orientation: the phone camera stores rotation as a tag, not pixels.
    try:
        image = ImageOps.exif_transpose(image)
    except Exception as exc:
        warnings.append(f"EXIF transpose skipped: {exc}")

    try:
        prepared = _preprocess_image(image)
    except Exception as exc:
        prepared = image
        warnings.append(f"OpenCV preprocessing skipped ({exc}); used the raw image.")

    metadata: Dict[str, Any] = {
        "format": (image.format or "").lower(),
        "size": [int(image.width), int(image.height)],
        "mode": image.mode,
    }

    text = ""
    confidence = 0.0
    method = METHOD_IMAGE_OCR
    if not settings.OCR_ENABLED:
        warnings.append("OCR is disabled (OCR_ENABLED=false); image text not read.")
    elif not ocr_available():
        warnings.append(ocr_warning_suffix())
    else:
        text, ocr_warning = _ocr_image(prepared)
        if ocr_warning:
            warnings.append(ocr_warning)
        if text.strip():
            confidence = IMAGE_OCR_CONFIDENCE

    pages = [PageText(1, text, method, confidence)]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _finalize(
        pages, {method: 1}, warnings, None, [], metadata, bool(text.strip()),
        elapsed_ms,
    )


def _preprocess_image(image: Any) -> Any:
    """Grayscale + histogram stretch with OpenCV, falling back to the input.

    Grayscale removes colour noise and stretching the histogram (a percentile
    "autocontrast") sharply improves Tesseract's accuracy on phone photos of
    documents. OpenCV is *optional*: when it (or numpy) is missing the original
    image is returned unchanged. The stretch is implemented with numpy rather
    than ``cv2.autocontrast`` because that function is not present in the
    headless builds we target.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except Exception:
        return image

    try:
        rgb = image.convert("RGB")
        array = np.asarray(rgb, dtype=np.uint8)
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        low, high = np.percentile(gray, (2.0, 98.0))
        if high > low:
            stretched = np.clip(
                (gray.astype(np.float32) - low) * (255.0 / (high - low)), 0, 255
            ).astype(np.uint8)
        else:  # flat image: nothing to stretch
            stretched = gray
        return Image.fromarray(stretched)
    except Exception:
        return image


# --------------------------------------------------------------------------- #
# Plain text
# --------------------------------------------------------------------------- #
def extract_plain_text(path: Path) -> ExtractionResult:
    """Read a UTF-8 text file (tolerant of encoding errors and BOMs)."""
    started = time.perf_counter()
    warnings: List[str] = []
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise ServiceError(
            f"Could not read {path.name!r}: {exc}", "unreadable_file"
        )
    # ``utf-8-sig`` transparently drops a BOM; ``replace`` never raises.
    text = raw.decode("utf-8-sig", errors="replace")
    if "\ufffd" in text:
        warnings.append(
            "The file is not valid UTF-8; undecodable bytes were replaced."
        )
    # Plain text has no style metadata, so the same conservative line heuristics
    # used for PDFs apply (ALL-CAPS / numbered section lines).
    headings = [
        Heading(text=line.strip(), level=1, page=1, method=heuristic)
        for line in text.splitlines()
        if (heuristic := _looks_like_heading(line))
    ]
    pages = [PageText(1, text, METHOD_PLAIN, PLAIN_TEXT_CONFIDENCE)]
    metadata = {"format": "text", "bytes": len(raw)}
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _finalize(
        pages, {METHOD_PLAIN: 1}, warnings, None, headings, metadata, False,
        elapsed_ms,
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
#: Extension -> extractor.
_EXTRACTORS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "txt": extract_plain_text,
    "md": extract_plain_text,
    "markdown": extract_plain_text,
    "csv": extract_plain_text,
    "log": extract_plain_text,
    "json": extract_plain_text,
    "png": extract_image,
    "jpg": extract_image,
    "jpeg": extract_image,
    "jif": extract_image,
    "gif": extract_image,
    "bmp": extract_image,
    "tif": extract_image,
    "tiff": extract_image,
    "webp": extract_image,
}


def supported_extensions() -> List[str]:
    """Return every extension the extraction layer can handle."""
    return sorted(_EXTRACTORS)


def extract(path: str | Path) -> ExtractionResult:
    """Extract text from ``path``, dispatching on the file extension.

    Raises
    ------
    ServiceError
        For unsupported extensions and for corrupt/undecodable files.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ServiceError(f"File not found: {file_path}", "file_not_found")
    extension = file_path.suffix.lower().lstrip(".")
    extractor = _EXTRACTORS.get(extension)
    if extractor is None:
        raise ServiceError(
            f"Unsupported file type '.{extension}'. Supported: "
            f"{', '.join(supported_extensions())}.",
            "unsupported_type",
        )
    return extractor(file_path)
