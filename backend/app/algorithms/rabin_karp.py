"""Rabin-Karp substring search using a polynomial rolling hash.

Purpose
-------
Find all occurrences of ``pattern`` inside ``text`` by comparing *hash values*
of fixed-size windows instead of comparing characters at every position. A
polynomial rolling hash lets each subsequent window's hash be computed from the
previous one in O(1) time by subtracting the outgoing character's contribution
and adding the incoming character's contribution.

Because hashes can collide (two different windows may share a hash value),
DocuTrace ALWAYS re-verifies a window's characters after a hash match before
reporting a hit. Spurious matches are counted as ``collisions``.

DocuTrace use case
------------------
Fast fingerprinting of sliding windows over extracted document text, e.g. to
detect whether a known template fragment (a suspicious "boilerplate" block)
appears anywhere in a long PDF, or as the hashing core of a k-gram duplicate
detector across many documents.

Complexity
----------
* Average / expected time O(n + m)  (n = len(text), m = len(pattern)): each of
  the n windows updates its hash in O(1) and usually rejects on hash alone.
* Worst case O(n * m): adversarial inputs (or a tiny modulus that forces every
  window to hash-equal) defeat the hash filter, so every window is re-verified
  character-by-character. This is why character verification must be explicit.
* Space O(1) auxiliary (a few integers) beyond the output/trace.

Unicode-safe: hashing uses ``ord()`` over code points, so accented/CJK text works.
"""

from __future__ import annotations

import time

_MAX_TRACE = 500


class RabinKarpResult:
    """Result of a :func:`rabin_karp_search` call."""

    def __init__(
        self,
        matches: list[int],
        hash_comparisons: int,
        char_comparisons: int,
        collisions: int,
        elapsed_ns: int,
        base: int,
        modulus: int,
        trace: list[dict],
    ) -> None:
        self.matches: list[int] = matches
        self.hash_comparisons: int = hash_comparisons
        self.char_comparisons: int = char_comparisons
        self.collisions: int = collisions            # hash equal, chars differed
        self.elapsed_ns: int = elapsed_ns
        self.base: int = base
        self.modulus: int = modulus
        self.trace: list[dict] = trace

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "matches": list(self.matches),
            "hash_comparisons": self.hash_comparisons,
            "char_comparisons": self.char_comparisons,
            "collisions": self.collisions,
            "elapsed_ns": self.elapsed_ns,
            "base": self.base,
            "modulus": self.modulus,
            "trace": [dict(step) for step in self.trace],
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"RabinKarpResult(matches={self.matches}, "
            f"hash_comparisons={self.hash_comparisons}, "
            f"collisions={self.collisions})"
        )


def rabin_karp_search(
    text: str,
    pattern: str,
    trace: bool = False,
    base: int = 257,
    modulus: int = 1_000_000_007,
) -> RabinKarpResult:
    """Find all (overlapping) occurrences of ``pattern`` in ``text``.

    Rolling hash of ``sum(ord(c) * base**...)`` taken modulo ``modulus``. Every
    hash match is re-verified character-by-character before being accepted, so
    results are always correct even under hash collisions.

    Returns a :class:`RabinKarpResult`. Empty pattern or pattern longer than
    the text yields an empty result (no exception).
    """
    start_ns = time.perf_counter_ns()

    n = len(text)
    m = len(pattern)

    matches: list[int] = []
    hash_comparisons = 0
    char_comparisons = 0
    collisions = 0
    trace_steps: list[dict] = []

    if m == 0 or m > n:
        return RabinKarpResult(
            matches=[], hash_comparisons=0, char_comparisons=0, collisions=0,
            elapsed_ns=time.perf_counter_ns() - start_ns,
            base=base, modulus=modulus, trace=[],
        )

    # base^(m-1) mod modulus -> contribution weight of the outgoing character.
    high_order = pow(base, m - 1, modulus)

    # Pattern hash.
    pattern_hash = 0
    for ch in pattern:
        pattern_hash = (pattern_hash * base + ord(ch)) % modulus

    # Initial window hash for text[0:m].
    window_hash = 0
    for ch in text[:m]:
        window_hash = (window_hash * base + ord(ch)) % modulus

    num_windows = n - m + 1
    for i in range(num_windows):
        hash_comparisons += 1
        hash_match = window_hash == pattern_hash
        char_match: bool | None = None

        if hash_match:
            # ALWAYS verify characters after a hash match (collision-prone).
            ok = True
            for k in range(m):
                char_comparisons += 1
                if text[i + k] != pattern[k]:
                    ok = False
                    break
            char_match = ok
            if ok:
                matches.append(i)
                action = "verified_match"
                description = (
                    f"Hash match at window {i} confirmed by {char_comparisons} "
                    f"char comparison(s)."
                )
            else:
                collisions += 1
                action = "collision"
                description = (
                    f"Hash match at window {i} but characters differ "
                    f"(collision #{collisions})."
                )
        else:
            action = "reject"
            description = f"Hash mismatch at window {i}; window rejected."

        if trace and len(trace_steps) < _MAX_TRACE:
            trace_steps.append({
                "window_start": i,
                "window_end": i + m,
                "window_hash": window_hash,
                "pattern_hash": pattern_hash,
                "hash_match": hash_match,
                "char_match": char_match,
                "action": action,
                "description": description,
            })

        # Roll the hash to the next window in O(1).
        if i < num_windows - 1:
            # Remove outgoing char, shift left, add incoming char (mod-safe).
            window_hash = (window_hash - ord(text[i]) * high_order) % modulus
            window_hash = (window_hash * base + ord(text[i + m])) % modulus

    elapsed_ns = time.perf_counter_ns() - start_ns
    return RabinKarpResult(
        matches=matches,
        hash_comparisons=hash_comparisons,
        char_comparisons=char_comparisons,
        collisions=collisions,
        elapsed_ns=elapsed_ns,
        base=base,
        modulus=modulus,
        trace=trace_steps if trace else [],
    )
