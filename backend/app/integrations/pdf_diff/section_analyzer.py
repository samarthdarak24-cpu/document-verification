"""Research paper section detector and modification analyzer.

Identifies sections (Abstract, Introduction, Methodology, Results, Conclusion, etc.)
and maps text, font, and visual differences to their respective sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf
from app.algorithms.inversions import count_inversions

#: Standard research paper section patterns
RESEARCH_SECTION_PATTERNS = [
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?abstract\b", "Abstract"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?introduction\b", "Introduction"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:related\s+work|literature\s+review)\b", "Related Work"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?background\b", "Background"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:methodology|methods|proposed\s+method|system\s+model|architecture)\b", "Methodology"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:experimental\s+setup|experiments|implementation)\b", "Experiments"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:results|evaluation|empirical\s+results|findings)\b", "Results"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?discussion\b", "Discussion"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:conclusion|conclusions|concluding\s+remarks|future\s+work)\b", "Conclusion"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:references|bibliography)\b", "References"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?(?:appendix|appendices)\b", "Appendix"),
    (r"^\s*(?:(?:\d+|[IVXLCDM]+)[\.\s]+)?acknowledg(?:e)?ments?\b", "Acknowledgements"),
]

#: Standard certificate & report field patterns
CERTIFICATE_FIELD_PATTERNS = [
    (r"^\s*(?:certificate\s+of|statement\s+of|grade\s+card|transcript|mark\s*sheet)\b", "Header & Title"),
    (r"^\s*(?:name|student\s+name|candidate\s+name|certifies\s+that|awarded\s+to|presented\s+to)\b", "Recipient Name"),
    (r"^\s*(?:reg(?:istration)?\s*(?:no|number)|roll\s*(?:no|number)|enrollment\s*(?:no|number)|id\s*number)\b", "Registration / ID"),
    (r"^\s*(?:course|degree|program|discipline|department|subject)\b", "Course & Program"),
    (r"^\s*(?:date\s+of\s+issue|issue\s+date|date|issued\s+on)\b", "Date of Issue"),
    (r"^\s*(?:grade|cgpa|percentage|marks|class|division|score)\b", "Grade & Performance"),
    (r"^\s*(?:authorized\s+signatory|director|dean|registrar|controller|signature)\b", "Signatures & Authority"),
]


@dataclass
class SectionHeading:
    """A detected heading in a document."""

    title: str
    standard_name: str
    page: int
    y: float
    bbox: List[float]


def _match_section_name(line: str) -> Optional[str]:
    text = line.strip().lower()
    for pattern, std_name in RESEARCH_SECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return std_name
    for pattern, std_name in CERTIFICATE_FIELD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return std_name
    return None


def extract_document_sections(pdf_path: str) -> List[SectionHeading]:
    """Scan PDF using PyMuPDF to locate all section headings and their coordinates."""
    doc = pymupdf.open(pdf_path)
    headings: List[SectionHeading] = []

    try:
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(sp.get("text", "") for sp in line.get("spans", [])).strip()
                    if not line_text or len(line_text) > 100:
                        continue

                    std_name = _match_section_name(line_text)
                    if std_name:
                        l_bbox = [float(v) for v in line.get("bbox", [0, 0, 0, 0])]
                        headings.append(
                            SectionHeading(
                                title=line_text,
                                standard_name=std_name,
                                page=page_num,
                                y=l_bbox[1],
                                bbox=l_bbox,
                            )
                        )
    finally:
        doc.close()

    return headings


def find_enclosing_section(
    page: int,
    y: float,
    headings: Sequence[SectionHeading],
    default_section: str = "General Content",
) -> str:
    """Locate the section containing a given page and vertical coordinate."""
    current_section = default_section
    for h in headings:
        if h.page < page:
            current_section = h.standard_name
        elif h.page == page:
            if y >= h.y - 5.0:
                current_section = h.standard_name
            else:
                break
        else:
            break
    return current_section


def analyze_section_modifications(
    headings_orig: Sequence[SectionHeading],
    headings_mod: Sequence[SectionHeading],
    changes_with_sections: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compile a complete report of section modifications, additions, and reorderings."""
    orig_names = [h.standard_name for h in headings_orig]
    mod_names = [h.standard_name for h in headings_mod]

    # Deduplicate preserving order
    def _dedup(items: Sequence[str]) -> List[str]:
        seen = set()
        res = []
        for x in items:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res

    distinct_orig = _dedup(orig_names)
    distinct_mod = _dedup(mod_names)

    all_sections = _dedup(distinct_orig + distinct_mod + [c.get("section", "General Content") for c in changes_with_sections])
    if not all_sections:
        all_sections = ["General Content"]

    section_stats: Dict[str, Dict[str, Any]] = {}
    for sec in all_sections:
        section_stats[sec] = {
            "section": sec,
            "status": "unchanged",
            "changes_count": 0,
            "words_added": 0,
            "words_removed": 0,
            "style_changes": 0,
            "visual_changes": 0,
            "numerical_changes": 0,
            "date_changes": 0,
            "snippets": [],
        }

    for c in changes_with_sections:
        sec = c.get("section", "General Content")
        if sec not in section_stats:
            section_stats[sec] = {
                "section": sec,
                "status": "unchanged",
                "changes_count": 0,
                "words_added": 0,
                "words_removed": 0,
                "style_changes": 0,
                "visual_changes": 0,
                "numerical_changes": 0,
                "date_changes": 0,
                "snippets": [],
            }
        stats = section_stats[sec]
        stats["changes_count"] += 1

        cat = c.get("category", "")
        if cat == "numerical":
            stats["numerical_changes"] += 1
        elif cat == "date":
            stats["date_changes"] += 1
        elif cat == "font_only":
            stats["style_changes"] += 1
        elif cat == "visual_diagram":
            stats["visual_changes"] += 1

        ctype = c.get("type", "")
        if ctype == "insert":
            stats["words_added"] += len(c.get("added_text", "").split())
        elif ctype == "delete":
            stats["words_removed"] += len(c.get("removed_text", "").split())
        elif ctype == "replace":
            stats["words_added"] += len(c.get("added_text", "").split())
            stats["words_removed"] += len(c.get("removed_text", "").split())

        # Collect sample snippets
        if len(stats["snippets"]) < 4:
            snippet = ""
            if c.get("removed_text") and c.get("added_text"):
                snippet = f"Changed: '{c['removed_text'][:40]}' -> '{c['added_text'][:40]}'"
            elif c.get("added_text"):
                snippet = f"Added: '{c['added_text'][:40]}'"
            elif c.get("removed_text"):
                snippet = f"Removed: '{c['removed_text'][:40]}'"
            elif c.get("description"):
                snippet = c["description"]
            if snippet:
                stats["snippets"].append(snippet)

    # Determine section status
    for sec, stats in section_stats.items():
        in_orig = sec in distinct_orig
        in_mod = sec in distinct_mod
        if in_mod and not in_orig:
            stats["status"] = "added"
        elif in_orig and not in_mod:
            stats["status"] = "removed"
        elif stats["changes_count"] > 0:
            stats["status"] = "modified"
        else:
            stats["status"] = "unchanged"

    # Quantify section reordering using count_inversions (DAA Unit II)
    reordering_data = None
    shared = [s for s in distinct_orig if s in distinct_mod]
    if len(shared) >= 2:
        rank_map = {name: idx for idx, name in enumerate(shared)}
        mod_ranks = [rank_map[name] for name in distinct_mod if name in rank_map]
        inversion_result = count_inversions(mod_ranks, trace=False)
        reordering_data = {
            "shared_sections": shared,
            "inversion_count": inversion_result.inversion_count,
            "reorder_score": round(inversion_result.normalized_reorder_score, 4),
            "reordered": inversion_result.inversion_count > 0,
        }

    return {
        "all_sections": all_sections,
        "sections": list(section_stats.values()),
        "modified_sections_count": sum(1 for s in section_stats.values() if s["status"] != "unchanged"),
        "reordering": reordering_data,
    }
