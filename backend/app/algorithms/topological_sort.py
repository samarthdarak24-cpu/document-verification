"""Topological sorting (Kahn's algorithm) over the verification pipeline DAG.

Purpose
-------
DocuTrace's verification pipeline is a set of stages with dependencies:

    upload -> file_validation -> text_extraction -> normalization
    normalization -> field_detection -> field_validation -> report_generation
    normalization -> hashing -> duplicate_lookup -> report_generation
    normalization -> candidate_retrieval -> similarity_analysis -> report_generation

 ``topological_sort`` computes a valid execution order for these stages and
raises :class:`CycleError` when the dependency graph contains a cycle (no valid
order exists). Kahn's algorithm repeatedly removes a node with in-degree 0,
which is exactly the set of stages whose prerequisites are all satisfied.

DocuTrace use case
------------------
The pipeline scheduler orders verification stages; the Algorithm Laboratory
demonstrates the same routine on an arbitrary user-supplied DAG.

Complexity
----------
* Time O(V + E): every node is enqueued/dequeued once and every edge is
  scanned once when its source node is removed.
* Space O(V + E): adjacency list plus the in-degree map and queue.

Correctness sketch (loop invariant)
----------------------------------
At the start of each iteration, the queue contains exactly the nodes with
in-degree 0 among the not-yet-ordered nodes. If the graph is acyclic this set
is non-empty until every node has been ordered (a finite DAG always has at
least one source). Every emitted prefix respects all edges because a node is
only emitted after all its predecessors. If nodes remain while no in-degree-0
node exists, the remainder contains a cycle.
"""

from __future__ import annotations

import time
from typing import Optional

_MAX_TRACE = 500


class CycleError(ValueError):
    """Raised when the input graph contains a directed cycle."""


class TopologicalSortResult:
    """Result of a :func:`topological_sort` call."""

    def __init__(
        self,
        order: list[str],
        node_count: int,
        edge_count: int,
        steps: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.order: list[str] = order
        self.node_count: int = node_count
        self.edge_count: int = edge_count
        self.steps: list[dict] = steps
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "steps": [dict(s) for s in self.steps],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"TopologicalSortResult(order={self.order})"


def topological_sort(
    nodes: list[str],
    edges: list[tuple[str, str]],
    trace: bool = False,
) -> TopologicalSortResult:
    """Return a topological ordering of ``nodes`` with dependencies ``edges``.

    Parameters
    ----------
    nodes:
        Node identifiers (verification stage names).
    edges:
        Directed edges ``(u, v)`` meaning *u must run before v*.
    trace:
        When True, record Kahn's algorithm steps (capped at 500).

    Raises
    ------
    CycleError
        If the graph contains a directed cycle.
    """
    start_ns = time.perf_counter_ns()
    node_set = set(nodes)
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    indegree: dict[str, int] = {n: 0 for n in nodes}

    for u, v in edges:
        if u not in node_set or v not in node_set:
            raise ValueError(f"edge ({u!r}, {v!r}) references unknown node")
        adjacency[u].append(v)
        indegree[v] += 1

    # Deterministic ordering: always take the alphabetically smallest source.
    queue = sorted(n for n in nodes if indegree[n] == 0)
    order: list[str] = []
    steps: list[dict] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        if trace and len(steps) < _MAX_TRACE:
            steps.append({
                "removed": node,
                "remaining": sorted(n for n in nodes if n not in set(order)),
                "reason": "in-degree 0: all prerequisites satisfied",
            })
        for neighbor in adjacency[node]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()

    if len(order) != len(nodes):
        remaining = sorted(n for n in nodes if n not in set(order))
        raise CycleError(
            "Dependency graph contains a cycle; no valid execution order "
            f"exists. Unorderable stages: {remaining}"
        )

    return TopologicalSortResult(
        order=order,
        node_count=len(nodes),
        edge_count=len(edges),
        steps=steps if trace else [],
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )


def verification_pipeline_dag() -> dict:
    """Return the DocuTrace verification pipeline as (nodes, edges).

    The DAG mirrors ``app/pipeline/processing.py``: text-only stages feed
    hashing/duplicate lookup and candidate retrieval/similarity analysis, and
    every analytical path feeds report generation.
    """
    nodes = [
        "upload",
        "file_validation",
        "text_extraction",
        "normalization",
        "field_detection",
        "field_validation",
        "hashing",
        "duplicate_lookup",
        "candidate_retrieval",
        "similarity_analysis",
        "structural_validation",
        "verification_decision",
        "report_generation",
    ]
    edges = [
        ("upload", "file_validation"),
        ("file_validation", "text_extraction"),
        ("text_extraction", "normalization"),
        ("normalization", "field_detection"),
        ("field_detection", "field_validation"),
        ("normalization", "hashing"),
        ("hashing", "duplicate_lookup"),
        ("normalization", "candidate_retrieval"),
        ("candidate_retrieval", "similarity_analysis"),
        ("normalization", "structural_validation"),
        ("field_validation", "verification_decision"),
        ("duplicate_lookup", "verification_decision"),
        ("similarity_analysis", "verification_decision"),
        ("structural_validation", "verification_decision"),
        ("verification_decision", "report_generation"),
    ]
    return {"nodes": nodes, "edges": edges}
