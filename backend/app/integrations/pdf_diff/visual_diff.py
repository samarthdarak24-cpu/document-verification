"""OpenCV & PyMuPDF visual difference detector for figures, diagrams, and images.

Extends pdf-diff to identify modifications in:
- Figures, charts, and diagrams
- Embedded images and photos
- Signatures, stamps, and seals
- Vector drawings and layout shapes
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import pymupdf
from PIL import Image


@dataclass
class VisualDiffRegion:
    """A detected non-text visual modification on a page."""

    page: int
    kind: str  # "figure" | "diagram" | "image" | "stamp_or_seal" | "graphic"
    bbox_pixel: List[int]  # [x, y, w, h] in rendered pixels
    bbox_pdf: List[float]  # [x, y, w, h] in PDF points
    area_pixels: int
    change_severity: str  # "minor" | "moderate" | "significant"
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "kind": self.kind,
            "bbox_pixel": list(self.bbox_pixel),
            "bbox_pdf": [round(v, 2) for v in self.bbox_pdf],
            "area_pixels": self.area_pixels,
            "change_severity": self.change_severity,
            "description": self.description,
        }


def _bbox_overlap_ratio(b1: Sequence[float], b2: Sequence[float]) -> float:
    """Calculate intersection over union or overlap ratio between two bboxes [x, y, w, h]."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[0] + b1[2], b2[0] + b2[2])
    y2 = min(b1[1] + b1[3], b2[1] + b2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = b1[2] * b1[3]
    if area1 <= 0:
        return 0.0
    return intersection / area1


def _extract_page_images(doc: pymupdf.Document, page_num: int) -> List[Dict[str, Any]]:
    """Extract embedded image metadata and bounding rects for a page."""
    page = doc[page_num - 1]
    image_list = page.get_images(full=True)
    results = []

    for img_info in image_list:
        xref = img_info[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image.get("image", b"")
        md5 = hashlib.md5(image_bytes).hexdigest()
        
        # Bounding boxes on page where this image is placed
        rects = page.get_image_rects(xref)
        for r in rects:
            results.append({
                "xref": xref,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0),
                "ext": base_image.get("ext", "png"),
                "md5": md5,
                "bbox": [float(r.x0), float(r.y0), float(r.width), float(r.height)],
            })
    return results


def detect_visual_modifications(
    pdf_path_1: str,
    pdf_path_2: str,
    text_change_boxes: Optional[Sequence[Dict[str, Any]]] = None,
    dpi: int = 150,
) -> Dict[str, Any]:
    """Compare visual layers of two PDFs using OpenCV and PyMuPDF.

    Distinguishes purely visual/graphic modifications (charts, diagrams, images)
    from text changes.
    """
    doc1 = pymupdf.open(pdf_path_1)
    doc2 = pymupdf.open(pdf_path_2)

    total_pages = min(len(doc1), len(doc2))
    all_regions: List[VisualDiffRegion] = []
    modified_images_count = 0
    modified_drawings_count = 0

    # Build index of text change bboxes per page for filtering
    text_boxes_by_page: Dict[int, List[List[float]]] = {}
    if text_change_boxes:
        for box in text_change_boxes:
            if box == "*":
                continue
            pg = box.get("page")
            if isinstance(pg, dict):
                p_num = int(pg.get("number", 1))
            elif isinstance(pg, (list, tuple)):
                p_num = int(pg[0])
            else:
                try:
                    p_num = int(pg or 1)
                except Exception:
                    p_num = 1

            if p_num not in text_boxes_by_page:
                text_boxes_by_page[p_num] = []
            text_boxes_by_page[p_num].append([
                float(box.get("x", 0)),
                float(box.get("y", 0)),
                float(box.get("width", 0)),
                float(box.get("height", 0)),
            ])

    try:
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page1 = doc1[page_idx]
            page2 = doc2[page_idx]

            # 1. Compare embedded images (figures/photos)
            imgs1 = _extract_page_images(doc1, page_num)
            imgs2 = _extract_page_images(doc2, page_num)

            # Match images by position/xref
            for i1 in imgs1:
                b1 = i1["bbox"]
                matched = False
                for i2 in imgs2:
                    b2 = i2["bbox"]
                    if _bbox_overlap_ratio(b1, b2) > 0.5:
                        matched = True
                        if i1["md5"] != i2["md5"]:
                            modified_images_count += 1
                            all_regions.append(
                                VisualDiffRegion(
                                    page=page_num,
                                    kind="image",
                                    bbox_pixel=[int(v * (dpi / 72.0)) for v in b1],
                                    bbox_pdf=b1,
                                    area_pixels=int(b1[2] * b1[3] * ((dpi / 72.0) ** 2)),
                                    change_severity="significant",
                                    description=f"Embedded image/figure modified on page {page_num} ({i1['width']}x{i1['height']}px)",
                                )
                            )
                        break
                if not matched:
                    # Image removed or replaced
                    all_regions.append(
                        VisualDiffRegion(
                            page=page_num,
                            kind="image",
                            bbox_pixel=[int(v * (dpi / 72.0)) for v in b1],
                            bbox_pdf=b1,
                            area_pixels=int(b1[2] * b1[3] * ((dpi / 72.0) ** 2)),
                            change_severity="significant",
                            description=f"Image/figure removed or shifted on page {page_num}",
                        )
                    )

            # 2. Pixel-level OpenCV contour differencing
            pix1 = page1.get_pixmap(dpi=dpi)
            pix2 = page2.get_pixmap(dpi=dpi)

            # Convert to OpenCV BGR images
            img1 = np.frombuffer(pix1.samples, dtype=np.uint8).reshape((pix1.height, pix1.width, pix1.n))
            img2 = np.frombuffer(pix2.samples, dtype=np.uint8).reshape((pix2.height, pix2.width, pix2.n))

            if img1.shape[2] == 4:
                gray1 = cv2.cvtColor(img1, cv2.COLOR_RGBA2GRAY)
            else:
                gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)

            if img2.shape[2] == 4:
                gray2 = cv2.cvtColor(img2, cv2.COLOR_RGBA2GRAY)
            else:
                gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)

            # Ensure same dimensions
            if gray1.shape != gray2.shape:
                max_h = max(gray1.shape[0], gray2.shape[0])
                max_w = max(gray1.shape[1], gray2.shape[1])
                padded1 = np.full((max_h, max_w), 255, dtype=np.uint8)
                padded2 = np.full((max_h, max_w), 255, dtype=np.uint8)
                padded1[: gray1.shape[0], : gray1.shape[1]] = gray1
                padded2[: gray2.shape[0], : gray2.shape[1]] = gray2
                gray1, gray2 = padded1, padded2

            diff = cv2.absdiff(gray1, gray2)
            blurred = cv2.GaussianBlur(diff, (5, 5), 0)
            _, thresh = cv2.threshold(blurred, 30, 255, cv2.THRESH_BINARY)

            # Morphological dilation/closing to group nearby pixels into diagram regions
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            scale_to_pdf_x = page1.rect.width / float(gray1.shape[1])
            scale_to_pdf_y = page1.rect.height / float(gray1.shape[0])

            page_text_boxes = text_boxes_by_page.get(page_num, [])

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                # Filter out tiny noise (less than 150 px^2)
                if area < 150:
                    continue

                pdf_bbox = [
                    x * scale_to_pdf_x,
                    y * scale_to_pdf_y,
                    w * scale_to_pdf_x,
                    h * scale_to_pdf_y,
                ]

                # Check if this contour is fully or mostly explained by a text change
                is_text_change = False
                for tb in page_text_boxes:
                    if _bbox_overlap_ratio(pdf_bbox, tb) > 0.45 or _bbox_overlap_ratio(tb, pdf_bbox) > 0.45:
                        is_text_change = True
                        break

                if is_text_change:
                    continue

                # Determine if it's already recorded in image diffs
                already_in_images = False
                for reg in all_regions:
                    if reg.page == page_num and _bbox_overlap_ratio(pdf_bbox, reg.bbox_pdf) > 0.4:
                        already_in_images = True
                        break

                if already_in_images:
                    continue

                # Classify visual element
                ratio = w / float(h) if h > 0 else 1.0
                if area > 10000 or (w > 200 and h > 100):
                    kind = "figure"
                    desc = f"Figure or diagram graphic modification on page {page_num}"
                    severity = "significant"
                elif 0.8 <= ratio <= 1.2 and area > 1200:
                    kind = "stamp_or_seal"
                    desc = f"Seal, stamp, or circular graphic change on page {page_num}"
                    severity = "moderate"
                elif w > 100 and h < 25:
                    kind = "graphic"
                    desc = f"Horizontal divider rule or line change on page {page_num}"
                    severity = "minor"
                else:
                    kind = "diagram"
                    desc = f"Visual diagram or chart element changed on page {page_num}"
                    severity = "moderate"

                modified_drawings_count += 1
                all_regions.append(
                    VisualDiffRegion(
                        page=page_num,
                        kind=kind,
                        bbox_pixel=[x, y, w, h],
                        bbox_pdf=pdf_bbox,
                        area_pixels=area,
                        change_severity=severity,
                        description=desc,
                    )
                )

    finally:
        doc1.close()
        doc2.close()

    return {
        "visual_modifications_detected": len(all_regions) > 0,
        "region_count": len(all_regions),
        "modified_images_count": modified_images_count,
        "modified_drawings_count": modified_drawings_count,
        "regions": [r.to_dict() for r in all_regions],
    }
