"""Document tree traversal & structural validation for DocuTrace.

Purpose
-------
A parsed document is modelled as a tree of :class:`DocumentNode`s (e.g. a root
"Document" containing "Header", "Body", "Footer" sections, each with their own
sub-fields). This module provides depth-first and breadth-first traversal, a
structural signature for template fingerprinting, ordering/presence validation
against a required-sections spec, and a structural diff between two documents.

DocuTrace use case
------------------
After OCR + field extraction, two documents built from the same template share
the same *section structure* even if the field *values* differ. Comparing
structural signatures lets DocuTrace decide "same template, different record"
before running the value-level comparisons.

Complexity
----------
* ``dfs`` / ``bfs`` traverse every node and edge once: time O(V + E).
* Space depends on method and tree shape:
  - DFS (recursive) holds the current root-to-node path: O(h) where h = height.
  - BFS holds the current frontier in a queue: O(w) where w = maximum breadth.
* ``validate_structure`` is O(V) for the tree scan plus O(P * V) for path probes
  (P = number of required sections); trivial for realistic document trees.
* ``structural_signature`` is O(V) time, O(V) space for the emitted paths.

Cycle-safety: :meth:`DocumentNode.add_child` refuses to link an ancestor as a
descendant (raising ``ValueError``), so a malformed spec cannot hang traversal.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from typing import Optional, Union

_MAX_TRACE = 500


class DocumentNode:
    """A node in the document tree.

    Attributes ``id``, ``name``, ``data``, ``children`` are part of the node;
    ``parent`` is a back-reference used for navigation and cycle checks and is
    *never* serialized (see :meth:`to_dict`).
    """

    def __init__(
        self,
        name: str,
        data: Optional[dict] = None,
        node_id: Optional[str] = None,
    ) -> None:
        self.id: str = node_id if node_id is not None else uuid.uuid4().hex
        self.name: str = name
        self.data: dict = data if data is not None else {}
        self.children: list[DocumentNode] = []
        self.parent: Optional[DocumentNode] = None

    def add_child(self, node: "DocumentNode") -> "DocumentNode":
        """Attach ``node`` as the last child. Raises ``ValueError`` on a cycle."""
        if node is self:
            raise ValueError("Cannot add a node as a child of itself (cycle).")
        # Refuse to link an ancestor of self as a descendant.
        ancestor = self.parent
        while ancestor is not None:
            if ancestor is node:
                raise ValueError(
                    "Cannot add an ancestor as a child (would create a cycle)."
                )
            ancestor = ancestor.parent
        node.parent = self
        self.children.append(node)
        return node

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (the parent link is never included)."""
        return {
            "id": self.id,
            "name": self.name,
            "data": dict(self.data),
            "children": [child.to_dict() for child in self.children],
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"DocumentNode(name={self.name!r}, children={len(self.children)})"


def _build_node(spec: dict) -> DocumentNode:
    node = DocumentNode(spec.get("name", "Unnamed"), data=spec.get("data", {}))
    for child_spec in spec.get("children", []) or []:
        node.add_child(_build_node(child_spec))
    return node


def build_tree(spec: Union[dict, list]) -> DocumentNode:
    """Build a :class:`DocumentNode` tree from a nested spec.

    ``spec`` is either a single dict ``{"name", "data"?, "children"?}`` or a list
    of such dicts (wrapped under a synthetic root named "Document").
    """
    if isinstance(spec, list):
        root = DocumentNode("Document")
        for child_spec in spec:
            root.add_child(_build_node(child_spec))
        return root
    return _build_node(spec)


class TraversalResult:
    """Result of :func:`dfs` / :func:`bfs`."""

    def __init__(
        self,
        order: list[str],
        steps: list[dict],
        visited_count: int,
        max_depth: int,
        elapsed_ns: int,
    ) -> None:
        self.order: list[str] = order
        self.steps: list[dict] = steps
        self.visited_count: int = visited_count
        self.max_depth: int = max_depth
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "steps": [dict(step) for step in self.steps],
            "visited_count": self.visited_count,
            "max_depth": self.max_depth,
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"TraversalResult(visited={self.visited_count}, "
            f"max_depth={self.max_depth})"
        )


def dfs(root: DocumentNode, trace: bool = False) -> TraversalResult:
    """Pre-order depth-first traversal of ``root``. Time O(V + E), space O(h)."""
    start_ns = time.perf_counter_ns()
    order: list[str] = []
    steps: list[dict] = []
    visited = 0
    max_depth = 0
    path: list[str] = []

    def rec(node: DocumentNode, depth: int) -> None:
        nonlocal visited, max_depth
        order.append(node.name)
        visited += 1
        if depth > max_depth:
            max_depth = depth
        if trace and len(steps) < _MAX_TRACE:
            steps.append({
                "node": node.name, "depth": depth, "action": "visit",
                "stack": list(path) + [node.name],
            })
        path.append(node.name)
        for child in node.children:
            rec(child, depth + 1)
        path.pop()
        if trace and len(steps) < _MAX_TRACE:
            steps.append({
                "node": node.name, "depth": depth, "action": "backtrack",
                "stack": list(path),
            })

    if root is not None:
        rec(root, 0)
    return TraversalResult(order, steps, visited, max_depth,
                           time.perf_counter_ns() - start_ns)


def bfs(root: DocumentNode, trace: bool = False) -> TraversalResult:
    """Level-order (breadth-first) traversal of ``root``. O(V+E), space O(w)."""
    start_ns = time.perf_counter_ns()
    order: list[str] = []
    steps: list[dict] = []
    visited = 0
    max_depth = 0

    if root is not None:
        queue: deque[tuple[DocumentNode, int]] = deque([(root, 0)])
        while queue:
            node, depth = queue.popleft()
            order.append(node.name)
            visited += 1
            if depth > max_depth:
                max_depth = depth
            if trace and len(steps) < _MAX_TRACE:
                steps.append({
                    "node": node.name, "depth": depth, "action": "visit",
                    "queue": [n.name for n, _ in queue],
                })
            for child in node.children:
                queue.append((child, depth + 1))

    return TraversalResult(order, steps, visited, max_depth,
                           time.perf_counter_ns() - start_ns)


# --------------------------------------------------------------------------- #
# Structural validation & comparison
# --------------------------------------------------------------------------- #
class StructureValidation:
    """Result of :func:`validate_structure`."""

    def __init__(
        self,
        present: list[str],
        missing: list[str],
        extra_sections: list[str],
        order_ok: bool,
        issues: list[dict],
    ) -> None:
        self.present: list[str] = present
        self.missing: list[str] = missing
        self.extra_sections: list[str] = extra_sections
        self.order_ok: bool = order_ok
        self.issues: list[dict] = issues

    def to_dict(self) -> dict:
        return {
            "present": list(self.present),
            "missing": list(self.missing),
            "extra_sections": list(self.extra_sections),
            "order_ok": self.order_ok,
            "issues": [dict(issue) for issue in self.issues],
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"StructureValidation(present={len(self.present)}, "
            f"missing={len(self.missing)}, order_ok={self.order_ok})"
        )


def _path_exists(node: DocumentNode, components: list[str]) -> bool:
    """True if the dotted path of names exists starting under ``node``."""
    if not components:
        return True
    head = components[0]
    for child in node.children:
        if child.name == head and _path_exists(child, components[1:]):
            return True
    return False


def _name_exists_anywhere(node: DocumentNode, name: str) -> bool:
    if node.name == name:
        return True
    return any(_name_exists_anywhere(child, name) for child in node.children)


def _required_present(root: DocumentNode, section: str) -> bool:
    if "/" in section:
        return _path_exists(root, section.split("/"))
    return _name_exists_anywhere(root, section)


def validate_structure(
    root: DocumentNode, required_sections: list[str]
) -> StructureValidation:
    """Validate ``root`` against ``required_sections``.

    Each required section is a dotted path (``"Header/Title"``, anchored at the
    root) or a plain name (matched anywhere). Reports presence, order
    conformance of the root children, and unexpected (informational) sections.
    """
    present: list[str] = []
    missing: list[str] = []
    issues: list[dict] = []

    for section in required_sections:
        if _required_present(root, section):
            present.append(section)
        else:
            missing.append(section)
            # ``detail`` carries the bare section name. Consumers render the
            # wording themselves ("missing section (Header)"), so baking a
            # sentence in here produced "missing section (Missing required
            # section: Header)".
            issues.append({
                "type": "missing_section",
                "detail": section,
            })

    # Ordering of the root's direct children vs the required top-level order.
    required_top: list[str] = []
    recognized: set[str] = set()
    for section in required_sections:
        components = section.split("/")
        for comp in components:
            recognized.add(comp)
        top = components[0]
        if top not in required_top:
            required_top.append(top)

    root_child_names = {child.name for child in root.children}
    actual_order = [c.name for c in root.children if c.name in required_top]
    expected_order = [t for t in required_top if t in root_child_names]
    order_ok = actual_order == expected_order
    if not order_ok:
        issues.append({
            "type": "order_violation",
            "detail": (
                f"expected {' > '.join(expected_order) or 'nothing'}, "
                f"found {' > '.join(actual_order) or 'nothing'}"
            ),
        })

    # Extra (informational) sections: names present in the tree but not required.
    extra_sections: list[str] = []
    stack = list(root.children)  # exclude the root's own name
    while stack:
        node = stack.pop()
        if node.name not in recognized and node.name not in extra_sections:
            extra_sections.append(node.name)
            issues.append({
                "type": "unexpected_section",
                "detail": node.name,
            })
        for child in node.children:
            stack.append(child)

    return StructureValidation(
        present=present,
        missing=missing,
        extra_sections=extra_sections,
        order_ok=order_ok,
        issues=issues,
    )


def structural_signature(root: DocumentNode) -> str:
    """Return the '; '-joined DFS leaf paths, e.g. ``"Header/Title; ..."``.

    A leaf path is the '/'-joined chain of names from the root to a node that
    has no children. Leaves are emitted in DFS pre-order.
    """
    parts: list[str] = []

    def rec(node: DocumentNode, prefix: str) -> None:
        if not node.children:
            parts.append(prefix if prefix else node.name)
            return
        for child in node.children:
            child_prefix = f"{prefix}/{child.name}" if prefix else child.name
            rec(child, child_prefix)

    rec(root, "")
    return "; ".join(parts)


def compare_structures(root_a: DocumentNode, root_b: DocumentNode) -> dict:
    """Compare two document trees by their structural signatures."""
    sig_a = structural_signature(root_a)
    sig_b = structural_signature(root_b)
    paths_a = [p for p in sig_a.split("; ") if p]
    paths_b = [p for p in sig_b.split("; ") if p]
    set_a = set(paths_a)
    set_b = set(paths_b)
    only_in_a = [p for p in paths_a if p not in set_b]
    only_in_b = [p for p in paths_b if p not in set_a]
    common = [p for p in paths_a if p in set_b]
    return {
        "signature_a": sig_a,
        "signature_b": sig_b,
        "identical": paths_a == paths_b,
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "common": common,
    }
