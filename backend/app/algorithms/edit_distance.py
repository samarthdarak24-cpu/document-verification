"""Levenshtein edit distance between two documents (character or token level).

Purpose
-------
Measure how many single-element edits (insert / delete / substitute) separate one
string from another. The distance converts to a normalised similarity
``1 - d / max(len)`` that DocuTrace uses as a stricter, position-sensitive
comparator than LCS for short values like reference numbers, dates, or names.

Strings are compared character-by-character; sequences (lists/tuples) are
compared element-by-element (e.g. already-tokenised word lists).

DocuTrace use case
------------------
- Fine-grained verification of extracted fields (invoice number, date) where a
  one- or two-character OCR slip should still count as "the same" value.
- Ranking near-duplicate documents that differ only by a few tokens.

Complexity
----------
* Full DP with reconstruction:
  - Time O(n*m), space O(n*m) for the matrix (n = len(a), m = len(b)).
* Two-row optimization (:func:`edit_distance_optimized`):
  - Time O(n*m), space O(min(n, m)); the shorter sequence drives the columns.
* Backtracking to recover the edit script is O(n + m).
"""

from __future__ import annotations

import time
from typing import Optional, Sequence, Union


def _resolve(seq: Union[str, Sequence]) -> list:
    """Strings become a list of characters; sequences become a list of items."""
    if isinstance(seq, str):
        return list(seq)
    return list(seq)


class EditDistanceResult:
    """Result of an :func:`edit_distance` call."""

    def __init__(
        self,
        distance: int,
        similarity: float,
        operations: list[dict],
        matrix: Optional[list[list[int]]],
        dp_cell_updates: int,
        elapsed_ns: int,
    ) -> None:
        self.distance: int = distance
        self.similarity: float = similarity
        self.operations: list[dict] = operations
        self.matrix: Optional[list[list[int]]] = matrix  # only if with_operations
        self.dp_cell_updates: int = dp_cell_updates
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "distance": self.distance,
            "similarity": self.similarity,
            "operations": [dict(op) for op in self.operations],
            "matrix": [list(row) for row in self.matrix]
            if self.matrix is not None else None,
            "dp_cell_updates": self.dp_cell_updates,
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"EditDistanceResult(distance={self.distance}, "
            f"similarity={self.similarity:.4f})"
        )


def _two_row_distance(sa: list, sb: list) -> tuple[int, int]:
    """Return ``(distance, dp_cell_updates)`` using O(min(n,m)) space."""
    if len(sb) > len(sa):
        sa, sb = sb, sa
    n, m = len(sa), len(sb)
    prev = list(range(m + 1))
    updates = 0
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        ai = sa[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == sb[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # deletion
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + cost,  # substitution / match
            )
            updates += 1
        prev = curr
    return prev[m], updates


def _full_matrix(sa: list, sb: list) -> tuple[list[list[int]], int]:
    """Return ``(matrix, dp_cell_updates)`` with the complete DP table."""
    n, m = len(sa), len(sb)
    matrix = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, m + 1):
        matrix[0][i] = i
    for i in range(1, n + 1):
        matrix[i][0] = i
    updates = 0
    for i in range(1, n + 1):
        ai = sa[i - 1]
        row = matrix[i]
        prev = matrix[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == sb[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
            updates += 1
    return matrix, updates


def _backtrack(sa: list, sb: list, matrix: list[list[int]]) -> list[dict]:
    """Reconstruct the forward edit script that transforms ``sa`` into ``sb``.

    Each operation records ``position`` as an index into the *source* sequence
    ``sa`` (a delete/substitute at that index, or an insert at that gap). See
    the test suite for the exact apply-semantics.
    """
    n, m = len(sa), len(sb)
    i, j = n, m
    ops: list[dict] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and sa[i - 1] == sb[j - 1]:
            i -= 1
            j -= 1  # match: no operation
        elif i > 0 and j > 0 and matrix[i][j] == matrix[i - 1][j - 1] + 1:
            ops.append({"op": "substitute", "position": i - 1,
                        "old": sa[i - 1], "new": sb[j - 1]})
            i -= 1
            j -= 1
        elif i > 0 and matrix[i][j] == matrix[i - 1][j] + 1:
            ops.append({"op": "delete", "position": i - 1,
                        "old": sa[i - 1], "new": None})
            i -= 1
        else:  # insert: j > 0 here
            ops.append({"op": "insert", "position": i,
                        "old": None, "new": sb[j - 1]})
            j -= 1
    ops.reverse()
    return ops


def edit_distance(
    a: Union[str, Sequence],
    b: Union[str, Sequence],
    with_operations: bool = False,
) -> EditDistanceResult:
    """Compute the Levenshtein distance between ``a`` and ``b``.

    Strings are compared character-level; sequences element-level. When
    ``with_operations`` is True the full DP matrix is built and a reconstructable
    edit script is returned; otherwise an O(min(n,m))-space DP is used and the
    matrix is ``None``.
    """
    start_ns = time.perf_counter_ns()
    sa = _resolve(a)
    sb = _resolve(b)
    n, m = len(sa), len(sb)

    operations: list[dict] = []
    matrix: Optional[list[list[int]]] = None

    if with_operations:
        matrix, dp_cell_updates = _full_matrix(sa, sb)
        distance = matrix[n][m]
        operations = _backtrack(sa, sb, matrix)
    else:
        distance, dp_cell_updates = _two_row_distance(sa, sb)

    if n == 0 and m == 0:
        similarity = 1.0
    else:
        similarity = 1.0 - (distance / max(n, m))

    elapsed_ns = time.perf_counter_ns() - start_ns
    return EditDistanceResult(
        distance=distance,
        similarity=similarity,
        operations=operations,
        matrix=matrix,
        dp_cell_updates=dp_cell_updates,
        elapsed_ns=elapsed_ns,
    )


def edit_distance_optimized(
    a: Union[str, Sequence], b: Union[str, Sequence]
) -> tuple[int, int]:
    """Return ``(distance, dp_cell_updates)`` using O(min(n,m)) space."""
    sa = _resolve(a)
    sb = _resolve(b)
    return _two_row_distance(sa, sb)


def edit_distance_sequences(a: Sequence, b: Sequence) -> int:
    """Return the element-level edit distance without reconstruction."""
    sa = _resolve(a)
    sb = _resolve(b)
    distance, _ = _two_row_distance(sa, sb)
    return distance
