"""Document change detection: *what changed* between two versions of a document.

Motivation
----------
Duplicate detection answers "are these two documents the same?". When the answer
is *no*, the useful follow-up is "then what changed?" — a human reviewing a
re-submitted certificate needs the difference, not a similarity percentage.

This module produces that difference, and it does so with DocuTrace's own DAA
algorithms rather than :mod:`difflib`:

* **Word-level alignment** comes from :func:`app.algorithms.lcs.lcs_dp`. The LCS
  backtrack already yields matched / inserted / deleted tokens; this module
  groups those into readable hunks. LCS is the right primitive here because it
  is robust to insertions and reorderings, which is exactly the shape of a
  document edit.
* **Character-level refinement** of each changed region comes from
  :func:`app.algorithms.edit_distance.edit_distance` with ``with_operations``
  enabled, so a changed registration number reports *which digits* moved rather
  than a whole-word replacement.
* **Typography comparison** reuses :class:`app.services.pdf_metadata.TextSpan`:
  two spans with identical text but different font, size, colour or position are
  reported as a style change. That is the signal a text-only diff can never see.

Everything in this module is pure: it takes text and span objects and returns
dataclasses. File I/O lives in the caller (the API layer), which keeps the
change logic unit-testable without a PDF on disk.

Status vocabulary
-----------------
A hunk is ``insert`` / ``delete`` / ``replace`` — a factual description of the
text, never an accusation. As everywhere else in DocuTrace, the system reports
measurements and lets the rule engine (or a human) draw the conclusion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from app.algorithms.edit_distance import edit_distance
from app.algorithms.lcs import lcs_dp, tokenize

#: Default cap on tokens fed to the LCS DP (matches the project DP budget).
DEFAULT_MAX_TOKENS = 4_000

#: Default cap on character-level operations returned inside a replace hunk.
DEFAULT_MAX_CHAR_OPS = 40

#: Default cap on the number of hunks returned.
DEFAULT_MAX_HUNKS = 200


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class TextChangeHunk:
    """One contiguous region of difference between two texts."""

    type: str  # "insert" | "delete" | "replace"
    removed_text: str = ""
    added_text: str = ""
    removed_tokens: List[str] = field(default_factory=list)
    added_tokens: List[str] = field(default_factory=list)
    #: Character-level Levenshtein distance between the two sides of the hunk.
    char_edit_distance: int = 0
    #: Character-level edit script (capped) — only populated for ``replace``.
    char_operations: List[Dict[str, Any]] = field(default_factory=list)
    #: Index of the first affected token in the original / modified token list.
    original_index: Optional[int] = None
    modified_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "removed_text": self.removed_text,
            "added_text": self.added_text,
            "removed_tokens": list(self.removed_tokens),
            "added_tokens": list(self.added_tokens),
            "removed_token_count": len(self.removed_tokens),
            "added_token_count": len(self.added_tokens),
            "char_edit_distance": self.char_edit_distance,
            "char_operations": [dict(op) for op in self.char_operations],
            "original_index": self.original_index,
            "modified_index": self.modified_index,
        }


@dataclass
class StyleChange:
    """A typographic change for a text span that is otherwise identical."""

    text: str
    page: int
    changes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "changes": dict(self.changes),
        }


@dataclass
class ChangeReport:
    """The complete change analysis between an original and a modified document."""

    changed: bool
    text_similarity: float
    edit_similarity: float
    lcs_length: int
    original_token_count: int
    modified_token_count: int
    unchanged_tokens: int
    added_tokens: int
    removed_tokens: int
    hunks: List[TextChangeHunk] = field(default_factory=list)
    style_changes: List[StyleChange] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    algorithms_executed: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changed": self.changed,
            "verdict": self.verdict(),
            "text_similarity": round(self.text_similarity, 4),
            "edit_similarity": round(self.edit_similarity, 4),
            "lcs_length": self.lcs_length,
            "original_token_count": self.original_token_count,
            "modified_token_count": self.modified_token_count,
            "unchanged_tokens": self.unchanged_tokens,
            "added_tokens": self.added_tokens,
            "removed_tokens": self.removed_tokens,
            "hunk_count": len(self.hunks),
            "hunks": [hunk.to_dict() for hunk in self.hunks],
            "style_change_count": len(self.style_changes),
            "style_changes": [change.to_dict() for change in self.style_changes],
            "summary": dict(self.summary),
            "warnings": list(self.warnings),
            "algorithms_executed": list(self.algorithms_executed),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }

    def verdict(self) -> str:
        """A short factual label for the change, ordered by severity."""
        if not self.changed:
            return "identical"
        if self.style_changes and not self.hunks:
            return "metadata_only_change"
        if self.removed_tokens and self.added_tokens:
            return "content_replaced"
        if self.added_tokens:
            return "content_added"
        if self.removed_tokens:
            return "content_removed"
        return "changed"


# --------------------------------------------------------------------------- #
# Token alignment
# --------------------------------------------------------------------------- #
def _tokenize(text: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(text, str):
        return tokenize(text)
    return list(text)


def _group_hunks(alignment: Sequence[Dict[str, Any]]) -> List[TextChangeHunk]:
    """Group an LCS alignment into contiguous change hunks.

    The LCS backtrack emits a flat, forward-ordered list of ``match`` /
    ``delete`` / ``insert`` steps. A maximal run of non-match steps is one edit;
    a run containing both deletions and insertions is a ``replace``.
    """
    hunks: List[TextChangeHunk] = []
    index = 0
    total = len(alignment)
    while index < total:
        if alignment[index].get("op") == "match":
            index += 1
            continue
        start = index
        removed: List[str] = []
        added: List[str] = []
        while index < total and alignment[index].get("op") != "match":
            step = alignment[index]
            if step.get("op") == "delete" and step.get("a_token") is not None:
                removed.append(step["a_token"])
            elif step.get("op") == "insert" and step.get("b_token") is not None:
                added.append(step["b_token"])
            index += 1
        if not removed and not added:
            continue
        if removed and added:
            kind = "replace"
        elif removed:
            kind = "delete"
        else:
            kind = "insert"
        hunks.append(
            TextChangeHunk(
                type=kind,
                removed_text=" ".join(removed),
                added_text=" ".join(added),
                removed_tokens=removed,
                added_tokens=added,
                original_index=start,
                modified_index=start,
            )
        )
    return hunks


def detect_text_changes(
    original: Union[str, Sequence[str]],
    modified: Union[str, Sequence[str]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_char_ops: int = DEFAULT_MAX_CHAR_OPS,
    max_hunks: int = DEFAULT_MAX_HUNKS,
) -> ChangeReport:
    """Compare two texts and return a :class:`ChangeReport`.

    Word-level alignment uses LCS; each changed region is refined with a
    character-level edit distance so a single altered digit is reported as a
    substitution rather than a replaced word.

    ``max_tokens`` bounds the DP input (both sides are truncated to it, and the
    truncation is recorded as a warning — never applied silently).
    """
    started = time.perf_counter()
    warnings: List[str] = []

    original_tokens = _tokenize(original)
    modified_tokens = _tokenize(modified)

    truncated = False
    if len(original_tokens) > max_tokens:
        original_tokens = original_tokens[:max_tokens]
        truncated = True
    if len(modified_tokens) > max_tokens:
        modified_tokens = modified_tokens[:max_tokens]
        truncated = True
    if truncated:
        warnings.append(
            f"Token input truncated to {max_tokens} tokens per side for the "
            "LCS DP; the reported change counts are lower bounds."
        )

    lcs = lcs_dp(original_tokens, modified_tokens)
    hunks = _group_hunks(lcs.alignment)
    hunks_truncated = False
    if len(hunks) > max_hunks:
        hunks = hunks[:max_hunks]
        hunks_truncated = True

    # Character-level refinement: only ``replace`` hunks carry a two-sided text
    # to diff, so that is where the edit script is computed.
    total_char_edits = 0
    for hunk in hunks:
        if hunk.type == "replace":
            result = edit_distance(
                hunk.removed_text, hunk.added_text, with_operations=True
            )
            hunk.char_edit_distance = result.distance
            hunk.char_operations = result.operations[:max_char_ops]
            total_char_edits += result.distance
        elif hunk.type == "delete":
            hunk.char_edit_distance = len(hunk.removed_text)
            total_char_edits += len(hunk.removed_text)
        else:
            hunk.char_edit_distance = len(hunk.added_text)
            total_char_edits += len(hunk.added_text)

    # Headline edit similarity: character-level over the whole (re-joined) text.
    original_joined = " ".join(original_tokens)
    modified_joined = " ".join(modified_tokens)
    overall_edit = edit_distance(original_joined, modified_joined)

    added = sum(len(hunk.added_tokens) for hunk in hunks)
    removed = sum(len(hunk.removed_tokens) for hunk in hunks)
    unchanged = lcs.length

    summary = {
        "changed": bool(hunks),
        "hunk_count": len(hunks),
        "insert_hunks": sum(1 for h in hunks if h.type == "insert"),
        "delete_hunks": sum(1 for h in hunks if h.type == "delete"),
        "replace_hunks": sum(1 for h in hunks if h.type == "replace"),
        "char_edit_operations": total_char_edits,
        "truncated_tokens": truncated,
        "truncated_hunks": hunks_truncated,
    }

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ChangeReport(
        changed=bool(hunks),
        text_similarity=lcs.similarity,
        edit_similarity=overall_edit.similarity,
        lcs_length=lcs.length,
        original_token_count=len(original_tokens),
        modified_token_count=len(modified_tokens),
        unchanged_tokens=unchanged,
        added_tokens=added,
        removed_tokens=removed,
        hunks=hunks,
        summary=summary,
        warnings=warnings,
        algorithms_executed=["tokenize", "lcs_dp", "edit_distance"],
        elapsed_ms=elapsed_ms,
    )


# --------------------------------------------------------------------------- #
# Typography comparison
# --------------------------------------------------------------------------- #
def _span_text_key(text: str) -> str:
    """Normalise span text for alignment (case/whitespace insensitive)."""
    return " ".join(text.split()).casefold()


def detect_style_changes(
    original_spans: Sequence[Any],
    modified_spans: Sequence[Any],
    *,
    max_spans: int = DEFAULT_MAX_TOKENS,
) -> List[StyleChange]:
    """Report typographic changes for spans whose *text* is unchanged.

    Spans are aligned with LCS over their normalised text, so identical fields
    pair up even when surrounding text moved. For each matched pair whose
    appearance differs — font, size, bold/italic/serif/monospace/superscript,
    colour, or position — a :class:`StyleChange` is emitted.
    """
    orig = [span for span in original_spans if str(getattr(span, "text", "")).strip()]
    mod = [span for span in modified_spans if str(getattr(span, "text", "")).strip()]
    if len(orig) > max_spans:
        orig = orig[:max_spans]
    if len(mod) > max_spans:
        mod = mod[:max_spans]

    keys_a = [_span_text_key(str(span.text)) for span in orig]
    keys_b = [_span_text_key(str(span.text)) for span in mod]
    alignment = lcs_dp(keys_a, keys_b).alignment

    changes: List[StyleChange] = []
    # Walk the alignment keeping parallel cursors into both span lists.
    cursor_a = cursor_b = 0
    for step in alignment:
        if step.get("op") == "match":
            span_a = orig[cursor_a]
            span_b = mod[cursor_b]
            delta = _style_delta(span_a, span_b)
            if delta:
                changes.append(
                    StyleChange(
                        text=str(span_a.text).strip(),
                        page=int(getattr(span_a, "page", 0) or 0),
                        changes=delta,
                    )
                )
            cursor_a += 1
            cursor_b += 1
        elif step.get("op") == "delete":
            cursor_a += 1
        else:  # insert
            cursor_b += 1
    return changes


def _style_delta(span_a: Any, span_b: Any) -> Dict[str, Any]:
    """Return the appearance differences between two spans (empty if equal)."""
    delta: Dict[str, Any] = {}

    font_a = str(getattr(span_a, "font", "") or "")
    font_b = str(getattr(span_b, "font", "") or "")
    if font_a != font_b:
        delta["font"] = {"original": font_a, "modified": font_b}

    size_a = float(getattr(span_a, "size", 0.0) or 0.0)
    size_b = float(getattr(span_b, "size", 0.0) or 0.0)
    if abs(size_a - size_b) > 0.01:
        delta["size"] = {
            "original": round(size_a, 2),
            "modified": round(size_b, 2),
        }

    color_a = getattr(span_a, "color_hex", None)
    color_b = getattr(span_b, "color_hex", None)
    if color_a != color_b:
        delta["color"] = {"original": color_a, "modified": color_b}

    style_flags: Dict[str, Any] = {}
    for flag in ("bold", "italic", "serif", "monospace", "superscript"):
        before = bool(getattr(span_a, flag, False))
        after = bool(getattr(span_b, flag, False))
        if before != after:
            style_flags[flag] = {"original": before, "modified": after}
    if style_flags:
        delta["style"] = style_flags

    bbox_a = getattr(span_a, "bbox", None)
    bbox_b = getattr(span_b, "bbox", None)
    if bbox_a and bbox_b and len(bbox_a) >= 4 and len(bbox_b) >= 4:
        dx = round(float(bbox_b[0]) - float(bbox_a[0]), 2)
        dy = round(float(bbox_b[1]) - float(bbox_a[1]), 2)
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            delta["position"] = {
                "dx": dx,
                "dy": dy,
                "original_bbox": list(bbox_a),
                "modified_bbox": list(bbox_b),
            }
    return delta


# --------------------------------------------------------------------------- #
# Combined entry point
# --------------------------------------------------------------------------- #
def _text_of(source: Any) -> str:
    """Pull the text out of a ``PdfMetadataResult``-like object or a string."""
    if isinstance(source, str):
        return source
    if hasattr(source, "pages"):
        return "\n".join(
            page.text for page in source.pages if getattr(page, "text", "")
        )
    if hasattr(source, "full_text"):
        return str(source.full_text)
    raise TypeError(
        "detect_document_changes expects text, an ExtractionResult or a "
        "PdfMetadataResult."
    )


def _spans_of(source: Any) -> List[Any]:
    if hasattr(source, "all_spans"):
        try:
            return list(source.all_spans())
        except Exception:  # pragma: no cover - defensive
            return []
    return []


def detect_document_changes(
    original: Any,
    modified: Any,
    *,
    compare_metadata: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_char_ops: int = DEFAULT_MAX_CHAR_OPS,
) -> ChangeReport:
    """Full change report between two documents.

    ``original`` / ``modified`` may each be a plain string, an
    :class:`~app.services.extraction.ExtractionResult`, or a
    :class:`~app.services.pdf_metadata.PdfMetadataResult`. When both sides carry
    span metadata *and* ``compare_metadata`` is true, typographic changes are
    included alongside the text changes.
    """
    original_text = _text_of(original)
    modified_text = _text_of(modified)

    report = detect_text_changes(
        original_text,
        modified_text,
        max_tokens=max_tokens,
        max_char_ops=max_char_ops,
    )

    if compare_metadata:
        spans_a = _spans_of(original)
        spans_b = _spans_of(modified)
        if spans_a or spans_b:
            report.style_changes = detect_style_changes(spans_a, spans_b)
            report.algorithms_executed.append("detect_style_changes")
            if report.style_changes and not report.hunks:
                # Identical text but different typography: still a change.
                report.changed = True
                report.summary["metadata_only"] = True
        else:
            report.warnings.append(
                "No span metadata was available for one or both documents; "
                "only text changes were compared."
            )

    report.summary["style_change_count"] = len(report.style_changes)
    return report


__all__ = [
    "DEFAULT_MAX_CHAR_OPS",
    "DEFAULT_MAX_HUNKS",
    "DEFAULT_MAX_TOKENS",
    "ChangeReport",
    "StyleChange",
    "TextChangeHunk",
    "detect_document_changes",
    "detect_style_changes",
    "detect_text_changes",
]
