"""Maximum bipartite matching via a max-flow reduction (Edmonds-Karp).

Purpose
-------
Assign extracted document fields (right side) to expected template fields
(left side) so that no expected field claims more than one extracted field and
no extracted field is claimed twice. This is the maximum-cardinality bipartite
matching problem.

Construction
------------
A flow network is built:

    source -> expected field nodes   (capacity 1)
    expected field -> extracted field (capacity 1, only for compatible pairs)
    extracted field -> sink          (capacity 1)

Integral max flow then saturates exactly the matched pairs.

Algorithm
---------
Ford-Fulkerson with BFS augmenting paths (Edmonds-Karp): while a path from
source to sink exists in the residual graph, push one unit of flow and flip the
residual edges along the path.

Complexity
----------
* Edmonds-Karp: O(V * E^2) here, i.e. O(L * R * (L + R)) for L expected and R
  extracted fields. For document-scale inputs (tens of fields) this is
  instantaneous.
* Max cardinality does NOT maximise confidence: edges are thresholded by a
  deterministic compatibility rule and ties break by input order.

Correctness
-----------
By the Max-Flow Min-Cut theorem (and integrality of capacities), an integral
maximum flow decomposes into edge-disjoint source-sink paths, which correspond
one-to-one with a maximum matching.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from app.algorithms.lcs import lcs_similarity

_MAX_AUGMENTING_PATHS = 200

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_label(label: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to single spaces, strip."""
    return _NORMALIZE_RE.sub(" ", label.lower()).strip()


def _types_compatible(expected_type: str, extracted_type: str) -> bool:
    return (
        expected_type in ("", "unknown")
        or extracted_type in ("", "unknown")
        or expected_type == extracted_type
    )


def _expected_field_name(field) -> str:
    if isinstance(field, dict):
        return str(field.get("name", field.get("label", "")))
    return str(field)


def _extracted_field_name(field) -> str:
    if isinstance(field, dict):
        return str(field.get("label", field.get("name", "")))
    return str(field)


def _field_type(field) -> str:
    if isinstance(field, dict):
        return str(field.get("data_type", field.get("type", "unknown")) or "unknown")
    return "unknown"


def build_matching_problem(
    expected_fields: list,
    extracted_fields: list,
    similarity_threshold: float = 0.6,
    aliases: Optional[dict[str, set[str]]] = None,
) -> dict:
    """Build the bipartite problem from template and extracted fields.

    Compatibility is deterministic, in priority order:

    1. exact normalized-label match (lowercased, non-alphanumerics collapsed);
    2. an approved alias hit — ``aliases`` maps an expected field name to a set
       of accepted alternative labels (normalized before comparison);
    3. label similarity at or above ``similarity_threshold`` combined with
       compatible value types.

    Returns ``{"expected": [...], "extracted": [...], "edges": [...]}`` where
    each edge carries its rule and similarity.
    """
    expected = [_expected_field_name(f) for f in expected_fields]
    extracted = [_extracted_field_name(f) for f in extracted_fields]
    norm_expected = [_normalize_label(e) for e in expected]
    norm_extracted = [_normalize_label(x) for x in extracted]
    alias_map: dict[str, set[str]] = {}
    for key, values in (aliases or {}).items():
        alias_map[_normalize_label(key)] = {
            _normalize_label(v) for v in values
        }

    edges: list[dict] = []
    for i, e in enumerate(expected):
        for j, x in enumerate(extracted):
            if not e or not x:
                continue
            if not _types_compatible(
                _field_type(expected_fields[i]), _field_type(extracted_fields[j])
            ):
                continue
            if norm_expected[i] == norm_extracted[j]:
                edges.append({
                    "expected": e, "extracted": x,
                    "similarity": 1.0, "rule": "exact_label",
                })
                continue
            approved = alias_map.get(norm_expected[i], set())
            if norm_extracted[j] in approved:
                edges.append({
                    "expected": e, "extracted": x,
                    "similarity": 1.0, "rule": "alias",
                })
                continue
            similarity = lcs_similarity(norm_expected[i], norm_extracted[j])
            if similarity >= similarity_threshold:
                edges.append({
                    "expected": e, "extracted": x,
                    "similarity": round(similarity, 4),
                    "rule": "similar_label",
                })
    return {"expected": expected, "extracted": extracted, "edges": edges}


class BipartiteGraph:
    """Adjacency structure for a bipartite matching problem."""

    def __init__(self, problem: dict) -> None:
        self.left: list[str] = list(problem.get("expected", []))
        self.right: list[str] = list(problem.get("extracted", []))
        self.edges: list[dict] = list(problem.get("edges", []))
        self.adj: dict[str, list[str]] = {}
        for edge in self.edges:
            self.adj.setdefault(edge["expected"], []).append(edge["extracted"])


class MatchingResult:
    """Result of :func:`bipartite_match`."""

    def __init__(
        self,
        matching: list[tuple[str, str]],
        unmatched_expected: list[str],
        unmatched_extracted: list[str],
        augmenting_paths: list[dict],
        edge_details: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.matching: list[tuple[str, str]] = matching
        self.matched_expected: list[str] = [p[0] for p in matching]
        self.matched_extracted: list[str] = [p[1] for p in matching]
        self.unmatched_expected: list[str] = unmatched_expected
        self.unmatched_extracted: list[str] = unmatched_extracted
        self.max_matching_size: int = len(matching)
        self.max_flow: int = len(matching)
        self.augmenting_paths: list[dict] = augmenting_paths
        self.edge_details: list[dict] = edge_details
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        return {
            "matching": [list(p) for p in self.matching],
            "matched_expected": list(self.matched_expected),
            "matched_extracted": list(self.matched_extracted),
            "unmatched_expected": list(self.unmatched_expected),
            "unmatched_extracted": list(self.unmatched_extracted),
            "max_matching_size": self.max_matching_size,
            "max_flow": self.max_flow,
            "augmenting_paths": [dict(p) for p in self.augmenting_paths],
            "edge_details": [dict(e) for e in self.edge_details],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"MatchingResult(size={self.max_matching_size})"


def bipartite_match(problem: dict) -> MatchingResult:
    """Compute a maximum bipartite matching via Edmonds-Karp augmenting paths.

    ``problem`` is the dict produced by :func:`build_matching_problem`.
    """
    start_ns = time.perf_counter_ns()
    graph = BipartiteGraph(problem)
    left, right, adj = graph.left, graph.right, graph.adj

    match_right: dict[str, Optional[str]] = {r: None for r in right}
    match_left: dict[str, Optional[str]] = {l: None for l in left}
    augmenting_paths: list[dict] = []

    for u in left:
        # BFS for an augmenting path from u (Kuhn's algorithm over the
        # equality graph == Edmonds-Karp on the unit-capacity flow network).
        # NOTE: ``visited`` tracks RIGHT-side nodes only. Left- and right-side
        # node names may collide (a field can appear on both sides), so the
        # start node must not be pre-seeded into the visited set.
        parent: dict[str, Optional[str]] = {}
        queue = [u]
        visited: set[str] = set()
        found: Optional[str] = None
        while queue and found is None:
            current = queue.pop(0)
            for v in adj.get(current, []):
                if v in visited:
                    continue
                visited.add(v)
                parent[v] = current
                if match_right[v] is None:
                    found = v
                    break
                # Walk back through the alternating path.
                nxt = match_right[v]
                parent.setdefault(nxt, v)
                queue.append(nxt)
        if found is not None:
            # Augment: flip assignments along the discovered alternating path.
            flips: list[tuple[str, str, Optional[str]]] = []
            v = found
            while v is not None:
                l_node = parent.get(v)
                if l_node is None:
                    break
                prev_right = match_left[l_node]
                flips.append((l_node, v, prev_right))
                match_left[l_node] = v
                match_right[v] = l_node
                v = prev_right
            if len(augmenting_paths) < _MAX_AUGMENTING_PATHS:
                augmenting_paths.append({
                    "start": u,
                    "path": [u] + [x for pair in flips for x in pair[:2]],
                    "assignments": [
                        {"expected": l, "extracted": r} for l, r, _ in flips
                    ],
                    "displaced": [d for _, _, d in flips if d is not None],
                })

    matching = sorted(
        (l, r) for l, r in match_left.items() if r is not None
    )
    unmatched_expected = sorted(l for l in left if match_left[l] is None)
    unmatched_extracted = sorted(r for r in right if match_right[r] is None)

    return MatchingResult(
        matching=matching,
        unmatched_expected=unmatched_expected,
        unmatched_extracted=unmatched_extracted,
        augmenting_paths=augmenting_paths,
        edge_details=graph.edges,
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )
