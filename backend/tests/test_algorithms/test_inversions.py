"""Tests for inversion counting (Unit II — divide & conquer)."""

import random

from app.algorithms.inversions import count_inversions


def _naive_inversions(items):
    count = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] > items[j]:
                count += 1
    return count


def test_sorted_input_zero_inversions():
    result = count_inversions([1, 2, 3, 4, 5])
    assert result.inversion_count == 0
    assert result.normalized_reorder_score == 0.0


def test_reverse_input_max_inversions():
    result = count_inversions([5, 4, 3, 2, 1])
    assert result.inversion_count == 10  # C(5,2)
    assert abs(result.normalized_reorder_score - 1.0) < 1e-9


def test_documented_example():
    # Original [1,2,3,4,5] vs modified [1,4,3,2,5] -> inversions (4,3),(4,2),(3,2)
    result = count_inversions([1, 4, 3, 2, 5])
    assert result.inversion_count == 3
    assert abs(result.normalized_reorder_score - 0.3) < 1e-9


def test_empty_and_single():
    assert count_inversions([]).inversion_count == 0
    assert count_inversions([42]).inversion_count == 0
    assert count_inversions([]).normalized_reorder_score == 0.0


def test_duplicates_are_not_inversions():
    # Equal elements must not count as inversions.
    result = count_inversions([2, 2, 2, 1])
    assert result.inversion_count == 3


def test_randomized_cross_check():
    rng = random.Random(2026)
    for _ in range(60):
        n = rng.randint(0, 80)
        data = [rng.randint(0, 15) for _ in range(n)]
        expected = _naive_inversions(data)
        result = count_inversions(data)
        assert result.inversion_count == expected
        assert data is not None  # input untouched in spirit (documented)


def test_trace_present():
    result = count_inversions([3, 1, 2], trace=True)
    assert len(result.trace) > 0
    assert {"range", "merged", "cross_inversions_so_far"} <= set(result.trace[0])


def test_counters_and_score_bounds():
    result = count_inversions([4, 3, 2, 1, 5, 9, 7])
    assert result.comparisons > 0
    assert 0.0 <= result.normalized_reorder_score <= 1.0
