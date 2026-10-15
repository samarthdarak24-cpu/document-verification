"""Document structure analysis: heading detection, tree building, validation.

Honesty rule
------------
**The structure service never invents a section.** If the extractor produced no
reliable heading signal (a scanned invoice photographed at an angle, an image
with OCR disabled) the result is returned with ``uncertain=True`` and the
template's expected sections are reported as *not verified* rather than as
*missing*. A missing section is an accusation; "we could not read this
document's structure" is an observation, and only the latter is defensible from
a document with no headings.

Heading detection heuristics (in priority order)
-------------------------------------------------
1. **DOCX heading styles** — the document's own structural metadata, so this is
   the strongest signal (``method="docx_style"``, level from the style name).
2. **ALL-CAPS short lines** — a line of 3-60 characters, no trailing sentence
   punctuation, all letters uppercase (``method="all_caps"``).
3. **Numbered sections** — ``"3. Methodology"`` / ``"IV. Results"``
   (``method="numbered"``).

The resulting :class:`~app.algorithms.tree_traversal.DocumentNode` tree is then
validated against the template with
:func:`app.algorithms.tree_traversal.validate_structure`, and traversed with
both :func:`~app.algorithms.tree_traversal.dfs` and
:func:`~app.algorithms.tree_traversal.bfs` so the traversal costs appear in
``algorithm_runs`` (and therefore in the report).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.algorithms.tree_traversal import (
    DocumentNode,
    bfs,
    build_tree,
    dfs,
    structural_signature,
    validate_structure,
)
from app.services.field_validation import TemplateSpec
from app.services.extraction import ExtractionResult, Heading

#: Cap on the number of nodes in a generated tree (keeps traversal linear and
#: the JSON payloads small on pathological inputs).
_MAX_TREE_NODES = 300


@dataclass
class StructureResult:
    """Outcome of the structural stage."""

    tree_spec: Dict[str, Any] = field(default_factory=dict)
    headings: List[Dict[str, Any]] = field(default_factory=list)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    unverified_sections: List[str] = field(default_factory=list)
    uncertain: bool = True
    heuristic: str = "none"
    validation: Dict[str, Any] = field(default_factory=dict)
    dfs: Dict[str, Any] = field(default_factory=dict)
    bfs: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    node_count: int = 0
    notes: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tree_spec": self.tree_spec,
            "headings": list(self.headings),
            "sections": list(self.sections),
            "unverified_sections": list(self.unverified_sections),
            "uncertain": self.uncertain,
            "heuristic": self.heuristic,
            "validation": self.validation,
            "dfs": self.dfs,
            "bfs": self.bfs,
            "signature": self.signature,
            "node_count": self.node_count,
            "notes": list(self.notes),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


def _heading_levels(headings: Sequence[Heading]) -> List[Tuple[str, int]]:
    """Ordered ``(text, level)`` pairs, normalised to a strictly increasing tree."""
    levels: List[Tuple[str, int]] = []
    previous = 0
    for heading in headings:
        level = max(1, min(heading.level, 6))
        if level > previous + 1:
            level = previous + 1  # never skip a level: keeps the tree well-formed
        levels.append((heading.text.strip(), level))
        previous = level
    return levels


def build_structure_tree(headings: Sequence[Heading]) -> Tuple[Dict[str, Any], int]:
    """Build a nested tree spec from ordered ``(text, level)`` headings.

    A level jump deeper than the previous heading creates a child of the last
    heading at the previous level (the standard outline model). Returns
    ``(spec, node_count)``.
    """
    levels = _heading_levels(headings)
    root: Dict[str, Any] = {"name": "Document", "children": []}
    if not levels:
        return root, 1

    # Stack of open containers: stack[i] is the parent list for level i+1.
    stack: List[List[Dict[str, Any]]] = [root["children"]]
    for text, level in levels:
        while len(stack) > level:
            stack.pop()
        while len(stack) < level:
            # Sibling promotion: attach to the deepest open list rather than
            # inventing a level.
            stack.append(stack[-1])
        node = {"name": text[:120], "children": [], "data": {"level": level}}
        if stack:
            stack[-1].append(node)
        else:  # pragma: no cover - defensive
            root["children"].append(node)
        stack.append(node["children"])
    return root, _count_nodes(root)


def _count_nodes(spec: Dict[str, Any]) -> int:
    return 1 + sum(_count_nodes(child) for child in spec.get("children", []))


def analyze_structure(
    extraction: ExtractionResult, spec: Optional[TemplateSpec] = None
) -> StructureResult:
    """Analyse the structure of an extraction result.

    Three sources of structure are tried in order of reliability:

    1. **DOCX heading styles / PDF heading heuristics** — the document's own
       structural signal (``uncertain=False``).
    2. **Template section markers** — for each expected section, the template's
       field labels/aliases are searched in the document; a section becomes a
       tree node only when one of its labels was actually found. Every node is
       therefore *backed by evidence* in the document, which is why this is not
       "inventing sections".
    3. **Nothing** — ``uncertain=True``; the expected sections are reported as
       *not verified*, never as missing.
    """
    started = time.perf_counter()
    result = StructureResult()
    headings = list(extraction.headings or [])

    if headings:
        result.uncertain = False
        methods = {heading.method for heading in headings}
        if "docx_style" in methods:
            result.heuristic = "docx_style"
        elif "all_caps" in methods:
            result.heuristic = "all_caps"
        else:
            result.heuristic = "numbered"
        if len(headings) > _MAX_TREE_NODES:
            headings = headings[:_MAX_TREE_NODES]
            result.notes.append(
                f"Only the first {_MAX_TREE_NODES} headings were used to keep the "
                f"document tree bounded."
            )
        result.headings = [heading.to_dict() for heading in headings]
        tree_spec, node_count = build_structure_tree(headings)
        result.tree_spec = tree_spec
        result.node_count = node_count
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    if spec is not None and (spec.expected_sections or spec.section_order):
        markers = build_section_tree(extraction, spec)
        if markers["sections"]:
            result.uncertain = False
            result.heuristic = "template_section_markers"
            result.sections = markers["sections"]
            result.unverified_sections = markers["unmatched_sections"]
            result.notes.append(
                "No headings were detected; section presence was derived from "
                f"{len(markers['sections'])} template section marker(s) found in "
                "the document text (each node is backed by a matched label)."
            )
            result.tree_spec = markers["tree_spec"]
            result.node_count = _count_nodes(markers["tree_spec"])
            result.elapsed_ms = (time.perf_counter() - started) * 1000
            return result
        result.notes.append(
            "None of the template's section markers were found in the document "
            "text, so section presence cannot be verified."
        )

    result.uncertain = True
    result.heuristic = "none"
    result.notes.append(
        "No reliable headings were detected (no DOCX heading styles, no "
        "ALL-CAPS section lines, no numbered sections). Section presence "
        "cannot be verified for this document."
    )
    if spec is not None and (spec.expected_sections or spec.section_order):
        result.unverified_sections = list(
            spec.expected_sections or spec.section_order or []
        )
    result.tree_spec = {"name": "Document", "children": []}
    result.node_count = 1
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result


def _section_marker_labels(spec: TemplateSpec, section: str) -> List[str]:
    """Labels that evidence ``section`` in a document.

    A template field evidences a section when the field name or one of its
    aliases shares its leading token with the section name
    ("Supplier" <- supplier name/aliases, "Totals" <- total amount/aliases).
    """
    from app.services.field_validation import _search_variants
    from app.services.normalization import normalize_label

    target = normalize_label(section)
    if not target:
        return []
    labels: List[str] = []
    for spec_field in spec.fields:
        candidates = _search_variants(spec_field.name) + list(spec_field.aliases)
        for candidate in candidates:
            normalized = normalize_label(candidate)
            if not normalized:
                continue
            if normalized == target or target.startswith(normalized):
                labels.append(candidate)
                break
    return labels


def build_section_tree(
    extraction: ExtractionResult, spec: TemplateSpec
) -> Dict[str, Any]:
    """Build a tree from template sections that are *evidenced* in the document.

    Returns ``{"sections": [...], "unmatched_sections": [...], "tree_spec": {...}}``.
    Each section entry records the label that evidenced it and where it was
    found, so the report can show *why* a section was considered present.
    """
    from app.services.field_validation import find_label

    pages = [(page.page, page.text) for page in extraction.pages if page.text.strip()]
    if not pages and extraction.full_text.strip():
        pages = [(1, extraction.full_text)]

    sections: List[Dict[str, Any]] = []
    unmatched: List[str] = []
    children: List[Dict[str, Any]] = []
    for section in spec.expected_sections or spec.section_order or []:
        labels = _section_marker_labels(spec, section)
        found: Optional[Dict[str, Any]] = None
        for label in sorted(labels, key=len, reverse=True):
            for page_number, page_text in pages:
                hit, _ = find_label(page_text, page_number, [label])
                if hit is not None:
                    found = {
                        "section": section,
                        "label": hit.matched_label,
                        "page": page_number,
                        "line": hit.line,
                    }
                    break
            if found is not None:
                break
        if found is None:
            unmatched.append(section)
            continue
        sections.append(found)
        children.append(
            {
                "name": section,
                "data": {
                    "label": found["label"],
                    "page": found["page"],
                    "line": found["line"],
                },
                "children": [],
            }
        )
    return {
        "sections": sections,
        "unmatched_sections": unmatched,
        "tree_spec": {"name": "Document", "children": children},
    }


def validate_against_template(
    analysis: StructureResult, spec: TemplateSpec
) -> StructureResult:
    """Validate an analysed structure against a template's expected sections.

    Fills ``validation``, ``dfs`` and ``bfs`` on ``analysis`` in place and
    returns it. When the analysis was *uncertain* the expected sections are
    moved to ``unverified_sections`` instead of being reported missing.
    """
    started = time.perf_counter()
    required = list(spec.expected_sections or spec.section_order or [])

    tree = build_tree(analysis.tree_spec)
    validation = validate_structure(tree, required)
    analysis.validation = validation.to_dict()
    dfs_result = dfs(tree)
    bfs_result = bfs(tree)
    analysis.dfs = dfs_result.to_dict()
    analysis.bfs = bfs_result.to_dict()
    analysis.signature = structural_signature(tree)
    analysis.notes.append(
        f"Structure validated against {len(required)} expected section(s) of "
        f"template {spec.name!r} (DFS visited {dfs_result.visited_count} nodes, "
        f"max depth {dfs_result.max_depth})."
    )
    if analysis.uncertain:
        analysis.unverified_sections = list(required)
        analysis.notes.append(
            "Section presence was NOT verified: the document structure could not "
            "be read reliably, so no section is reported as missing."
        )
    elif required:
        if validation.missing:
            analysis.notes.append(
                f"Missing sections (reliably detected): "
                f"{', '.join(validation.missing)}."
            )
        if not validation.order_ok:
            analysis.notes.append(
                "Detected sections do not appear in the template's expected order."
            )
    analysis.elapsed_ms = (time.perf_counter() - started) * 1000
    return analysis


def compare_document_structures(
    analysis_a: StructureResult, analysis_b: StructureResult
) -> Dict[str, Any]:
    """Compare two analysed structures by their DFS leaf signatures."""
    tree_a = build_tree(analysis_a.tree_spec)
    tree_b = build_tree(analysis_b.tree_spec)
    from app.algorithms.tree_traversal import compare_structures

    comparison = compare_structures(tree_a, tree_b)
    comparison["uncertain"] = bool(analysis_a.uncertain or analysis_b.uncertain)
    return comparison


def structure_has_issues(analysis: StructureResult) -> bool:
    """True when the structural stage found something worth reporting (rule R007).

    Only *reliably detected* problems count: an uncertain structure reports
    nothing (it reports its own uncertainty instead).
    """
    if analysis.uncertain:
        return False
    validation = analysis.validation or {}
    if validation.get("missing"):
        return True
    if validation.get("order_ok") is False:
        return True
    for issue in validation.get("issues", []):
        if issue.get("type") == "order_violation":
            return True
    return False


def section_names(analysis: StructureResult) -> List[str]:
    """Return the detected heading texts (helper for reports)."""
    return [heading["text"] for heading in analysis.headings]


def tree_node_summary(node: Optional[DocumentNode]) -> Dict[str, Any]:
    """Summarise a node for the API layer (debug/inspection helper)."""
    if node is None:
        return {"nodes": 0, "max_depth": 0}
    return {
        "nodes": dfs(node).visited_count,
        "max_depth": bfs(node).max_depth,
        "name": node.name,
    }
