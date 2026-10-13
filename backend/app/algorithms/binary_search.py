"""Binary search over a sorted list (iterative).

Purpose
-------
Locate a target in an already-sorted sequence in O(log n) time by repeatedly
halving the search interval. This is the fastest membership/lookup primitive in
the standard library's own toolkit (``bisect``) and is used throughout DocuTrace
to probe sorted result sets.

Precondition
------------
The input MUST be sorted with respect to ``key`` *before* calling this function
(use :func:`app.algorithms.merge_sort.merge_sort` or the built-in ``sorted``
first). Binary search returns a meaningless index on unsorted data; there is
deliberately no O(n) sortedness pre-check here because that would defeat the
O(log n) guarantee — the caller is responsible for the precondition.

DocuTrace use case
------------------
Determining whether an exact SHA-256 fingerprint already exists in a sorted
list of previously-seen document hashes (membership check), or probing a sorted
table of reference numbers during verification.

Complexity
----------
* Time: O(log n) comparisons in the best, average, and worst cases (each probe
  halves the interval). ``O(1)`` if the target is at the first midpoint.
* Space: O(1) auxiliary (iterative; O(log n) only for a trace of that length).
* Comparisons: exactly one per midpoint probe.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

_MAX_TRACE = 500


class BinarySearchResult:
    """Result of a :func:`binary_search` call."""

    def __init__(
        self,
        index: int,
        comparisons: int,
        steps: list[dict],
        elapsed_ns: int,
    ) -> None:
        self.index: int = index        # position of a match, or -1
        self.comparisons: int = comparisons
        self.steps: list[dict] = steps  # [] unless trace=True
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "index": self.index,
            "comparisons": self.comparisons,
            "steps": [dict(step) for step in self.steps],
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"BinarySearchResult(index={self.index}, "
            f"comparisons={self.comparisons})"
        )


def binary_search(
    items: list, target, key: Optional[Callable] = None, trace: bool = False
) -> BinarySearchResult:
    """Return a :class:`BinarySearchResult` for ``target`` in sorted ``items``.

    ``items`` must already be sorted by ``key`` (see module docstring). If
    ``key`` is given it is applied to each element and the result is compared
    against ``target``; otherwise elements are compared directly.
    """
    start_ns = time.perf_counter_ns()
    key_fn = (lambda x: x) if key is None else key

    low = 0
    high = len(items) - 1
    comparisons = 0
    steps: list[dict] = []
    index = -1

    while low <= high:
        mid = (low + high) // 2
        mid_value = items[mid]
        mid_key = key_fn(mid_value)
        comparisons += 1

        if mid_key == target:
            index = mid
            if trace and len(steps) < _MAX_TRACE:
                steps.append({
                    "low": low, "high": high, "mid": mid,
                    "mid_value": mid_value, "comparison": "=",
                    "action": "found",
                })
            break
        elif mid_key < target:
            new_low = mid + 1
            empty = new_low > high
            if trace and len(steps) < _MAX_TRACE:
                steps.append({
                    "low": low, "high": high, "mid": mid,
                    "mid_value": mid_value, "comparison": "<",
                    "action": "not_found" if empty else "search_right",
                })
            low = new_low
        else:  # mid_key > target
            new_high = mid - 1
            empty = low > new_high
            if trace and len(steps) < _MAX_TRACE:
                steps.append({
                    "low": low, "high": high, "mid": mid,
                    "mid_value": mid_value, "comparison": ">",
                    "action": "not_found" if empty else "search_left",
                })
            high = new_high

    elapsed_ns = time.perf_counter_ns() - start_ns
    return BinarySearchResult(
        index=index,
        comparisons=comparisons,
        steps=steps if trace else [],
        elapsed_ns=elapsed_ns,
    )
