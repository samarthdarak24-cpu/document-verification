"""Tests for :mod:`app.algorithms.kmp` (KMP exact substring search)."""

import random

import pytest

from app.algorithms.kmp import KMPResult, build_lps, kmp_search


def naive_find_all(text: str, pattern: str) -> list[int]:
    """Overlap-permitting reference search using str.find in a loop."""
    if not pattern:
        return []
    out: list[int] = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + 1  # allow overlaps
    return out


# --------------------------------------------------------------------------- #
# build_lps
# --------------------------------------------------------------------------- #
def test_build_lps_empty():
    assert build_lps("") == []


def test_build_lps_single_char():
    assert build_lps("A") == [0]


def test_build_lps_ababc():
    assert build_lps("ABABC") == [0, 0, 1, 2, 0]


def test_build_lps_all_same():
    assert build_lps("AAAA") == [0, 1, 2, 3]


def test_build_lps_no_repeat():
    assert build_lps("ABCDE") == [0, 0, 0, 0, 0]


def test_build_lps_aabaa():
    assert build_lps("AABAA") == [0, 1, 0, 1, 2]


# --------------------------------------------------------------------------- #
# kmp_search — edge cases
# --------------------------------------------------------------------------- #
def test_empty_pattern():
    result = kmp_search("hello world", "")
    assert result.matches == []
    assert result.comparisons == 0
    assert result.trace == []


def test_empty_text():
    result = kmp_search("", "abc")
    assert result.matches == []
    assert result.comparisons == 0


def test_pattern_longer_than_text():
    result = kmp_search("ab", "abcdef")
    assert result.matches == []
    assert result.comparisons == 0


def test_no_exception_on_degenerate():
    # None of these should raise.
    kmp_search("", "")
    kmp_search("a", "aaaa")
    kmp_search("", "x")


# --------------------------------------------------------------------------- #
# kmp_search — placement
# --------------------------------------------------------------------------- #
def test_match_at_start():
    assert kmp_search("hello world", "hello").matches == [0]


def test_match_at_middle():
    assert kmp_search("abcdefg", "cde").matches == [2]


def test_match_at_end():
    assert kmp_search("hello world", "world").matches == [6]


def test_multiple_matches():
    assert kmp_search("aXaXaX", "aX").matches == [0, 2, 4]


def test_overlapping_matches():
    assert kmp_search("aaaa", "aa").matches == [0, 1, 2]


def test_adversarial_repeated_pattern():
    # Classic repeated-pattern adversarial case.
    result = kmp_search("aaabaaab", "aaab")
    assert result.matches == [0, 4]


def test_no_match():
    result = kmp_search("abcdef", "xyz")
    assert result.matches == []
    assert result.comparisons > 0  # still did real work


# --------------------------------------------------------------------------- #
# Unicode
# --------------------------------------------------------------------------- #
def test_unicode_word():
    text = "café résumé"
    assert kmp_search(text, "résumé").matches == [5]


def test_unicode_accent_char_repeats():
    text = "café résumé"
    assert kmp_search(text, "é").matches == [3, 6, 10]


def test_cjk():
    # Code-point indices: 你(0) 好(1) 世(2) 界(3) ，(4) 你(5) 好(6)
    text = "你好世界，你好"
    assert kmp_search(text, "你好").matches == [0, 5]


# --------------------------------------------------------------------------- #
# counters / trace
# --------------------------------------------------------------------------- #
def test_comparisons_positive_for_real_search():
    result = kmp_search("abcabcabc", "abc")
    assert result.comparisons > 0
    assert result.matches == [0, 3, 6]


def test_elapsed_ns_nonneg():
    result = kmp_search("abcdefg", "cd")
    assert result.elapsed_ns >= 0


def test_trace_empty_by_default():
    result = kmp_search("abcabc", "abc")
    assert result.trace == []


def test_trace_present_when_requested():
    result = kmp_search("aaaa", "aa", trace=True)
    assert len(result.trace) > 0
    for step in result.trace:
        assert set(step.keys()) == {
            "step", "text_index", "pattern_index", "action", "description"
        }
        assert step["action"] in {"match", "mismatch", "shift", "start"}
    # starts with a "start" marker
    assert result.trace[0]["action"] == "start"


def test_trace_capped_at_500():
    result = kmp_search("a" * 2000, "a" * 3, trace=True)
    assert len(result.trace) <= 500


def test_to_dict_json_serializable():
    import json
    result = kmp_search("abcabc", "abc", trace=True)
    d = result.to_dict()
    # Should not raise.
    json.dumps(d)
    assert d["matches"] == [0, 3]


def test_result_type():
    assert isinstance(kmp_search("abc", "b"), KMPResult)


# --------------------------------------------------------------------------- #
# Randomized cross-check vs naive
# --------------------------------------------------------------------------- #
def test_randomized_cross_check_against_naive():
    rng = random.Random(42)
    for _ in range(200):
        t_len = rng.randint(0, 40)
        p_len = rng.randint(0, 8)
        text = "".join(rng.choice("abc") for _ in range(t_len))
        pattern = "".join(rng.choice("abc") for _ in range(p_len))
        result = kmp_search(text, pattern)
        assert result.matches == naive_find_all(text, pattern), (
            f"text={text!r} pattern={pattern!r}"
        )
