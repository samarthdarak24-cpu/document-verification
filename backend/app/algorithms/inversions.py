"""Inversion counting via a modified merge sort (divide & conquer).

Purpose
-------
Measure how much the order of *reliably matched* document sections has changed
between two versions of a document. Given the matched-section ranks of the
original order and the ranks observed in the modified document, the number of
inversions (pairs ``i < j`` with ``a[i] > a[j]``) quantifies the reordering.

Example
-------
Original section ranks:  ``[1, 2, 3, 4, 5]``
Modified section ranks:  ``[1, 4, 3, 2, 5]``
Inversions: (4,3), (4,2), (3,2) -> ``3`` out of C(5,2)=10 pairs.

DocuTrace use case
------------------
The comparison engine passes the matched-section rank sequence; a high
normalized reorder score is reported as a structural difference (never as
fraud — reordering alone is not evidence of tampering).

Complexity
----------
* Time O(n log n): identical recursion to merge sort; each level of recursion
  performs O(n) work counting cross-half inversions while merging.
* Space O(n) for the merge buffer.

Why divide & conquer beats the naive approach
----------------------------------------------
The naive method compares every pair in O(n^2). During the merge step both
halves are already sorted, so when an element of the right half is taken
before remaining elements of the left half, *all* of those remaining left
elements form inversions with it in O(1) amortised work — collapsing the
quadratic pairwise scan into the merge's linear work.
"""

from __future__ import annotations

import time

_MAX_TRACE = 500


class InversionResult:
    """Result of a :func:`count_inversions` call."""

    def __init__(
        self,
        inversion_count: int,
        n: int,
        comparisons: int,
        trace: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.inversion_count: int = inversion_count
        self.n: int = n
        self.comparisons: int = comparisons
        self.normalized_reorder_score: float = (
            inversion_count / (n * (n - 1) / 2) if n > 1 else 0.0
        )
        self.trace: list[dict] = trace
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        return {
            "inversion_count": self.inversion_count,
            "n": self.n,
            "comparisons": self.comparisons,
            "normalized_reorder_score": round(self.normalized_reorder_score, 6),
            "trace": [dict(s) for s in self.trace],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"InversionResult(count={self.inversion_count}, n={self.n})"


def count_inversions(items: list, trace: bool = False) -> InversionResult:
    """Count inversions in ``items`` (comparable scalars) via merge sort.

    Returns an :class:`InversionResult`. The input list is never mutated.
    """
    start_ns = time.perf_counter_ns()
    arr = list(items)
    comparisons = 0
    trace_steps: list[dict] = []

    def _sort(lo: int, hi: int) -> int:
        """Sort arr[lo:hi] and return its inversion count."""
        nonlocal comparisons
        if hi - lo <= 1:
            return 0
        mid = (lo + hi) // 2
        count = _sort(lo, mid) + _sort(mid, hi)
        merged: list = []
        i, j = lo, mid
        while i < mid and j < hi:
            comparisons += 1
            if arr[i] <= arr[j]:
                merged.append(arr[i])
                i += 1
            else:
                # arr[i..mid) all exceed arr[j]: each forms an inversion.
                count += mid - i
                merged.append(arr[j])
                j += 1
        merged.extend(arr[i:mid])
        merged.extend(arr[j:hi])
        arr[lo:hi] = merged
        if trace and len(trace_steps) < _MAX_TRACE:
            trace_steps.append({
                "range": [lo, hi],
                "merged": merged[:20],
                "cross_inversions_so_far": count,
            })
        return count

    inversion_count = _sort(0, len(arr))

    return InversionResult(
        inversion_count=inversion_count,
        n=len(items),
        comparisons=comparisons,
        trace=trace_steps if trace else [],
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )
