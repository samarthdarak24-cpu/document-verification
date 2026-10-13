"""Knuth-Morris-Pratt (KMP) exact substring search.

Purpose
-------
Find every occurrence of ``pattern`` inside ``text`` without re-examining
characters that are already known to match. KMP pre-computes a
Longest-Prefix-Suffix (LPS) table so that, on a mismatch, the pattern can be
shifted intelligently instead of restarting the comparison from the next text
position (as a naive scan would).

DocuTrace use case
------------------
Locating known boilerplate markers (e.g. a repeated reference-number label
``"Ref No:"`` or a template placeholder) inside extracted PDF text so the system
can segment a document into header/body regions before running the heavier
similarity algorithms.

Complexity
----------
* ``build_lps``: time O(m), space O(m) where m = len(pattern).
* ``kmp_search``:
  - Best case O(n)  (n = len(text); no backtracking on text).
  - Average case O(n + m).
  - Worst case O(n + m).
  - Space O(m) for the LPS table (plus O(k) for k matches / O(trace) trace).
* Compared to naive O(n*m) search, KMP guarantees linear O(n+m) time by never
  moving the text cursor ``i`` backwards.

Unicode-safe: comparisons operate on Python ``str`` code points directly, so
accented characters (``"café"``) and CJK text are handled correctly.
"""

from __future__ import annotations

import time
from typing import Optional

# Upper bound on recorded trace steps (contract requirement).
_MAX_TRACE = 500


def build_lps(pattern: str) -> list[int]:
    """Return the Longest-Prefix-Suffix (LPS) table for ``pattern``.

    ``lps[i]`` is the length of the longest *proper* prefix of
    ``pattern[0..i]`` that is also a suffix of that substring. An empty pattern
    yields an empty list.

    Time O(m), auxiliary space O(m) where m = len(pattern).
    """
    if not pattern:
        return []
    lps = [0] * len(pattern)
    length = 0  # length of the current longest prefix-suffix
    i = 1
    while i < len(pattern):
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                # Fall back to the previous candidate without moving ``i``.
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1
    return lps


class KMPResult:
    """Result of a :func:`kmp_search` call."""

    def __init__(
        self,
        matches: list[int],
        comparisons: int,
        elapsed_ns: int,
        trace: list[dict],
    ) -> None:
        self.matches: list[int] = matches          # start indices of matches
        self.comparisons: int = comparisons        # character comparisons made
        self.elapsed_ns: int = elapsed_ns          # time.perf_counter_ns delta
        self.trace: list[dict] = trace             # [] unless trace=True

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (all plain types)."""
        return {
            "matches": list(self.matches),
            "comparisons": self.comparisons,
            "elapsed_ns": self.elapsed_ns,
            "trace": [dict(step) for step in self.trace],
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"KMPResult(matches={self.matches}, "
            f"comparisons={self.comparisons})"
        )


def kmp_search(text: str, pattern: str, trace: bool = False) -> KMPResult:
    """Search for all (overlapping) occurrences of ``pattern`` in ``text``.

    Returns a :class:`KMPResult`. An empty pattern, or a pattern longer than the
    text, yields ``matches=[]`` and ``comparisons=0`` (no exception raised).

    Time O(n + m), space O(m) (see module docstring).
    """
    start_ns = time.perf_counter_ns()

    matches: list[int] = []
    comparisons = 0
    trace_steps: list[dict] = []

    n = len(text)
    m = len(pattern)

    if m == 0 or m > n:
        # Nothing to search: return an empty but well-formed result.
        elapsed_ns = time.perf_counter_ns() - start_ns
        return KMPResult(matches=[], comparisons=0, elapsed_ns=elapsed_ns,
                         trace=[])

    lps = build_lps(pattern)

    step = 0
    if trace:
        trace_steps.append({
            "step": step,
            "text_index": 0,
            "pattern_index": 0,
            "action": "start",
            "description": (
                f"Begin KMP search: text length {n}, pattern length {m}."
            ),
        })
        step += 1

    i = 0  # cursor into text
    j = 0  # cursor into pattern
    while i < n:
        comparisons += 1
        if text[i] == pattern[j]:
            # Characters match -> advance both cursors.
            if trace and len(trace_steps) < _MAX_TRACE:
                trace_steps.append({
                    "step": step,
                    "text_index": i,
                    "pattern_index": j,
                    "action": "match",
                    "description": (
                        f"Match at text[{i}]={text[i]!r} with "
                        f"pattern[{j}]={pattern[j]!r}."
                    ),
                })
                step += 1
            i += 1
            j += 1
            if j == m:
                # Full pattern matched starting at i - j.
                matches.append(i - j)
                # Allow overlapping matches by following the LPS fallback.
                j = lps[j - 1]
        else:
            if j != 0:
                # Shift: reuse LPS to avoid rechecking text characters.
                if trace and len(trace_steps) < _MAX_TRACE:
                    trace_steps.append({
                        "step": step,
                        "text_index": i,
                        "pattern_index": j,
                        "action": "shift",
                        "description": (
                            f"Mismatch at text[{i}]={text[i]!r} vs "
                            f"pattern[{j}]={pattern[j]!r}; shift pattern "
                            f"using LPS to index {lps[j - 1]}."
                        ),
                    })
                    step += 1
                j = lps[j - 1]
            else:
                # No matching prefix: advance the text cursor.
                if trace and len(trace_steps) < _MAX_TRACE:
                    trace_steps.append({
                        "step": step,
                        "text_index": i,
                        "pattern_index": j,
                        "action": "mismatch",
                        "description": (
                            f"Mismatch at text[{i}]={text[i]!r} vs "
                            f"pattern[0]={pattern[0]!r}; advance text cursor."
                        ),
                    })
                    step += 1
                i += 1

    elapsed_ns = time.perf_counter_ns() - start_ns
    return KMPResult(
        matches=matches,
        comparisons=comparisons,
        elapsed_ns=elapsed_ns,
        trace=trace_steps if trace else [],
    )
