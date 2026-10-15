"""Similarity detection: candidate generation, then bounded detailed comparison.

Why two phases
--------------
Comparing every pair of documents is O(n^2) pairs, and each pair costs an
O(n*m) DP — for 100 documents of 500 tokens that is ~2.5 *billion* DP cells.
DocuTrace therefore splits the work:

**Phase 1 — candidate generation (cheap, all pairs).**
Documents are first filtered by ``doc_type`` (an invoice is never a candidate
match for a mark sheet), then by a token-set Jaccard index over character
3-gram shingles. Shingles rather than raw tokens make the filter robust to
morphological variants ("invoice" / "invoiced"), and a set-based Jaccard index
costs O(|A| + |B|) per pair instead of a DP.

**Phase 2 — detailed comparison (expensive, bounded candidates only).**
Only pairs whose Jaccard index reaches ``candidate_min`` are compared with the
real DP algorithms: LCS similarity and Levenshtein edit similarity over the
normalised token lists, each **capped at ``DP_MAX_TOKENS``** (further reduced if
the product of the two lengths would exceed the DP cell budget). Truncation is
recorded in the result — it is never silently applied.

Token-level diff
----------------
The LCS backtrack yields matched / inserted / deleted tokens (words added,
removed and unchanged), and the edit-distance script yields substitutions, which
together give a diff a human can read in a report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.algorithms.edit_distance import edit_distance
from app.algorithms.lcs import lcs_dp
from app.services.normalization import normalize_for_comparison, normalize_label

#: Default Jaccard threshold for candidate selection (overridden by settings).
DEFAULT_JACCARD_CANDIDATE = 0.15

#: Default shingle size.
DEFAULT_SHINGLE_SIZE = 3

#: Hard product limit for the O(n*m) DP: above this, the token cap is lowered so
#: the product of the two sequence lengths stays within budget.
DP_CELL_BUDGET = 2_000_000

#: Maximum tokens fed to the edit-distance script reconstruction.
_MAX_EDIT_SCRIPT_TOKENS = 500

#: Overall score weights (documented so a reviewer can recompute any score).
WEIGHT_LCS = 0.6
WEIGHT_EDIT = 0.4


# --------------------------------------------------------------------------- #
# Shingles & Jaccard
# --------------------------------------------------------------------------- #
def shingles(tokens: Sequence[str], size: int = DEFAULT_SHINGLE_SIZE) -> Set[str]:
    """Return the set of character ``size``-gram shingles over ``tokens``.

    Token groups are joined with a space so shingles do not straddle token
    boundaries in a way that creates spurious matches between unrelated words.
    """
    if not tokens:
        return set()
    text = " ".join(tokens)
    if len(text) <= size:
        return {text} if text else set()
    return {text[i : i + size] for i in range(len(text) - size + 1)}


def jaccard(left: Set[str], right: Set[str]) -> float:
    """Jaccard index ``|A n B| / |A u B|`` (1.0 when both are empty)."""
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    """A cheap candidate pair produced by phase 1."""

    document_id: str
    filename: str
    doc_type: str
    jaccard: float
    shared_shingles: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "doc_type": self.doc_type,
            "jaccard": round(self.jaccard, 4),
            "shared_shingles": self.shared_shingles,
        }


@dataclass
class ComparisonResult:
    """A bounded, fully measured document-to-document comparison."""

    text_similarity: float = 0.0
    edit_similarity: float = 0.0
    overall_score: float = 0.0
    lcs_length: int = 0
    edit_distance: int = 0
    source_tokens: int = 0
    target_tokens: int = 0
    compared_source_tokens: int = 0
    compared_target_tokens: int = 0
    truncated: bool = False
    truncation_note: Optional[str] = None
    insertions: List[str] = field(default_factory=list)
    deletions: List[str] = field(default_factory=list)
    replacements: List[Dict[str, Optional[str]]] = field(default_factory=list)
    words_added: int = 0
    words_removed: int = 0
    words_unchanged: int = 0
    substitutions: int = 0
    field_differences: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_similarity": round(self.text_similarity, 4),
            "edit_similarity": round(self.edit_similarity, 4),
            "overall_score": round(self.overall_score, 4),
            "lcs_length": self.lcs_length,
            "edit_distance": self.edit_distance,
            "source_tokens": self.source_tokens,
            "target_tokens": self.target_tokens,
            "compared_source_tokens": self.compared_source_tokens,
            "compared_target_tokens": self.compared_target_tokens,
            "truncated": self.truncated,
            "truncation_note": self.truncation_note,
            "insertions": list(self.insertions[:100]),
            "deletions": list(self.deletions[:100]),
            "replacements": list(self.replacements[:100]),
            "words_added": self.words_added,
            "words_removed": self.words_removed,
            "words_unchanged": self.words_unchanged,
            "substitutions": self.substitutions,
            "field_differences": list(self.field_differences),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------- #
# Phase 1
# --------------------------------------------------------------------------- #
def find_candidates(
    source_tokens: Sequence[str],
    source_doc_type: str,
    others: Sequence[Any],
    *,
    doc_type_field: str = "doc_type",
    tokens_field: str = "comparison_tokens",
    id_field: str = "id",
    filename_field: str = "filename",
    jaccard_threshold: float = DEFAULT_JACCARD_CANDIDATE,
    shingle_size: int = DEFAULT_SHINGLE_SIZE,
) -> List[Candidate]:
    """Return the documents in ``others`` worth a detailed comparison.

    ``others`` items may be ORM rows, dicts or objects; the ``*_field``
    arguments let the same routine serve both the pipeline (ORM rows) and the
    API layer (dicts). Candidates are ranked by Jaccard (descending) so the
    pipeline can stop early if a cap is configured.
    """
    source_shingles = shingles(list(source_tokens), shingle_size)
    candidates: List[Candidate] = []
    for other in others:
        other_tokens = _read(other, tokens_field)
        other_type = _read(other, doc_type_field)
        if source_doc_type and other_type and other_type != source_doc_type:
            continue  # different document class: never compared
        score = jaccard(source_shingles, shingles(list(other_tokens or []), shingle_size))
        if score < jaccard_threshold:
            continue
        candidates.append(
            Candidate(
                document_id=str(_read(other, id_field)),
                filename=str(_read(other, filename_field) or ""),
                doc_type=str(other_type or ""),
                jaccard=score,
                shared_shingles=len(source_shingles & shingles(list(other_tokens or []), shingle_size)),
            )
        )
    candidates.sort(key=lambda item: (-item.jaccard, item.document_id))
    return candidates


def _read(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


# --------------------------------------------------------------------------- #
# Phase 2
# --------------------------------------------------------------------------- #
def _cap_tokens(
    source: Sequence[str], target: Sequence[str], max_tokens: int
) -> Tuple[List[str], List[str], bool, Optional[str]]:
    """Truncate both token lists so the DP stays inside the cell budget."""
    source_list = list(source)
    target_list = list(target)
    truncated = False
    note: Optional[str] = None
    if len(source_list) > max_tokens or len(target_list) > max_tokens:
        truncated = True
        source_list = source_list[:max_tokens]
        target_list = target_list[:max_tokens]
        note = (
            f"Token lists truncated to {max_tokens} tokens per document "
            f"(DP_MAX_TOKENS)."
        )
    product = len(source_list) * len(target_list)
    if product > DP_CELL_BUDGET:
        reduced = max(1, DP_CELL_BUDGET // max(1, min(len(source_list), len(target_list))))
        source_list = source_list[:reduced]
        target_list = target_list[:reduced]
        truncated = True
        note = (
            f"Token lists reduced to {reduced} tokens each so the DP product "
            f"({reduced * reduced:,} cells) stays within the {DP_CELL_BUDGET:,} "
            f"cell budget (original lengths {len(source)} and {len(target)})."
        )
    return source_list, target_list, truncated, note


def compare_documents(
    source_tokens: Sequence[str],
    target_tokens: Sequence[str],
    *,
    max_tokens: int = 2000,
    source_fields: Optional[Dict[str, str]] = None,
    target_fields: Optional[Dict[str, str]] = None,
    critical_fields: Optional[Iterable[str]] = None,
    field_edit_similarity_min: float = 0.6,
) -> ComparisonResult:
    """Run the bounded detailed comparison of two token sequences."""
    started = time.perf_counter()
    result = ComparisonResult(
        source_tokens=len(source_tokens),
        target_tokens=len(target_tokens),
    )
    notes: List[str] = list(result.notes)

    capped_source, capped_target, truncated, note = _cap_tokens(
        source_tokens, target_tokens, max_tokens
    )
    result.compared_source_tokens = len(capped_source)
    result.compared_target_tokens = len(capped_target)
    result.truncated = truncated
    if note:
        result.truncation_note = note
        notes.append(note)

    # ---- LCS (token level) ------------------------------------------------- #
    lcs_result = lcs_dp(capped_source, capped_target)
    result.text_similarity = float(lcs_result.similarity)
    result.lcs_length = int(lcs_result.length)
    result.words_unchanged = int(lcs_result.length)
    result.words_removed = len(lcs_result.unmatched_a)
    result.words_added = len(lcs_result.unmatched_b)
    result.deletions = list(lcs_result.unmatched_a)
    result.insertions = list(lcs_result.unmatched_b)
    notes.append(
        f"LCS: {result.lcs_length} matching tokens "
        f"({result.words_unchanged} unchanged, {result.words_removed} removed, "
        f"{result.words_added} added)."
    )

    # ---- Edit distance (token level) --------------------------------------- #
    with_operations = len(capped_source) <= _MAX_EDIT_SCRIPT_TOKENS and (
        len(capped_target) <= _MAX_EDIT_SCRIPT_TOKENS
    )
    edit_result = edit_distance(capped_source, capped_target, with_operations=with_operations)
    result.edit_distance = int(edit_result.distance)
    result.edit_similarity = float(edit_result.similarity)
    replacements = [
        {"old": op.get("old"), "new": op.get("new")}
        for op in edit_result.operations
        if op.get("op") == "substitute"
    ]
    result.replacements = replacements
    result.substitutions = len(replacements)
    notes.append(
        f"Edit distance: {result.edit_distance} on the token sequences "
        f"({result.substitutions} substitutions)."
    )
    if not with_operations:
        notes.append(
            "Edit script reconstruction skipped: sequences exceed "
            f"{_MAX_EDIT_SCRIPT_TOKENS} tokens, so only the distance is reported."
        )

    result.overall_score = round(
        WEIGHT_LCS * result.text_similarity + WEIGHT_EDIT * result.edit_similarity, 6
    )

    # ---- Field-level differences ------------------------------------------- #
    if source_fields is not None or target_fields is not None:
        result.field_differences = compare_field_values(
            source_fields or {},
            target_fields or {},
            critical_fields=critical_fields,
            edit_similarity_min=field_edit_similarity_min,
        )
    result.notes = notes
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result


def compare_field_values(
    source_fields: Dict[str, str],
    target_fields: Dict[str, str],
    *,
    critical_fields: Optional[Iterable[str]] = None,
    edit_similarity_min: float = 0.6,
) -> List[Dict[str, Any]]:
    """Compare two field maps by name.

    For each shared field name:

    * values that are equal *after label normalization* (case/punctuation
      insensitive) are reported ``equal``;
    * short values (<= 64 characters) are additionally scored with Levenshtein
      edit similarity, which tolerates a one-character OCR slip;
    * long values are compared exactly after normalization (a character-level DP
      on prose would be both slow and meaningless).
    """
    critical = {name.lower() for name in (critical_fields or [])}
    differences: List[Dict[str, Any]] = []
    for name in sorted(set(source_fields) & set(target_fields)):
        source_value = source_fields[name] or ""
        target_value = target_fields[name] or ""
        source_norm = normalize_label(source_value)
        target_norm = normalize_label(target_value)
        equal = source_norm == target_norm
        entry: Dict[str, Any] = {
            "field": name,
            "source_value": source_value,
            "target_value": target_value,
            "equal": equal,
            "critical": name.lower() in critical,
            "comparison": "normalized_exact",
            "edit_distance": 0,
            "similarity": 1.0 if equal else 0.0,
        }
        if not equal and len(source_value) <= 64 and len(target_value) <= 64:
            edit_result = edit_distance(source_value, target_value)
            entry["comparison"] = "edit_distance"
            entry["edit_distance"] = int(edit_result.distance)
            entry["similarity"] = round(float(edit_result.similarity), 4)
            entry["mismatch"] = edit_result.similarity < edit_similarity_min
        else:
            entry["mismatch"] = not equal
        differences.append(entry)

    for name in sorted(set(source_fields) - set(target_fields)):
        differences.append(
            {
                "field": name,
                "source_value": source_fields[name],
                "target_value": None,
                "equal": False,
                "critical": name.lower() in critical,
                "comparison": "missing_in_target",
                "edit_distance": len(source_fields[name] or ""),
                "similarity": 0.0,
                "mismatch": True,
            }
        )
    for name in sorted(set(target_fields) - set(source_fields)):
        differences.append(
            {
                "field": name,
                "source_value": None,
                "target_value": target_fields[name],
                "equal": False,
                "critical": name.lower() in critical,
                "comparison": "missing_in_source",
                "edit_distance": len(target_fields[name] or ""),
                "similarity": 0.0,
                "mismatch": True,
            }
        )
    return differences


def critical_mismatches(
    field_differences: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return the critical field entries that actually differ."""
    return [
        entry for entry in field_differences
        if entry.get("critical") and not entry.get("equal")
    ]


# --------------------------------------------------------------------------- #
# Token cache (documents are re-extracted rather than stored as text columns)
# --------------------------------------------------------------------------- #
#: ``(document_id, mtime) -> tokens``. The DB stores a *preview* of the text, so
#: the token list is rebuilt from the stored file and memoised per (id, mtime).
#: The mtime key means a re-upload never serves stale tokens.
_TOKEN_CACHE: Dict[Tuple[str, int], List[str]] = {}
_TOKEN_CACHE_MAX = 512


def remember_tokens(document_id: str, mtime: int, tokens: Sequence[str]) -> None:
    """Memoise the token list of ``document_id`` (bounded LRU-ish eviction)."""
    key = (str(document_id), int(mtime))
    if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
        # Drop the oldest inserted key; the cache is a speed optimisation only.
        _TOKEN_CACHE.pop(next(iter(_TOKEN_CACHE)), None)
    _TOKEN_CACHE[key] = list(tokens)


def cached_tokens(document_id: str, mtime: int) -> Optional[List[str]]:
    """Return memoised tokens, or ``None`` when not cached."""
    return _TOKEN_CACHE.get((str(document_id), int(mtime)))


def clear_token_cache() -> None:
    """Empty the token cache (used by tests)."""
    _TOKEN_CACHE.clear()


def tokens_from_text(text: str) -> List[str]:
    """Normalise ``text`` into comparison tokens."""
    return normalize_for_comparison(text)


def similarity_label(score: float) -> str:
    """Human-readable bucket for a similarity score (used in reports)."""
    if score >= 0.95:
        return "identical"
    if score >= 0.85:
        return "near-identical"
    if score >= 0.6:
        return "similar"
    if score >= 0.15:
        return "some shared content"
    return "unrelated"


def overall_score(lcs_similarity: float, edit_similarity: float) -> float:
    """Combine the two similarity measures with the documented weights."""
    return round(
        WEIGHT_LCS * lcs_similarity + WEIGHT_EDIT * edit_similarity, 6
    )
