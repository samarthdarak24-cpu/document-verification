"""Stable merge sort (top-down, out-of-place).

Purpose
-------
Return a *new* list containing the items in non-decreasing order according to an
optional ``key``. Merge sort is **stable**: equal elements keep their original
relative order, which matters when ranking results by a score and wanting a
deterministic tie-break.

DocuTrace use case
------------------
Ordering a document-verification report's field-by-field matches, or ranking
look-alike documents by similarity score, where ties must preserve the input
(e.g. filename) order for reproducible output.

Complexity
----------
* Time: O(n log n) in the best, average, and worst cases (the list is always
  split in half and each level merges O(n) elements).
* Space: O(n) auxiliary (new sublists are created at each split/merge); the
  input list is never mutated.
* Comparisons: one per element emitted during merging.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

_MAX_TRACE = 500
_TRUNC = 10


def _trunc(seq: list) -> list:
    """Return a shallow copy of ``seq`` truncated to the first ``_TRUNC`` items."""
    return list(seq[:_TRUNC])


class SortResult:
    """Result of a :func:`merge_sort` call."""

    def __init__(
        self,
        sorted_items: list,
        comparisons: int,
        merges: int,
        trace: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.sorted_items: list = sorted_items
        self.comparisons: int = comparisons
        self.merges: int = merges
        self.trace: list[dict] = trace
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "sorted_items": list(self.sorted_items),
            "comparisons": self.comparisons,
            "merges": self.merges,
            "trace": [dict(step) for step in self.trace],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"SortResult(n={len(self.sorted_items)}, "
            f"comparisons={self.comparisons}, merges={self.merges})"
        )


def merge_sort(
    items: list, key: Optional[Callable] = None, trace: bool = False
) -> SortResult:
    """Return a stable, newly-allocated sorted copy of ``items``.

    The input list is never mutated. ``key`` behaves like the built-in
    ``sorted``. Ties preserve original order (stability).
    """
    start_ns = time.perf_counter_ns()
    key_fn = (lambda x: x) if key is None else key

    comparisons = 0
    merges = 0
    trace_steps: list[dict] = []

    def _merge(left: list, right: list) -> list:
        nonlocal comparisons
        i = j = 0
        out: list = []
        while i < len(left) and j < len(right):
            comparisons += 1
            # '<=' keeps the left (earlier) element first on ties -> stable.
            if key_fn(left[i]) <= key_fn(right[j]):
                out.append(left[i])
                i += 1
            else:
                out.append(right[j])
                j += 1
        out.extend(left[i:])
        out.extend(right[j:])
        return out

    def _sort(a: list) -> list:
        nonlocal merges
        n = len(a)
        if n <= 1:
            return list(a)
        mid = n // 2
        left_part = a[:mid]
        right_part = a[mid:]
        if trace and len(trace_steps) < _MAX_TRACE:
            trace_steps.append({
                "action": "split",
                "left": _trunc(left_part),
                "right": _trunc(right_part),
                "result": [],
            })
        left = _sort(left_part)
        right = _sort(right_part)
        merged = _merge(left, right)
        merges += 1
        if trace and len(trace_steps) < _MAX_TRACE:
            trace_steps.append({
                "action": "merge",
                "left": _trunc(left),
                "right": _trunc(right),
                "result": _trunc(merged),
            })
        return merged

    result = _sort(list(items))  # copy; never mutate the caller's list
    return SortResult(
        sorted_items=result,
        comparisons=comparisons,
        merges=merges,
        trace=trace_steps if trace else [],
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )
