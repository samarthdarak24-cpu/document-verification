"""Tests for :mod:`app.algorithms.merge_sort` and :mod:`quick_sort`."""

import json
import random

from app.algorithms.merge_sort import SortResult as MergeResult
from app.algorithms.merge_sort import merge_sort
from app.algorithms.quick_sort import SortResult as QuickResult
from app.algorithms.quick_sort import quick_sort


def both_sorts(items, key=None):
    return merge_sort(items, key=key), quick_sort(items, key=key)


# --------------------------------------------------------------------------- #
# Basic correctness vs sorted()
# --------------------------------------------------------------------------- #
def test_merge_simple():
    assert merge_sort([3, 1, 2]).sorted_items == [1, 2, 3]


def test_quick_simple():
    assert quick_sort([3, 1, 2]).sorted_items == [1, 2, 3]


def test_empty():
    assert merge_sort([]).sorted_items == []
    assert quick_sort([]).sorted_items == []
    assert quick_sort([]).partitions == 0


def test_single_element():
    assert merge_sort([42]).sorted_items == [42]
    assert quick_sort([42]).sorted_items == [42]


def test_duplicates():
    data = [5, 2, 5, 1, 2, 5, 1]
    assert merge_sort(data).sorted_items == sorted(data)
    assert quick_sort(data).sorted_items == sorted(data)


# --------------------------------------------------------------------------- #
# Non-mutation
# --------------------------------------------------------------------------- #
def test_merge_does_not_mutate_input():
    data = [3, 1, 2]
    result = merge_sort(data)
    assert data == [3, 1, 2]           # original untouched
    assert result.sorted_items is not data


def test_quick_does_not_mutate_input():
    data = [3, 1, 2]
    result = quick_sort(data)
    assert data == [3, 1, 2]
    assert result.sorted_items is not data


# --------------------------------------------------------------------------- #
# Key handling
# --------------------------------------------------------------------------- #
def test_key_parameter():
    words = ["banana", "apple", "cherry"]
    assert merge_sort(words, key=len).sorted_items == sorted(words, key=len)
    assert quick_sort(words, key=len).sorted_items == sorted(words, key=len)


# --------------------------------------------------------------------------- #
# Stability (merge sort only)
# --------------------------------------------------------------------------- #
def test_merge_stable():
    records = [
        {"k": 2, "i": 0}, {"k": 1, "i": 1}, {"k": 2, "i": 2},
        {"k": 1, "i": 3}, {"k": 2, "i": 4},
    ]
    result = merge_sort(records, key=lambda d: d["k"])
    order = [(d["k"], d["i"]) for d in result.sorted_items]
    # Ties (equal k) keep original i order.
    assert order == [(1, 1), (1, 3), (2, 0), (2, 2), (2, 4)]


# --------------------------------------------------------------------------- #
# Comparisons counted
# --------------------------------------------------------------------------- #
def test_comparisons_counted():
    assert merge_sort([5, 4, 3, 2, 1]).comparisons > 0
    assert quick_sort([5, 4, 3, 2, 1]).comparisons > 0
    assert quick_sort([1, 2, 3]).partitions > 0
    assert merge_sort([4, 3, 2, 1]).merges > 0


def test_pivot_strategy():
    assert quick_sort([3, 1, 2]).pivot_strategy == "last"


# --------------------------------------------------------------------------- #
# Pre-sorted / reverse-sorted
# --------------------------------------------------------------------------- #
def test_already_sorted():
    data = list(range(1000))
    for tag, out in (("merge", merge_sort(data)),
                    ("quick", quick_sort(data))):
        assert out.sorted_items == data, tag


def test_reverse_sorted():
    data = list(range(1000, 0, -1))
    assert merge_sort(data).sorted_items == sorted(data)
    assert quick_sort(data).sorted_items == sorted(data)


# --------------------------------------------------------------------------- #
# Large random sanity + randomized cross-check
# --------------------------------------------------------------------------- #
def test_large_random_10k():
    rng = random.Random(42)
    data = [rng.randint(-1000, 1000) for _ in range(10_000)]
    assert merge_sort(data).sorted_items == sorted(data)
    assert quick_sort(data).sorted_items == sorted(data)


def test_randomized_cross_check_vs_sorted():
    rng = random.Random(123)
    for _ in range(60):
        n = rng.randint(0, 200)
        data = [rng.randint(0, 20) for _ in range(n)]
        kf = lambda x: x
        assert merge_sort(data).sorted_items == sorted(data, key=kf)
        assert quick_sort(data).sorted_items == sorted(data, key=kf)


def test_randomized_key_cross_check():
    rng = random.Random(7)
    for _ in range(40):
        n = rng.randint(0, 120)
        data = [{"s": rng.randint(0, 10), "t": i} for i in range(n)]
        kf = lambda d: d["s"]
        expected = sorted(data, key=kf)
        # merge_sort is stable: identical order including tie-breaks.
        assert merge_sort(data, key=kf).sorted_items == expected
        # quick_sort is NOT stable: compare key sequences and multiset only.
        qs = quick_sort(data, key=kf).sorted_items
        assert [d["s"] for d in qs] == [d["s"] for d in expected]
        assert sorted(d["t"] for d in qs) == sorted(d["t"] for d in data)


# --------------------------------------------------------------------------- #
# Traces
# --------------------------------------------------------------------------- #
def test_merge_trace():
    result = merge_sort([5, 2, 8, 1], trace=True)
    assert len(result.trace) > 0
    actions = set()
    for step in result.trace:
        assert set(step.keys()) == {"action", "left", "right", "result"}
        actions.add(step["action"])
        # lists truncated to at most 10 items
        assert len(step["left"]) <= 10
        assert len(step["right"]) <= 10
        assert len(step["result"]) <= 10
    assert {"split", "merge"} <= actions


def test_quick_trace():
    result = quick_sort([5, 2, 8, 1, 9, 3], trace=True)
    assert len(result.trace) > 0
    for step in result.trace:
        assert set(step.keys()) == {"action", "pivot", "array", "low", "high"}
        assert step["action"] in {"partition", "pivot_swap"}
        assert len(step["array"]) <= 10
    assert any(s["action"] == "partition" for s in result.trace)


def test_trace_capped():
    big = list(range(600))
    assert len(merge_sort(big, trace=True).trace) <= 500
    assert len(quick_sort(big, trace=False).sorted_items) == 600


def test_trace_empty_by_default():
    assert merge_sort([3, 1, 2]).trace == []
    assert quick_sort([3, 1, 2]).trace == []


# --------------------------------------------------------------------------- #
# Serialization / types
# --------------------------------------------------------------------------- #
def test_merge_to_dict_json():
    json.dumps(merge_sort([3, 1, 2], trace=True).to_dict())


def test_quick_to_dict_json():
    json.dumps(quick_sort([3, 1, 2], trace=True).to_dict())


def test_result_types():
    assert isinstance(merge_sort([2, 1]), MergeResult)
    assert isinstance(quick_sort([2, 1]), QuickResult)
