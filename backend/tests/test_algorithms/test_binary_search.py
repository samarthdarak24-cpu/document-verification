"""Tests for :mod:`app.algorithms.binary_search`."""

import json

from app.algorithms.binary_search import BinarySearchResult, binary_search


def items_1_to_9():
    return list(range(1, 10))  # [1,2,3,4,5,6,7,8,9]


# --------------------------------------------------------------------------- #
# found
# --------------------------------------------------------------------------- #
def test_found_first():
    assert binary_search(items_1_to_9(), 1).index == 0


def test_found_middle():
    assert binary_search(items_1_to_9(), 5).index == 4


def test_found_last():
    assert binary_search(items_1_to_9(), 9).index == 8


def test_found_arbitrary():
    for target in range(1, 10):
        r = binary_search(items_1_to_9(), target)
        assert items_1_to_9()[r.index] == target


# --------------------------------------------------------------------------- #
# not found
# --------------------------------------------------------------------------- #
def test_not_found_below_range():
    assert binary_search(items_1_to_9(), 0).index == -1


def test_not_found_above_range():
    assert binary_search(items_1_to_9(), 10).index == -1


def test_not_found_in_gap():
    data = [1, 3, 5, 7, 9]
    assert binary_search(data, 4).index == -1
    assert binary_search(data, 6).index == -1


# --------------------------------------------------------------------------- #
# edge cases
# --------------------------------------------------------------------------- #
def test_empty_list():
    r = binary_search([], 5)
    assert r.index == -1
    assert r.comparisons == 0


def test_single_element():
    assert binary_search([7], 7).index == 0
    assert binary_search([7], 3).index == -1


def test_duplicates_any_valid_index():
    data = [1, 2, 2, 2, 3]
    r = binary_search(data, 2)
    assert r.index != -1
    assert data[r.index] == 2  # any correct index acceptable


# --------------------------------------------------------------------------- #
# comparisons bound
# --------------------------------------------------------------------------- #
def test_comparisons_log_bound():
    import math
    data = list(range(1, 1001))
    upper = math.ceil(math.log2(len(data))) + 1
    for target in (1, 500, 999, 1000, 501):
        r = binary_search(data, target)
        assert r.comparisons <= upper, (target, r.comparisons)


def test_comparisons_positive_when_searching():
    assert binary_search(items_1_to_9(), 5).comparisons > 0


# --------------------------------------------------------------------------- #
# key
# --------------------------------------------------------------------------- #
def test_key_parameter():
    data = [{"k": 1}, {"k": 2}, {"k": 3}, {"k": 4}]
    r = binary_search(data, 3, key=lambda d: d["k"])
    assert r.index != -1
    assert data[r.index]["k"] == 3
    assert binary_search(data, 99, key=lambda d: d["k"]).index == -1


# --------------------------------------------------------------------------- #
# trace
# --------------------------------------------------------------------------- #
def test_trace_empty_by_default():
    assert binary_search(items_1_to_9(), 5).steps == []


def test_trace_found():
    r = binary_search(items_1_to_9(), 5, trace=True)
    assert len(r.steps) > 0
    assert r.steps[-1]["action"] == "found"
    assert r.steps[-1]["comparison"] == "="
    for s in r.steps:
        assert set(s.keys()) == {
            "low", "high", "mid", "mid_value", "comparison", "action"
        }
        assert s["comparison"] in {"<", ">", "="}
        assert s["action"] in {"search_left", "search_right", "found", "not_found"}


def test_trace_not_found():
    r = binary_search(items_1_to_9(), 10, trace=True)
    assert len(r.steps) > 0
    assert r.steps[-1]["action"] == "not_found"
    for s in r.steps:
        assert s["action"] in {"search_left", "search_right", "found", "not_found"}


# --------------------------------------------------------------------------- #
# serialization / types
# --------------------------------------------------------------------------- #
def test_to_dict_json_serializable():
    r = binary_search(items_1_to_9(), 5, trace=True)
    json.dumps(r.to_dict())


def test_result_type():
    assert isinstance(binary_search(items_1_to_9(), 5), BinarySearchResult)
