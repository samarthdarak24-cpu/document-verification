"""Quick sort (last-element pivot, Lomuto partition, iterative).

Purpose
-------
Return a *new* list containing the items in non-decreasing order according to an
optional ``key``. The pivot is always the **last** element of the current range
and the partitioning uses the in-place **Lomuto** scheme. The input list is copied
first, so the caller's list is never mutated.

Note: quick sort is **not** stable. When a stable ordering is required, use
:func:`app.algorithms.merge_sort.merge_sort`.

DocuTrace use case
------------------
Fast in-memory ranking of large result sets (e.g. ordering thousands of detected
look-alike documents by similarity score) where the extra O(n) buffer of merge
sort is undesirable and ties do not carry meaning.

Complexity
----------
* Time:
  - Best case O(n log n): the pivot splits ranges near the middle.
  - Average case O(n log n) over random inputs.
  - Worst case O(n^2): already-sorted / reverse-sorted inputs (the last element
    is always the extreme) or many duplicates.
* Space: O(log n) expected recursion depth; implemented with an explicit stack
  (bounded by the number of pending sub-ranges, O(n) worst case) so no
  ``RecursionError`` on large inputs.
* Comparisons: one per element scanned against the pivot.
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
    """Result of a :func:`quick_sort` call."""

    def __init__(
        self,
        sorted_items: list,
        comparisons: int,
        swaps: int,
        partitions: int,
        pivot_strategy: str,
        trace: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.sorted_items: list = sorted_items
        self.comparisons: int = comparisons
        self.swaps: int = swaps
        self.partitions: int = partitions
        self.pivot_strategy: str = pivot_strategy  # "last"
        self.trace: list[dict] = trace
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "sorted_items": list(self.sorted_items),
            "comparisons": self.comparisons,
            "swaps": self.swaps,
            "partitions": self.partitions,
            "pivot_strategy": self.pivot_strategy,
            "trace": [dict(step) for step in self.trace],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"SortResult(n={len(self.sorted_items)}, "
            f"comparisons={self.comparisons}, swaps={self.swaps})"
        )


def quick_sort(
    items: list, key: Optional[Callable] = None, trace: bool = False
) -> SortResult:
    """Return a newly-allocated sorted copy of ``items`` (last-element pivot).

    The caller's list is never mutated. Iterative (explicit stack) to avoid deep
    recursion on degenerate inputs.
    """
    start_ns = time.perf_counter_ns()
    arr = list(items)  # copy; never sort the caller's list in place
    key_fn = (lambda x: x) if key is None else key

    comparisons = 0
    swaps = 0
    partitions = 0
    trace_steps: list[dict] = []

    def _partition(low: int, high: int) -> int:
        nonlocal comparisons, swaps
        pivot_item = arr[high]              # last-element pivot (Lomuto)
        pivot_key = key_fn(pivot_item)
        if trace and len(trace_steps) < _MAX_TRACE:
            trace_steps.append({
                "action": "partition", "pivot": pivot_item,
                "array": _trunc(arr), "low": low, "high": high,
            })
        i = low - 1
        for j in range(low, high):
            comparisons += 1
            if key_fn(arr[j]) <= pivot_key:
                i += 1
                if i != j:
                    arr[i], arr[j] = arr[j], arr[i]
                    swaps += 1
        # Place the pivot in its final sorted position.
        if i + 1 != high:
            arr[i + 1], arr[high] = arr[high], arr[i + 1]
            swaps += 1
            if trace and len(trace_steps) < _MAX_TRACE:
                trace_steps.append({
                    "action": "pivot_swap", "pivot": pivot_item,
                    "array": _trunc(arr), "low": low, "high": high,
                })
        return i + 1

    if len(arr) > 1:
        stack = [(0, len(arr) - 1)]
        while stack:
            low, high = stack.pop()
            if low >= high:
                continue
            p = _partition(low, high)
            partitions += 1
            # Push the larger side first to keep the explicit stack shallow.
            if (p - low) > (high - p):
                stack.append((low, p - 1))
                stack.append((p + 1, high))
            else:
                stack.append((p + 1, high))
                stack.append((low, p - 1))

    return SortResult(
        sorted_items=arr,
        comparisons=comparisons,
        swaps=swaps,
        partitions=partitions,
        pivot_strategy="last",
        trace=trace_steps if trace else [],
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )
