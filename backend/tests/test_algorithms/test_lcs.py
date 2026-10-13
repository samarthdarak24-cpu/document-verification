"""Tests for :mod:`app.algorithms.lcs` (word-level Longest Common Subsequence)."""

import json
import random

from app.algorithms.lcs import (
    LCSResult,
    lcs_dp,
    lcs_length_optimized,
    lcs_similarity,
    tokenize,
)


def ref_lcs_length(a, b):
    """Independent reference DP for the LCS length."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[n][m]


# --------------------------------------------------------------------------- #
# tokenize
# --------------------------------------------------------------------------- #
def test_tokenize_basic():
    assert tokenize("A B C B D A B") == ["a", "b", "c", "b", "d", "a", "b"]


def test_tokenize_punctuation():
    assert tokenize("Hello, World! 123") == ["hello", "world", "123"]


def test_tokenize_unicode():
    assert tokenize("Café RÉSUMÉ !!!") == ["café", "résumé"]


# --------------------------------------------------------------------------- #
# known vectors
# --------------------------------------------------------------------------- #
def test_known_vector_classic():
    a = tokenize("A B C B D A B")
    b = tokenize("B D C A B A")
    result = lcs_dp(a, b)
    assert result.length == 4
    assert result.length == ref_lcs_length(a, b)


def test_known_vector_pre_tokenized():
    result = lcs_dp(["x", "y", "z", "w"], ["x", "y", "w"])
    assert result.length == 3
    assert result.length == ref_lcs_length(["x", "y", "z", "w"], ["x", "y", "w"])


def test_string_input_is_tokenized():
    result = lcs_dp("the cat sat", "the cat")
    assert result.matched_tokens == ["the", "cat"]


# --------------------------------------------------------------------------- #
# edge cases
# --------------------------------------------------------------------------- #
def test_both_empty():
    result = lcs_dp("", "")
    assert result.length == 0
    assert result.similarity == 1.0
    assert result.dp_cell_updates == 0
    assert result.alignment == []


def test_one_empty():
    result = lcs_dp("abc", "")
    assert result.length == 0
    assert result.similarity == 0.0


def test_identical():
    result = lcs_dp("the cat sat on mat", "the cat sat on mat")
    assert result.length == len(tokenize("the cat sat on mat"))
    assert result.similarity == 1.0


def test_completely_different():
    result = lcs_dp(["x", "y", "z"], ["a", "b", "c"])
    assert result.length == 0
    assert result.similarity == 0.0


# --------------------------------------------------------------------------- #
# alignment + partition
# --------------------------------------------------------------------------- #
def test_alignment_reconstructs_both():
    a = tokenize("the quick brown fox")
    b = tokenize("the slow brown dog")
    result = lcs_dp(a, b)
    recon_a = [s["a_token"] for s in result.alignment if s["a_token"] is not None]
    recon_b = [s["b_token"] for s in result.alignment if s["b_token"] is not None]
    assert recon_a == a
    assert recon_b == b


def test_alignment_ops_valid():
    a = tokenize("one two three")
    b = tokenize("one 2 three")
    for s in lcs_dp(a, b).alignment:
        assert s["op"] in {"match", "insert", "delete"}


def test_partition_consistent():
    a = tokenize("one two three four two")
    b = tokenize("zero two three five two")
    result = lcs_dp(a, b)
    assert sorted(result.matched_tokens + result.unmatched_a) == sorted(a)
    assert sorted(result.matched_tokens + result.unmatched_b) == sorted(b)
    assert len(result.matched_tokens) == result.length


# --------------------------------------------------------------------------- #
# counters / optimized / matrix guard
# --------------------------------------------------------------------------- #
def test_dp_cell_updates_positive():
    result = lcs_dp(tokenize("a b c d"), tokenize("a b c d"))
    assert result.dp_cell_updates > 0


def test_optimized_equals_full_random():
    rng = random.Random(7)
    for _ in range(60):
        a = [rng.choice("abc") for _ in range(rng.randint(0, 18))]
        b = [rng.choice("abc") for _ in range(rng.randint(0, 18))]
        full = lcs_dp(a, b).length
        opt_length, opt_updates = lcs_length_optimized(a, b)
        assert full == opt_length
        assert full == ref_lcs_length(a, b)
        assert opt_updates > 0 or (not a or not b)


def test_matrix_none_for_large_common():
    a = ["a"] * 600
    b = ["a"] * 600  # 360_000 cells > 250_000 guard
    result = lcs_dp(a, b)
    assert result.matrix is None
    assert result.length == 600
    opt_length, _ = lcs_length_optimized(a, b)
    assert result.length == opt_length


def test_matrix_none_for_large_disjoint():
    a = ["a"] * 600
    b = ["b"] * 600
    result = lcs_dp(a, b)
    assert result.matrix is None
    assert result.length == 0


def test_matrix_present_small():
    result = lcs_dp(tokenize("a b c"), tokenize("a b c"))
    assert result.matrix is not None
    assert len(result.matrix) == 4          # n + 1
    assert len(result.matrix[0]) == 4       # m + 1


# --------------------------------------------------------------------------- #
# similarity helper
# --------------------------------------------------------------------------- #
def test_lcs_similarity_helper():
    assert lcs_similarity("a b c", "a b c") == 1.0
    assert lcs_similarity("", "") == 1.0
    assert lcs_similarity("a b", "x y") == 0.0


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #
def test_to_dict_json_serializable():
    result = lcs_dp(tokenize("a b c d"), tokenize("a b x d"))
    d = result.to_dict()
    json.dumps(d)  # must not raise
    assert d["matrix"] is not None
    assert isinstance(d["length"], int)


def test_result_type():
    assert isinstance(lcs_dp("a", "a"), LCSResult)
