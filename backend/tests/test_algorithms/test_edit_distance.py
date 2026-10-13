"""Tests for :mod:`app.algorithms.edit_distance` (Levenshtein distance)."""

import json
import random

from app.algorithms.edit_distance import (
    EditDistanceResult,
    edit_distance,
    edit_distance_optimized,
    edit_distance_sequences,
)


def apply_edit_ops(a, ops):
    """Apply the reconstructed edit script to ``a``; return the rebuilt sequence.

    ``position`` is an index into the *source* ``a``: delete/substitute act at
    that index, insert writes at that gap. Ops are applied in forward order.
    """
    src = list(a)
    out = []
    ai = 0
    for op in ops:
        pos = op["position"]
        while ai < pos:
            out.append(src[ai])
            ai += 1
        kind = op["op"]
        if kind == "delete":
            ai += 1
        elif kind == "substitute":
            out.append(op["new"])
            ai += 1
        elif kind == "insert":
            out.append(op["new"])
    while ai < len(src):
        out.append(src[ai])
        ai += 1
    return out


# --------------------------------------------------------------------------- #
# known values
# --------------------------------------------------------------------------- #
def test_kitten_sitting():
    assert edit_distance("kitten", "sitting").distance == 3


def test_empty_to_abc():
    assert edit_distance("", "abc").distance == 3


def test_flaw_lawn():
    assert edit_distance("flaw", "lawn").distance == 2


def test_identical():
    assert edit_distance("abcabc", "abcabc").distance == 0


def test_both_empty():
    res = edit_distance("", "")
    assert res.distance == 0
    assert res.similarity == 1.0


# --------------------------------------------------------------------------- #
# symmetry
# --------------------------------------------------------------------------- #
def test_symmetry():
    pairs = [("kitten", "sitting"), ("flaw", "lawn"), ("", "abc"),
             ("abc", ""), ("intention", "execution"), ("aaaa", "aa")]
    for a, b in pairs:
        assert edit_distance(a, b).distance == edit_distance(b, a).distance


def test_symmetry_random():
    rng = random.Random(11)
    for _ in range(60):
        a = [rng.choice("abc") for _ in range(rng.randint(0, 15))]
        b = [rng.choice("abc") for _ in range(rng.randint(0, 15))]
        assert edit_distance(a, b).distance == edit_distance(b, a).distance


# --------------------------------------------------------------------------- #
# operation reconstruction
# --------------------------------------------------------------------------- #
def test_ops_reconstruct_chars():
    a, b = "kitten", "sitting"
    res = edit_distance(a, b, with_operations=True)
    assert apply_edit_ops(a, res.operations) == list(b)
    assert res.matrix is not None
    # number of non-match ops is bounded by the distance
    assert len(res.operations) <= res.distance + abs(len(a) - len(b))


def test_ops_reconstruct_tokens():
    a = ["a", "b", "c"]
    b = ["a", "x", "c", "d"]
    res = edit_distance(a, b, with_operations=True)
    assert apply_edit_ops(a, res.operations) == b


def test_ops_fields():
    res = edit_distance("flaw", "lawn", with_operations=True)
    for op in res.operations:
        assert set(op.keys()) == {"op", "position", "old", "new"}
        assert op["op"] in {"insert", "delete", "substitute"}


def test_ops_empty_by_default():
    res = edit_distance("kitten", "sitting")
    assert res.operations == []
    assert res.matrix is None


# --------------------------------------------------------------------------- #
# optimized / sequences
# --------------------------------------------------------------------------- #
def test_optimized_equals_full_random():
    rng = random.Random(3)
    for _ in range(80):
        a = [rng.choice("abc") for _ in range(rng.randint(0, 18))]
        b = [rng.choice("abc") for _ in range(rng.randint(0, 18))]
        d_full = edit_distance(a, b).distance
        d_opt, updates = edit_distance_optimized(a, b)
        assert d_full == d_opt
        assert updates > 0 or (not a or not b)
        # with-operations path agrees
        res = edit_distance(a, b, with_operations=True)
        assert res.distance == d_full
        assert apply_edit_ops(a, res.operations) == list(b)


def test_sequences_token_level():
    a = ["kitten", "purrs"]
    b = ["sitting", "purrs"]
    assert edit_distance_sequences(a, b) == edit_distance(a, b).distance == 1


# --------------------------------------------------------------------------- #
# similarity
# --------------------------------------------------------------------------- #
def test_similarity_bounds():
    assert edit_distance("", "").similarity == 1.0
    assert edit_distance("abc", "").similarity == 0.0
    rng = random.Random(5)
    for _ in range(50):
        a = [rng.choice("abcd") for _ in range(rng.randint(0, 20))]
        b = [rng.choice("abcd") for _ in range(rng.randint(0, 20))]
        s = edit_distance(a, b).similarity
        assert 0.0 <= s <= 1.0


def test_dp_cell_updates_positive():
    assert edit_distance("abc", "abd").dp_cell_updates > 0


def test_to_dict_json_serializable():
    res = edit_distance("kitten", "sitting", with_operations=True)
    json.dumps(res.to_dict())  # must not raise


def test_result_type():
    assert isinstance(edit_distance("a", "b"), EditDistanceResult)
