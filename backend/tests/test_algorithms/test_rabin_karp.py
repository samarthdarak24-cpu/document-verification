"""Tests for :mod:`app.algorithms.rabin_karp` (Rabin-Karp rolling-hash search)."""

import json
import random

from app.algorithms.rabin_karp import RabinKarpResult, rabin_karp_search


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
        start = idx + 1
    return out


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #
def test_empty_pattern():
    result = rabin_karp_search("hello", "")
    assert result.matches == []
    assert result.hash_comparisons == 0
    assert result.base == 257
    assert result.modulus == 1_000_000_007


def test_empty_text():
    result = rabin_karp_search("", "abc")
    assert result.matches == []
    assert result.hash_comparisons == 0


def test_pattern_longer_than_text():
    result = rabin_karp_search("ab", "abcdef")
    assert result.matches == []


# --------------------------------------------------------------------------- #
# Basic matches
# --------------------------------------------------------------------------- #
def test_single_char_pattern():
    assert rabin_karp_search("abcabc", "b").matches == [1, 4]


def test_word_match():
    assert rabin_karp_search("abcabd", "abc").matches == [0]


def test_multiple_matches():
    assert rabin_karp_search("aXaXaX", "aX").matches == [0, 2, 4]


def test_overlapping_matches():
    assert rabin_karp_search("aaaa", "aa").matches == [0, 1, 2]


def test_no_match():
    result = rabin_karp_search("abcdef", "xyz")
    assert result.matches == []
    assert result.hash_comparisons > 0  # did real window work


# --------------------------------------------------------------------------- #
# Unicode
# --------------------------------------------------------------------------- #
def test_unicode_word():
    assert rabin_karp_search("café café", "café").matches == [0, 5]


def test_cjk():
    assert rabin_karp_search("你好世界你好", "你好").matches == [0, 4]


# --------------------------------------------------------------------------- #
# Counters / verification
# --------------------------------------------------------------------------- #
def test_hash_comparisons_positive():
    result = rabin_karp_search("abcabcabc", "abc")
    assert result.hash_comparisons > 0
    assert result.matches == [0, 3, 6]


def test_char_verification_counts_exact():
    # With the default large modulus only hash-matching windows pay the cost of
    # character verification: "abcabd"/"abc" has exactly one hash-matching window
    # (window 0), so char_comparisons == 3 and collisions == 0.
    result = rabin_karp_search("abcabd", "abc")
    assert result.char_comparisons == 3
    assert result.collisions == 0


def test_forced_collisions_modulus_one():
    # modulus=1 -> every window hashes to 0, forcing char verification.
    result = rabin_karp_search("abcabd", "abc", modulus=1)
    assert result.matches == [0]           # still correct
    assert result.collisions == 3          # 3 windows hash-equal but differ
    assert result.char_comparisons == 8
    assert result.hash_comparisons == 4     # 4 windows total
    for step in result.trace:
        if step["hash_match"]:
            assert step["char_match"] in (True, False)


def test_custom_base_modulus_recorded():
    result = rabin_karp_search("abcabc", "bc", base=101, modulus=97)
    assert result.base == 101
    assert result.modulus == 97


# --------------------------------------------------------------------------- #
# Trace
# --------------------------------------------------------------------------- #
def test_trace_empty_by_default():
    assert rabin_karp_search("abcabc", "bc").trace == []


def test_trace_present_when_requested():
    result = rabin_karp_search("abcabd", "abc", trace=True)
    assert len(result.trace) > 0
    for step in result.trace:
        assert set(step.keys()) == {
            "window_start", "window_end", "window_hash", "pattern_hash",
            "hash_match", "char_match", "action", "description",
        }
        assert step["action"] in {
            "hash_check", "verified_match", "collision", "reject"
        }
    # a real match should be recorded as verified_match somewhere
    assert any(s["action"] == "verified_match" for s in result.trace)


def test_trace_capped_at_500():
    result = rabin_karp_search("a" * 2000, "a", modulus=1, trace=True)
    assert len(result.trace) <= 500


def test_to_dict_json_serializable():
    result = rabin_karp_search("abcabd", "abc", trace=True, modulus=1)
    json.dumps(result.to_dict())  # must not raise


def test_result_type():
    assert isinstance(rabin_karp_search("abc", "b"), RabinKarpResult)


# --------------------------------------------------------------------------- #
# Randomized cross-check vs naive (default modulus)
# --------------------------------------------------------------------------- #
def test_randomized_cross_check_against_naive():
    rng = random.Random(42)
    for _ in range(200):
        t_len = rng.randint(0, 40)
        p_len = rng.randint(0, 8)
        text = "".join(rng.choice("abc") for _ in range(t_len))
        pattern = "".join(rng.choice("abc") for _ in range(p_len))
        result = rabin_karp_search(text, pattern, modulus=101)
        assert result.matches == naive_find_all(text, pattern), (
            f"text={text!r} pattern={pattern!r}"
        )
