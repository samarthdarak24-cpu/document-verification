"""Unified PDF difference and modification analysis orchestrator.

Integrates:
- JoshData/pdf-diff text & bounding-box detection
- PyMuPDF typographic span & layout extraction
- OpenCV figure/diagram visual change detection
- Research paper section identification & inversion counting
- DocuTrace DAA algorithms (LCS DP, Levenshtein edit distance, Tree traversal)
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf
from PIL import Image

from app.algorithms.edit_distance import edit_distance
from app.algorithms.lcs import lcs_dp, tokenize
from app.core.config import get_settings
from app.integrations.pdf_diff.core import compute_changes, render_changes, simplify_changes
from app.integrations.pdf_diff.section_analyzer import (
    analyze_section_modifications,
    extract_document_sections,
    find_enclosing_section,
)
from app.integrations.pdf_diff.semantic_classifier import classify_modification
from app.integrations.pdf_diff.visual_diff import detect_visual_modifications
from app.services.document_change_detector import detect_style_changes
from app.services.pdf_metadata import extract_pdf_metadata


def _file_hash(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_pdf_diff_analysis(
    pdf_path_1: str | Path,
    pdf_path_2: str | Path,
    *,
    source_label: str = "Original",
    target_label: str = "Modified",
    dpi: int = 150,
    render_image: bool = True,
) -> Dict[str, Any]:
    """Execute the full PDF comparison and modification analysis pipeline."""
    started_total = time.perf_counter()
    p1 = Path(pdf_path_1)
    p2 = Path(pdf_path_2)

    if not p1.exists():
        raise FileNotFoundError(f"Original PDF not found: {p1}")
    if not p2.exists():
        raise FileNotFoundError(f"Modified PDF not found: {p2}")

    # 1. Document metadata
    meta1 = {
        "filename": p1.name,
        "label": source_label,
        "sha256": _file_hash(p1),
        "file_size": p1.stat().st_size,
    }
    meta2 = {
        "filename": p2.name,
        "label": target_label,
        "sha256": _file_hash(p2),
        "file_size": p2.stat().st_size,
    }

    doc1 = pymupdf.open(str(p1))
    doc2 = pymupdf.open(str(p2))
    meta1["page_count"] = len(doc1)
    meta2["page_count"] = len(doc2)
    doc1.close()
    doc2.close()

    # 2. Extract research paper sections
    headings_1 = extract_document_sections(str(p1))
    headings_2 = extract_document_sections(str(p2))

    # 3. Span-level typography metadata extraction via PyMuPDF
    t_start = time.perf_counter()
    pdf_meta_1 = extract_pdf_metadata(str(p1))
    pdf_meta_2 = extract_pdf_metadata(str(p2))
    style_changes = detect_style_changes(pdf_meta_1.all_spans(), pdf_meta_2.all_spans())
    style_elapsed = (time.perf_counter() - t_start) * 1000

    # 4. Core pdf-diff bounding box text difference detection
    t_start = time.perf_counter()
    raw_pdf_diff_changes = compute_changes(str(p1), str(p2))
    simplified_pdf_diff = simplify_changes(raw_pdf_diff_changes)
    pdf_diff_elapsed = (time.perf_counter() - t_start) * 1000

    # 5. OpenCV visual & diagram difference detection
    t_start = time.perf_counter()
    visual_results = detect_visual_modifications(
        str(p1), str(p2), text_change_boxes=simplified_pdf_diff, dpi=dpi
    )
    opencv_elapsed = (time.perf_counter() - t_start) * 1000

    # 6. Extract full texts & run DocuTrace DAA LCS and Edit Distance
    text1 = "\n".join(page.text for page in pdf_meta_1.pages)
    text2 = "\n".join(page.text for page in pdf_meta_2.pages)
    tokens1 = tokenize(text1)[:4000]
    tokens2 = tokenize(text2)[:4000]

    t_start = time.perf_counter()
    lcs_result = lcs_dp(tokens1, tokens2)
    lcs_elapsed = (time.perf_counter() - t_start) * 1000

    t_start = time.perf_counter()
    overall_edit = edit_distance(" ".join(tokens1), " ".join(tokens2))
    edit_elapsed = (time.perf_counter() - t_start) * 1000

    # 7. Unify and classify granular change entries
    changes_list: List[Dict[str, Any]] = []
    change_id_seq = 1

    # Text changes from pdf-diff
    for box in simplified_pdf_diff:
        if box == "*":
            continue
        pdf_idx = box["pdf"]["index"]
        page_num = box["page"]["number"]
        bx = float(box["x"])
        by = float(box["y"])
        bw = float(box["width"])
        bh = float(box["height"])
        txt = box.get("text", "").strip()
        if not txt:
            continue

        sec = find_enclosing_section(
            page_num, by, headings_1 if pdf_idx == 0 else headings_2
        )
        change_type = "delete" if pdf_idx == 0 else "insert"
        removed_text = txt if pdf_idx == 0 else ""
        added_text = txt if pdf_idx == 1 else ""

        category, scope = classify_modification(removed_text, added_text)

        font_diff = None
        if box.get("font"):
            font_diff = {
                "font": box.get("font"),
                "size": box.get("size"),
                "color": box.get("color"),
                "bold": box.get("bold"),
                "italic": box.get("italic"),
            }

        changes_list.append({
            "id": f"change-{change_id_seq}",
            "type": change_type,
            "category": category,
            "scope": scope,
            "section": sec,
            "page": page_num,
            "removed_text": removed_text,
            "added_text": added_text,
            "font_diff": font_diff,
            "bbox": [round(bx, 2), round(by, 2), round(bw, 2), round(bh, 2)],
            "pdf_index": pdf_idx,
            "char_operations": [],
            "description": f"Text {change_type} in {sec}: '{txt}'",
        })
        change_id_seq += 1

    # Merge nearby delete + insert into replace hunks if they are on same page and section
    merged_changes: List[Dict[str, Any]] = []
    i = 0
    while i < len(changes_list):
        curr = changes_list[i]
        if i + 1 < len(changes_list):
            nxt = changes_list[i + 1]
            if (
                curr["type"] == "delete"
                and nxt["type"] == "insert"
                and curr["page"] == nxt["page"]
                and curr["section"] == nxt["section"]
                and abs(curr["bbox"][1] - nxt["bbox"][1]) < 25.0
            ):
                # Pair up as replacement
                ed = edit_distance(curr["removed_text"], nxt["added_text"], with_operations=True)
                cat, scope = classify_modification(curr["removed_text"], nxt["added_text"])
                merged_changes.append({
                    "id": f"change-rep-{change_id_seq}",
                    "type": "replace",
                    "category": cat,
                    "scope": scope,
                    "section": curr["section"],
                    "page": curr["page"],
                    "removed_text": curr["removed_text"],
                    "added_text": nxt["added_text"],
                    "font_diff": nxt.get("font_diff") or curr.get("font_diff"),
                    "bbox_original": curr["bbox"],
                    "bbox_modified": nxt["bbox"],
                    "bbox": nxt["bbox"],
                    "pdf_index": 1,
                    "char_edit_distance": ed.distance,
                    "char_operations": ed.operations[:20],
                    "description": f"Modified in {curr['section']}: '{curr['removed_text']}' -> '{nxt['added_text']}'",
                })
                change_id_seq += 1
                i += 2
                continue
        merged_changes.append(curr)
        i += 1

    # Add typographic/font changes (where text is identical but font/formatting differed)
    for sc in style_changes:
        sec = find_enclosing_section(sc.page, 0.0, headings_1)
        cat, scope = classify_modification("", "", has_style_change=True)
        merged_changes.append({
            "id": f"change-font-{change_id_seq}",
            "type": "style",
            "category": "font_only",
            "scope": "formatting",
            "section": sec,
            "page": sc.page,
            "removed_text": sc.text,
            "added_text": sc.text,
            "font_diff": sc.changes,
            "bbox": sc.changes.get("position", {}).get("modified_bbox") or [50.0, 50.0, 100.0, 15.0],
            "pdf_index": 1,
            "char_operations": [],
            "description": f"Typographic change in {sec}: '{sc.text}' ({', '.join(sc.changes.keys())})",
        })
        change_id_seq += 1

    # Add OpenCV visual diagram/figure changes
    for vr in visual_results.get("regions", []):
        sec = find_enclosing_section(vr["page"], vr["bbox_pdf"][1], headings_1)
        merged_changes.append({
            "id": f"change-vis-{change_id_seq}",
            "type": "visual_diagram",
            "category": "visual_diagram",
            "scope": "diagram",
            "section": sec,
            "page": vr["page"],
            "removed_text": "",
            "added_text": "",
            "font_diff": None,
            "bbox": vr["bbox_pdf"],
            "pdf_index": 1,
            "char_operations": [],
            "description": f"{vr['description']} ({vr['kind']}, {vr['change_severity']} change)",
        })
        change_id_seq += 1

    # 8. Section modifications analysis
    section_analysis = analyze_section_modifications(headings_1, headings_2, merged_changes)

    # 9. Render side-by-side diff image via pdf-diff
    diff_image_base64: Optional[str] = None
    diff_image_url: Optional[str] = None
    comparison_uuid = hashlib.md5(f"{meta1['sha256']}-{meta2['sha256']}".encode()).hexdigest()[:12]

    if render_image:
        try:
            if simplified_pdf_diff and any(b != "*" for b in simplified_pdf_diff):
                img = render_changes(simplified_pdf_diff, styles=("box", "box"), width=900)
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                diff_image_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

                # Also save to storage for URL fetching
                settings = get_settings()
                out_path = settings.storage_root / "diff_images" / f"{comparison_uuid}.png"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(out_path, format="PNG")
                diff_image_url = f"/api/compare/diff-image/{comparison_uuid}"
        except Exception:
            diff_image_base64 = None

    # 10. Compile Page-level bounding boxes for frontend side-by-side interactive viewer
    max_pages = max(meta1["page_count"], meta2["page_count"])
    pages_data: List[Dict[str, Any]] = []

    # Get page dimensions
    doc1 = pymupdf.open(str(p1))
    doc2 = pymupdf.open(str(p2))

    for p in range(1, max_pages + 1):
        p1_width = float(doc1[p - 1].rect.width) if p <= len(doc1) else 612.0
        p1_height = float(doc1[p - 1].rect.height) if p <= len(doc1) else 792.0
        p2_width = float(doc2[p - 1].rect.width) if p <= len(doc2) else 612.0
        p2_height = float(doc2[p - 1].rect.height) if p <= len(doc2) else 792.0

        page_changes = [c for c in merged_changes if c["page"] == p]
        pages_data.append({
            "page": p,
            "original_width": p1_width,
            "original_height": p1_height,
            "modified_width": p2_width,
            "modified_height": p2_height,
            "change_count": len(page_changes),
            "changes": page_changes,
        })

    doc1.close()
    doc2.close()

    # 11. Overall summary
    total_changes = len(merged_changes)
    numerical_count = sum(1 for c in merged_changes if c["category"] == "numerical")
    date_count = sum(1 for c in merged_changes if c["category"] == "date")
    reg_id_count = sum(1 for c in merged_changes if c["category"] == "registration_no")
    name_count = sum(1 for c in merged_changes if c["category"] == "name_entity")
    font_count = sum(1 for c in merged_changes if c["category"] == "font_only")
    visual_count = sum(1 for c in merged_changes if c["category"] == "visual_diagram")

    elapsed_ms = (time.perf_counter() - started_total) * 1000.0

    verdict = "identical"
    if total_changes > 0:
        if numerical_count > 0 or reg_id_count > 0 or date_count > 0:
            verdict = "critical_data_modified"
        elif font_count > 0 and (total_changes == font_count):
            verdict = "typography_only_modified"
        elif visual_count > 0 and (total_changes == visual_count):
            verdict = "visual_diagrams_modified"
        else:
            verdict = "content_modified"

    return {
        "comparison_id": comparison_uuid,
        "source_document": meta1,
        "target_document": meta2,
        "verdict": verdict,
        "summary": {
            "total_changes": total_changes,
            "text_changes": total_changes - font_count - visual_count,
            "numerical_changes": numerical_count,
            "date_changes": date_count,
            "registration_no_changes": reg_id_count,
            "name_changes": name_count,
            "font_changes": font_count,
            "visual_diagram_changes": visual_count,
            "sections_modified_count": section_analysis["modified_sections_count"],
        },
        "daa_algorithms": {
            "lcs_similarity": round(lcs_result.similarity, 4),
            "lcs_length": lcs_result.length,
            "edit_similarity": round(overall_edit.similarity, 4),
            "edit_distance": overall_edit.distance,
            "section_reorder_score": section_analysis["reordering"]["reorder_score"] if section_analysis["reordering"] else 0.0,
            "section_inversions": section_analysis["reordering"]["inversion_count"] if section_analysis["reordering"] else 0,
            "algorithms_executed": [
                "fast_diff_match_patch",
                "pdf_diff_bounding_box",
                "lcs_dp",
                "edit_distance",
                "opencv_visual_diff",
                "count_inversions",
                "tree_traversal",
            ],
            "timings_ms": {
                "pdf_diff": round(pdf_diff_elapsed, 2),
                "pymupdf_typography": round(style_elapsed, 2),
                "opencv_visual": round(opencv_elapsed, 2),
                "lcs_dp": round(lcs_elapsed, 2),
                "edit_distance": round(edit_elapsed, 2),
                "total": round(elapsed_ms, 2),
            },
        },
        "section_analysis": section_analysis,
        "changes": merged_changes,
        "pages": pages_data,
        "visual_modifications": visual_results,
        "diff_image_base64": diff_image_base64,
        "diff_image_url": diff_image_url,
        "elapsed_ms": round(elapsed_ms, 2),
    }
