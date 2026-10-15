"""Core implementation of pdf-diff with PyMuPDF enhancements.

Based on `pdf-diff` by Joshua Tauberer (CC0 1.0 Universal).
Enhanced for DocuTrace with:
1. Cross-platform PyMuPDF text & bounding-box extractor (runs everywhere without Poppler).
2. PyMuPDF-based rasterizer for rendering PDF pages to high-resolution PNG images.
3. Typography attachment (font family, size, color, flags) directly to word boxes.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple

import pymupdf
from PIL import Image, ImageDraw, ImageOps

from app.services.pdf_metadata import color_to_hex, decode_flags


def has_poppler() -> bool:
    """Check if pdftotext and pdftoppm are installed on PATH."""
    return bool(shutil.which("pdftotext") and shutil.which("pdftoppm"))


# --------------------------------------------------------------------------- #
# Bounding box extraction
# --------------------------------------------------------------------------- #
def pdf_to_bboxes_pymupdf(
    pdf_index: int,
    fn: str,
    top_margin: float = 0.0,
    bottom_margin: float = 100.0,
) -> Generator[Dict[str, Any], None, None]:
    """Extract bounding boxes and typographic metadata for words using PyMuPDF.

    Yields dictionaries identical to pdf-diff's expected format, enriched with
    font, size, style flags, and color.
    """
    doc = pymupdf.open(fn)
    box_index = 0
    pdfdict = {
        "index": pdf_index,
        "file": fn,
    }

    try:
        for page_idx, page in enumerate(doc):
            p_width = float(page.rect.width)
            p_height = float(page.rect.height)
            pagedict = {
                "number": page_idx + 1,
                "width": p_width,
                "height": p_height,
            }

            # Extract detailed layout spans to map font info to word boxes
            span_map = []
            try:
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", []):
                    if block.get("type", 0) == 0:  # text
                        for line in block.get("lines", []):
                            for sp in line.get("spans", []):
                                span_map.append(sp)
            except Exception:
                span_map = []

            # Extract words: (x0, y0, x1, y1, word_text, block_no, line_no, word_no)
            words = page.get_text("words")
            for w in words:
                x0, y0, x1, y1, text = float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])
                
                # Filter margins (in % of page height)
                if y1 < (top_margin / 100.0) * p_height:
                    continue
                if y0 > (bottom_margin / 100.0) * p_height:
                    continue

                # Find matching span for font attributes
                font_name = "Helvetica"
                font_size = 10.0
                flags = 0
                color_hex = "#000000"
                bold = False
                italic = False
                
                for sp in span_map:
                    sb = sp.get("bbox", [0, 0, 0, 0])
                    # Check if center of word is within span bbox
                    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                    if sb[0] - 1 <= cx <= sb[2] + 1 and sb[1] - 1 <= cy <= sb[3] + 1:
                        font_name = sp.get("font", font_name)
                        font_size = float(sp.get("size", font_size))
                        flags = int(sp.get("flags", 0))
                        c_raw = int(sp.get("color", -1))
                        color_hex = color_to_hex(c_raw) or "#000000"
                        decoded = decode_flags(flags)
                        bold = decoded["bold"]
                        italic = decoded["italic"]
                        break

                yield {
                    "index": box_index,
                    "pdf": pdfdict,
                    "page": pagedict,
                    "x": x0,
                    "y": y0,
                    "width": x1 - x0,
                    "height": y1 - y0,
                    "text": text,
                    "font": font_name,
                    "size": round(font_size, 2),
                    "flags": flags,
                    "color": color_hex,
                    "bold": bold,
                    "italic": italic,
                }
                box_index += 1
    finally:
        doc.close()


def pdf_to_bboxes_poppler(
    pdf_index: int,
    fn: str,
    top_margin: float = 0.0,
    bottom_margin: float = 100.0,
) -> Generator[Dict[str, Any], None, None]:
    """Original pdf-diff extractor using pdftotext -bbox."""
    from lxml import etree

    box_index = 0
    pdfdict = {
        "index": pdf_index,
        "file": fn,
    }
    xml = subprocess.check_output(["pdftotext", "-bbox", fn, "-"])

    codes_to_avoid = [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
    ]
    cleaned_xml = bytes([x for x in xml if x not in codes_to_avoid])
    dom = etree.fromstring(cleaned_xml)
    for i, page in enumerate(dom.findall(".//{http://www.w3.org/1999/xhtml}page")):
        pagedict = {
            "number": i + 1,
            "width": float(page.get("width")),
            "height": float(page.get("height")),
        }
        for word in page.findall("{http://www.w3.org/1999/xhtml}word"):
            if float(word.get("yMax")) < (top_margin / 100.0) * float(page.get("height")):
                continue
            if float(word.get("yMin")) > (bottom_margin / 100.0) * float(page.get("height")):
                continue

            yield {
                "index": box_index,
                "pdf": pdfdict,
                "page": pagedict,
                "x": float(word.get("xMin")),
                "y": float(word.get("yMin")),
                "width": float(word.get("xMax")) - float(word.get("xMin")),
                "height": float(word.get("yMax")) - float(word.get("yMin")),
                "text": word.text or "",
            }
            box_index += 1


def pdf_to_bboxes(
    pdf_index: int,
    fn: str,
    top_margin: float = 0.0,
    bottom_margin: float = 100.0,
    prefer_poppler: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Extract word bounding boxes with automatic PyMuPDF fallback."""
    if prefer_poppler and has_poppler():
        try:
            yield from pdf_to_bboxes_poppler(pdf_index, fn, top_margin, bottom_margin)
            return
        except Exception:
            pass
    yield from pdf_to_bboxes_pymupdf(pdf_index, fn, top_margin, bottom_margin)


# --------------------------------------------------------------------------- #
# Hyphenation & Serialization
# --------------------------------------------------------------------------- #
def mark_eol_hyphen(box: Dict[str, Any]) -> None:
    if box.get("text") is not None:
        if box["text"].endswith("-"):
            box["text"] = box["text"][0:-1] + "\u00AD"


def mark_eol_hyphens(boxes: Sequence[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
    box = None
    for next_box in boxes:
        if box is not None:
            if (
                box["pdf"] != next_box["pdf"]
                or box["page"] != next_box["page"]
                or next_box["y"] >= box["y"] + box["height"] / 2
            ):
                mark_eol_hyphen(box)
            yield box
        box = next_box
    if box is not None:
        mark_eol_hyphen(box)
        yield box


def serialize_pdf(
    i: int,
    fn: str,
    top_margin: float = 0.0,
    bottom_margin: float = 100.0,
    prefer_poppler: bool = False,
) -> Tuple[List[Dict[str, Any]], str]:
    box_generator = pdf_to_bboxes(i, fn, top_margin, bottom_margin, prefer_poppler=prefer_poppler)
    box_generator = mark_eol_hyphens(list(box_generator))

    boxes: List[Dict[str, Any]] = []
    text: List[str] = []
    textlength = 0
    for run in box_generator:
        if run["text"] is None:
            continue

        normalized_text = run["text"].strip()
        if normalized_text.endswith("\u00AD"):
            normalized_text = normalized_text[0:-1]
        else:
            normalized_text += " "

        run["text"] = normalized_text
        run["startIndex"] = textlength
        run["textLength"] = len(normalized_text)
        boxes.append(run)
        text.append(normalized_text)
        textlength += len(normalized_text)

    return boxes, "".join(text)


# --------------------------------------------------------------------------- #
# Diff & hunk processing
# --------------------------------------------------------------------------- #
def perform_diff(doc1text: str, doc2text: str) -> List[Tuple[str, int]]:
    from fast_diff_match_patch import diff

    return diff(doc1text, doc2text, timelimit=0, checklines=False)


def mark_difference(hunk_length: int, offset: int, boxes: List[Dict[str, Any]], changes: List[Any]) -> None:
    while len(boxes) > 0 and (boxes[0]["startIndex"] + boxes[0]["textLength"]) <= offset:
        boxes.pop(0)

    while len(boxes) > 0 and boxes[0]["startIndex"] < offset + hunk_length:
        changes.append(boxes.pop(0))


def process_hunks(hunks: Sequence[Tuple[str, int]], boxes: List[List[Dict[str, Any]]]) -> List[Any]:
    offsets = [0, 0]
    changes: List[Any] = []
    for op, oplen in hunks:
        if op == "=":
            offsets[0] += oplen
            offsets[1] += oplen
            if len(changes) > 0 and changes[-1] != "*":
                changes.append("*")
        elif op in ("-", "+"):
            idx = 0 if (op == "-") else 1
            mark_difference(oplen, offsets[idx], boxes[idx], changes)
            offsets[idx] += oplen

            idx2 = 1 - idx
            mark_difference(1, offsets[idx2] - 1, boxes[idx2], changes)
            mark_difference(0, offsets[idx2] + 0, boxes[idx2], changes)
        else:
            raise ValueError(op)

    if len(changes) > 0 and changes[-1] == "*":
        changes.pop()

    return changes


def simplify_changes(boxes: Sequence[Any]) -> List[Any]:
    changes: List[Any] = []
    for b in boxes:
        if (
            len(changes) > 0
            and changes[-1] != "*"
            and b != "*"
            and changes[-1]["pdf"] == b["pdf"]
            and changes[-1]["page"] == b["page"]
            and changes[-1]["index"] + 1 == b["index"]
            and abs(changes[-1]["y"] - b["y"]) < 2.0
            and abs(changes[-1]["height"] - b["height"]) < 3.0
        ):
            changes[-1]["width"] = b["x"] + b["width"] - changes[-1]["x"]
            changes[-1]["text"] += b["text"]
            changes[-1]["index"] += 1
            continue
        changes.append(b)
    return changes


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def pdftopng_pymupdf(pdffile: str, pagenumber: int, width: int) -> Image.Image:
    """Rasterize a PDF page to PIL RGBA image using PyMuPDF."""
    doc = pymupdf.open(pdffile)
    try:
        page = doc[pagenumber - 1]
        scale = width / float(page.rect.width)
        mat = pymupdf.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=True)
        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        return img
    finally:
        doc.close()


def pdftopng_poppler(pdffile: str, pagenumber: int, width: int) -> Image.Image:
    """Original pdf-diff rasterizer using pdftoppm."""
    pngbytes = subprocess.check_output(
        [
            "pdftoppm",
            "-f",
            str(pagenumber),
            "-l",
            str(pagenumber),
            "-scale-to",
            str(width),
            "-png",
            pdffile,
        ]
    )
    im = Image.open(io.BytesIO(pngbytes))
    return im.convert("RGBA")


def pdftopng(pdffile: str, pagenumber: int, width: int, prefer_poppler: bool = False) -> Image.Image:
    if prefer_poppler and has_poppler():
        try:
            return pdftopng_poppler(pdffile, pagenumber, width)
        except Exception:
            pass
    return pdftopng_pymupdf(pdffile, pagenumber, width)


def make_pages_images(changes: Sequence[Any], width: int, prefer_poppler: bool = False) -> List[Dict[Any, Image.Image]]:
    pages: List[Dict[Any, Image.Image]] = [{}, {}]
    for change in changes:
        if change == "*":
            continue
        pdf_index = change["pdf"]["index"]
        pdf_page = change["page"]["number"]
        if pdf_page not in pages[pdf_index]:
            pages[pdf_index][pdf_page] = pdftopng(
                change["pdf"]["file"], pdf_page, width, prefer_poppler=prefer_poppler
            )
    return pages


def realign_pages(pages: List[Dict[Any, Image.Image]], changes: List[Any]) -> List[Tuple[Dict[Any, Image.Image], Dict[Any, Image.Image]]]:
    for pdf in (0, 1):
        for page in list(pages[pdf]):
            split_index = 0
            pg = pages[pdf][page]
            del pages[pdf][page]
            pages[pdf][(page, split_index)] = pg
            for box in changes:
                if box != "*" and box["pdf"]["index"] == pdf and box["page"] == page:
                    box["page"] = (page, 0)

            for i, box in enumerate(changes):
                if box != "*":
                    continue
                try:
                    y1 = max(
                        b["y"] + b["height"]
                        for j, b in enumerate(changes)
                        if j < i
                        and b != "*"
                        and b["pdf"]["index"] == pdf
                        and b["page"] == (page, split_index)
                    )
                    y2 = min(
                        b["y"]
                        for j, b in enumerate(changes)
                        if j > i
                        and b != "*"
                        and b["pdf"]["index"] == pdf
                        and b["page"] == (page, split_index)
                    )
                except ValueError:
                    continue
                if y1 + 1 >= y2:
                    continue

                split_coord = int(round((y1 + y2) / 2))
                im = pages[pdf][(page, split_index)]
                pages[pdf][(page, split_index)] = im.crop([0, 0, im.size[0], split_coord])
                pages[pdf][(page, split_index + 1)] = im.crop([0, split_coord, im.size[0], im.size[1]])

                for j, b in enumerate(changes):
                    if j > i and b != "*" and b["pdf"]["index"] == pdf and b["page"] == (page, split_index):
                        b["page"] = (page, split_index + 1)
                        b["y"] -= split_coord
                split_index += 1

    page_groups: List[Tuple[Dict[Any, Image.Image], Dict[Any, Image.Image]]] = [({}, {})]
    for i, box in enumerate(changes):
        if box != "*":
            page_groups[-1][box["pdf"]["index"]][box["page"]] = pages[box["pdf"]["index"]][box["page"]]
        else:
            pages_before = set(
                (b["pdf"]["index"], b["page"])
                for j, b in enumerate(changes)
                if j < i and b != "*"
            )
            pages_after = set(
                (b["pdf"]["index"], b["page"])
                for j, b in enumerate(changes)
                if j > i and b != "*"
            )
            if len(pages_before & pages_after) == 0:
                page_groups.append(({}, {}))
    return page_groups


def draw_red_boxes(
    changes: Sequence[Any],
    pages: List[Dict[Any, Image.Image]],
    styles: Sequence[str] = ("strike", "underline"),
    box_color: str = "#E53E3E",
) -> None:
    for change in changes:
        if change == "*":
            continue

        style = styles[change["pdf"]["index"]]
        im = pages[change["pdf"]["index"]][change["page"]]
        draw = ImageDraw.Draw(im)

        cx = change["x"]
        cy = change["y"]
        cw = change["width"]
        ch = change["height"]

        if style == "box":
            draw.rectangle((cx, cy, cx + cw, cy + ch), outline=box_color, width=2)
        elif style == "strike":
            draw.line((cx, cy + ch / 2, cx + cw, cy + ch / 2), fill=box_color, width=2)
        elif style == "underline":
            draw.line((cx, cy + ch, cx + cw, cy + ch), fill=box_color, width=2)
        del draw


def zealous_crop(page_groups: List[Tuple[Dict[Any, Image.Image], Dict[Any, Image.Image]]]) -> None:
    for idx in (0, 1):
        minx = None
        maxx = None
        width = None
        for grp in page_groups:
            for pdf in grp[idx].values():
                bbox = ImageOps.invert(pdf.convert("L")).getbbox()
                if bbox is None:
                    continue
                minx = min(bbox[0], minx) if minx is not None else bbox[0]
                maxx = max(bbox[2], maxx) if maxx is not None else bbox[2]
                width = max(width, pdf.size[0]) if width is not None else pdf.size[0]
        if width is not None and minx is not None and maxx is not None:
            minx = max(0, minx - int(0.02 * width))
            maxx = min(width, maxx + int(0.02 * width))
            for grp in page_groups:
                for pg in grp[idx]:
                    im = grp[idx][pg]
                    bbox = ImageOps.invert(im.convert("L")).getbbox()
                    if bbox is None:
                        bbox = [0, 0, im.size[0], im.size[1]]
                    vpad = int(0.02 * im.size[1])
                    im = im.crop((0, max(0, bbox[1] - vpad), im.size[0], min(im.size[1], bbox[3] + vpad)))
                    if os.environ.get("HORZCROP", "1") != "0":
                        im = im.crop((minx, 0, maxx, im.size[1]))
                    grp[idx][pg] = im


def stack_pages(page_groups: List[Tuple[Dict[Any, Image.Image], Dict[Any, Image.Image]]]) -> Image.Image:
    col_height = [0, 0]
    col_width = 0
    page_group_spacers = []
    for grp in page_groups:
        for idx in (0, 1):
            for im in grp[idx].values():
                col_height[idx] += im.size[1]
                col_width = max(col_width, im.size[0])

        dy = col_height[1] - col_height[0]
        if abs(dy) < 10:
            dy = 0
        page_group_spacers.append((dy if dy > 0 else 0, -dy if dy < 0 else 0))
        col_height[0] += page_group_spacers[-1][0]
        col_height[1] += page_group_spacers[-1][1]

    height = max(max(col_height), 10)
    col_width = max(col_width, 10)

    img = Image.new("RGBA", (col_width * 2 + 1, height), "#F8FAFC")
    draw = ImageDraw.Draw(img)
    for x in range(0, col_width * 2 + 1, 50):
        draw.line((x, 0, x, img.size[1]), fill="#EDF2F7")

    for idx in (0, 1):
        y = 0
        for i, grp in enumerate(page_groups):
            for pg in sorted(grp[idx]):
                pgimg = grp[idx][pg]
                img.paste(pgimg, (0 if idx == 0 else (col_width + 1), y))
                if pg[0] > 1 and pg[1] == 0:
                    draw.line((0 if idx == 0 else col_width, y, col_width * (idx + 1), y), fill="#CBD5E0")
                y += pgimg.size[1]
            y += page_group_spacers[i][idx]

    draw.line((col_width, 0, col_width, height), fill="#718096", width=2)
    del draw

    return img


def compute_changes(
    pdf_fn_1: str,
    pdf_fn_2: str,
    top_margin: float = 0.0,
    bottom_margin: float = 100.0,
    prefer_poppler: bool = False,
) -> List[Any]:
    """Compute text and bounding box changes between two PDFs."""
    doc0 = serialize_pdf(0, pdf_fn_1, top_margin, bottom_margin, prefer_poppler=prefer_poppler)
    doc1 = serialize_pdf(1, pdf_fn_2, top_margin, bottom_margin, prefer_poppler=prefer_poppler)

    diff = perform_diff(doc0[1], doc1[1])
    changes = process_hunks(diff, [doc0[0], doc1[0]])
    return changes


def render_changes(
    changes: List[Any],
    styles: Sequence[str] = ("box", "box"),
    width: int = 900,
    prefer_poppler: bool = False,
) -> Image.Image:
    """Render side-by-side comparison image from changes list."""
    simplified = simplify_changes(changes)
    if not simplified or all(b == "*" for b in simplified):
        raise ValueError("There are no text differences to render.")

    pages = make_pages_images(simplified, width, prefer_poppler=prefer_poppler)

    for change in simplified:
        if change == "*":
            continue
        im = pages[change["pdf"]["index"]][change["page"]["number"]]
        scale_x = im.size[0] / change["page"]["width"]
        scale_y = im.size[1] / change["page"]["height"]
        change["x"] *= scale_x
        change["y"] *= scale_y
        change["width"] *= scale_x
        change["height"] *= scale_y
        change["page"] = change["page"]["number"]

    page_groups = realign_pages(pages, simplified)
    draw_red_boxes(simplified, pages, styles)
    zealous_crop(page_groups)
    return stack_pages(page_groups)
