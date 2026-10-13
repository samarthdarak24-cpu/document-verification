"""Longest Common Subsequence (LCS) — word-level document similarity.

Purpose
-------
The LCS is the longest sequence of tokens that appears (in order, but not
necessarily contiguously) in both documents. Its length feeds a normalised
similarity score that is robust to insertions/reorderings, making it a good
first-line "how much of these documents is shared?" measure for DocuTrace.

By default inputs are *tokenised* into lowercase alphanumeric words so two
documents whose only difference is punctuation/casing still score well. The DP
core also accepts pre-tokenised sequences (lists/tuples) directly.

DocuTrace use case
------------------
Estimating shared content between two extracted documents (e.g. two invoices
printed from the same template) before the exact per-field verification step.

Complexity
----------
* ``lcs_dp`` (full matrix + backtrack):
  - Time O(n*m), space O(n*m) for the matrix (n = len(a), m = len(b)).
* ``lcs_length_optimized`` (two-row DP):
  - Time O(n*m), space O(min(n, m)) — the shorter sequence drives the columns.
* Backtracking to recover the alignment is O(n + m).

To bound memory, ``lcs_dp`` stores and returns the full matrix *only* when
``n*m <= 250_000``; above that threshold the matrix is set to ``None`` and only
the length / similarity are produced (use :func:`lcs_length_optimized` for the
same time guarantee in bounded space).

Unicode-safe: tokenisation is Unicode-aware (non-``_`` word characters).
"""

from __future__ import annotations

import re
import time
from typing import Optional, Sequence, Union

# Above this many DP cells the full matrix is not materialised (memory guard).
_MATRIX_CELL_LIMIT = 250_000

# Unicode-aware alphanumeric token: word characters excluding underscore.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Split ``text`` into lowercase alphanumeric word tokens (Unicode-safe)."""
    return _TOKEN_RE.findall(text.lower())


def _resolve(seq: Union[str, Sequence[str]]) -> list[str]:
    """Tokenise a string, or pass through an already-tokenised sequence."""
    if isinstance(seq, str):
        return tokenize(seq)
    return list(seq)


class LCSResult:
    """Result of a :func:`lcs_dp` call."""

    def __init__(
        self,
        length: int,
        similarity: float,
        matrix: Optional[list[list[int]]],
        dp_cell_updates: int,
        alignment: list[dict],
        matched_tokens: list,
        unmatched_a: list,
        unmatched_b: list,
        elapsed_ns: int,
    ) -> None:
        self.length: int = length
        self.similarity: float = similarity
        self.matrix: Optional[list[list[int]]] = matrix
        self.dp_cell_updates: int = dp_cell_updates
        self.alignment: list[dict] = alignment
        self.matched_tokens: list = matched_tokens
        self.unmatched_a: list = unmatched_a
        self.unmatched_b: list = unmatched_b
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "length": self.length,
            "similarity": self.similarity,
            "matrix": [list(row) for row in self.matrix]
            if self.matrix is not None else None,
            "dp_cell_updates": self.dp_cell_updates,
            "alignment": [dict(step) for step in self.alignment],
            "matched_tokens": list(self.matched_tokens),
            "unmatched_a": list(self.unmatched_a),
            "unmatched_b": list(self.unmatched_b),
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"LCSResult(length={self.length}, "
            f"similarity={self.similarity:.4f})"
        )


def _similarity(length: int, len_a: int, len_b: int) -> float:
    if len_a == 0 and len_b == 0:
        return 1.0
    return 2.0 * length / (len_a + len_b)


def lcs_dp(a: Union[str, Sequence[str]], b: Union[str, Sequence[str]]) -> LCSResult:
    """Compute the LCS of ``a`` and ``b`` with a full DP matrix + backtrack.

    Strings are tokenised first; sequences are used as-is. Returns an
    :class:`LCSResult`. The matrix is ``None`` when ``len(a)*len(b)`` exceeds
    the internal memory guard (see module docstring), in which case the
    alignment is also omitted.
    """
    start_ns = time.perf_counter_ns()
    ta = _resolve(a)
    tb = _resolve(b)
    n, m = len(ta), len(tb)

    build_matrix = (n * m) <= _MATRIX_CELL_LIMIT

    dp_cell_updates = 0
    matrix: Optional[list[list[int]]] = None

    if build_matrix:
        # matrix[i][j] = LCS length of ta[:i], tb[:j]
        matrix = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            row = matrix[i]
            prev = matrix[i - 1]
            ai = ta[i - 1]
            for j in range(1, m + 1):
                if ai == tb[j - 1]:
                    row[j] = prev[j - 1] + 1
                else:
                    row[j] = prev[j] if prev[j] >= row[j - 1] else row[j - 1]
                dp_cell_updates += 1
        length = matrix[n][m]
    else:
        length, dp_cell_updates = lcs_length_optimized(ta, tb)

    alignment: list[dict] = []
    matched_tokens: list = []
    unmatched_a: list = []
    unmatched_b: list = []

    if build_matrix and matrix is not None:
        # Backtrack from the bottom-right corner, then reverse to start order.
        i, j = n, m
        while i > 0 and j > 0:
            if ta[i - 1] == tb[j - 1]:
                alignment.append({
                    "a_token": ta[i - 1], "b_token": tb[j - 1], "op": "match",
                })
                matched_tokens.append(ta[i - 1])
                i -= 1
                j -= 1
            elif matrix[i - 1][j] >= matrix[i][j - 1]:
                alignment.append({"a_token": ta[i - 1], "b_token": None,
                                  "op": "delete"})
                unmatched_a.append(ta[i - 1])
                i -= 1
            else:
                alignment.append({"a_token": None, "b_token": tb[j - 1],
                                  "op": "insert"})
                unmatched_b.append(tb[j - 1])
                j -= 1
        while i > 0:
            alignment.append({"a_token": ta[i - 1], "b_token": None,
                              "op": "delete"})
            unmatched_a.append(ta[i - 1])
            i -= 1
        while j > 0:
            alignment.append({"a_token": None, "b_token": tb[j - 1],
                              "op": "insert"})
            unmatched_b.append(tb[j - 1])
            j -= 1
        alignment.reverse()
        # Backtrack produced tokens tail-first; restore natural order.
        matched_tokens.reverse()
        unmatched_a.reverse()
        unmatched_b.reverse()
    else:
        # Large inputs: no backtrack, so decomposition is deferred.
        unmatched_a = list(ta)
        unmatched_b = list(tb)

    elapsed_ns = time.perf_counter_ns() - start_ns
    return LCSResult(
        length=length,
        similarity=_similarity(length, n, m),
        matrix=matrix,
        dp_cell_updates=dp_cell_updates,
        alignment=alignment,
        matched_tokens=matched_tokens,
        unmatched_a=unmatched_a,
        unmatched_b=unmatched_b,
        elapsed_ns=elapsed_ns,
    )


def lcs_length_optimized(
    a: Union[str, Sequence[str]], b: Union[str, Sequence[str]]
) -> tuple[int, int]:
    """Return ``(lcs_length, dp_cell_updates)`` using O(min(n,m)) space."""
    ta = _resolve(a)
    tb = _resolve(b)
    # Make ``tb`` the shorter so the DP columns (arrays) are minimal width.
    if len(tb) > len(ta):
        ta, tb = tb, ta
    n, m = len(ta), len(tb)

    prev = [0] * (m + 1)
    curr = [0] * (m + 1)
    updates = 0
    for i in range(1, n + 1):
        ai = ta[i - 1]
        for j in range(1, m + 1):
            updates += 1
            if ai == tb[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = prev[j] if prev[j] >= curr[j - 1] else curr[j - 1]
        prev, curr = curr, prev
    return prev[m], updates


def lcs_similarity(a: Union[str, Sequence[str]], b: Union[str, Sequence[str]]) -> float:
    """Return the normalised LCS similarity ``2*L / (len(a)+len(b))``.

    ``1.0`` when both inputs are empty; ``0.0`` when they share nothing.
    """
    ta = _resolve(a)
    tb = _resolve(b)
    if not ta and not tb:
        return 1.0
    length, _ = lcs_length_optimized(ta, tb)
    return _similarity(length, len(ta), len(tb))
