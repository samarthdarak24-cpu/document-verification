"""Unit tests for :mod:`app.services.document_change_detector`.

The point of these tests is twofold: that the change analysis is *correct*, and
that it is built on DocuTrace's own algorithms. The latter is asserted
explicitly (``algorithms_executed`` must name ``lcs_dp`` and ``edit_distance``,
and the module must not import :mod:`difflib`), because replacing a hand-rolled
LCS/edit-distance with a standard-library shortcut is exactly the regression this
module exists to prevent.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.services import document_change_detector as dcd
from app.services.document_change_detector import (
    ChangeReport,
    detect_document_changes,
    detect_style_changes,
    detect_text_changes,
)
from app.services.pdf_metadata import FLAG_BOLD, TextSpan, extract_pdf_metadata


def _span(
    text: str,
    *,
    font: str = "Helvetica",
    size: float = 10.0,
    bold: bool = False,
    color_hex: str = "#000000",
    bbox: list[float] | None = None,
    page: int = 1,
) -> TextSpan:
    return TextSpan(
        text=text,
        font=font,
        size=size,
        flags=FLAG_BOLD if bold else 0,
        bold=bold,
        italic=False,
        serif=False,
        monospace=False,
        superscript=False,
        color_hex=color_hex,
        color_rgb=(0, 0, 0),
        bbox=bbox or [0.0, 0.0, 10.0, 10.0],
        origin=[0.0, 0.0],
        page=page,
        block=0,
        line=0,
    )


# --------------------------------------------------------------------------- #
# Provenance: the module must use the project's own algorithms
# --------------------------------------------------------------------------- #
class TestAlgorithmProvenance:
    def test_no_difflib_import(self):
        # The docstring *mentions* difflib (explaining why it is not used), so
        # the check parses the module's AST for real import statements rather
        # than grepping for the word.
        tree = ast.parse(inspect.getsource(dcd))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "difflib" not in imported
        assert "app.algorithms.lcs" in {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }

    def test_algorithms_are_reported(self):
        report = detect_text_changes("a b c", "a b d")
        assert "lcs_dp" in report.algorithms_executed
        assert "edit_distance" in report.algorithms_executed
        assert "tokenize" in report.algorithms_executed


# --------------------------------------------------------------------------- #
# Text change detection
# --------------------------------------------------------------------------- #
class TestTextChanges:
    def test_identical_text_is_not_changed(self):
        report = detect_text_changes("the quick brown fox", "the quick brown fox")
        assert report.changed is False
        assert report.verdict() == "identical"
        assert report.hunks == []
        assert report.text_similarity == pytest.approx(1.0)
        assert report.edit_similarity == pytest.approx(1.0)

    def test_single_digit_change_is_isolated(self):
        report = detect_text_changes(
            "Registration Number: MH/2024/008421",
            "Registration Number: MH/2024/008422",
        )
        assert report.changed is True
        replaces = [h for h in report.hunks if h.type == "replace"]
        assert len(replaces) == 1
        hunk = replaces[0]
        assert hunk.removed_text == "008421"
        assert hunk.added_text == "008422"
        assert hunk.char_edit_distance == 1
        # The character-level script must pinpoint the digit, not the word.
        subs = [op for op in hunk.char_operations if op["op"] == "substitute"]
        assert len(subs) == 1
        assert subs[0]["old"] == "1" and subs[0]["new"] == "2"

    def test_insertion_is_detected(self):
        report = detect_text_changes("alpha gamma", "alpha beta gamma")
        assert report.verdict() == "content_added"
        assert any(h.type == "insert" for h in report.hunks)
        assert report.added_tokens >= 1

    def test_deletion_is_detected(self):
        report = detect_text_changes("alpha beta gamma", "alpha gamma")
        assert report.verdict() == "content_removed"
        assert any(h.type == "delete" for h in report.hunks)
        assert report.removed_tokens >= 1

    def test_replacement_is_detected(self):
        report = detect_text_changes("status active", "status revoked")
        assert report.verdict() == "content_replaced"
        assert any(h.type == "replace" for h in report.hunks)

    def test_identical_empty_texts(self):
        report = detect_text_changes("", "")
        assert report.changed is False
        assert report.text_similarity == pytest.approx(1.0)

    def test_lcs_length_and_token_counts(self):
        report = detect_text_changes("one two three", "one two four")
        assert report.lcs_length == 2
        assert report.unchanged_tokens == 2
        assert report.original_token_count == 3
        assert report.modified_token_count == 3

    def test_token_truncation_is_recorded_not_silent(self):
        report = detect_text_changes("a b c d e f", "a b c d e g", max_tokens=3)
        assert any("truncated" in warning.lower() for warning in report.warnings)
        assert report.summary["truncated_tokens"] is True

    def test_hunk_cap_is_recorded(self):
        # Changes must be *separated* by unchanged tokens, otherwise the LCS
        # alignment merges them into a single contiguous hunk.
        original = " ".join(f"a{i} x" for i in range(10))
        modified = " ".join(f"b{i} x" for i in range(10))
        full = detect_text_changes(original, modified)
        assert len(full.hunks) == 10
        capped = detect_text_changes(original, modified, max_hunks=3)
        assert len(capped.hunks) == 3
        assert capped.summary["truncated_hunks"] is True

    def test_to_dict_is_json_safe(self):
        import json

        payload = detect_text_changes("a b", "a c").to_dict()
        json.dumps(payload)
        assert "verdict" in payload and "hunks" in payload


# --------------------------------------------------------------------------- #
# Typography change detection
# --------------------------------------------------------------------------- #
class TestStyleChanges:
    def test_identical_spans_produce_no_change(self):
        spans = [_span("Registration Number: MH/2024/008421")]
        assert detect_style_changes(spans, spans) == []

    def test_font_and_size_change_is_reported(self):
        original = [_span("Registration Number: MH/2024/008421")]
        modified = [
            _span("Registration Number: MH/2024/008421", font="Courier", size=12.0)
        ]
        changes = detect_style_changes(original, modified)
        assert len(changes) == 1
        delta = changes[0].changes
        assert delta["font"] == {"original": "Helvetica", "modified": "Courier"}
        assert delta["size"] == {"original": 10.0, "modified": 12.0}

    def test_colour_and_bold_change_is_reported(self):
        original = [_span("Status: Active")]
        modified = [_span("Status: Active", bold=True, color_hex="#ff0000")]
        delta = detect_style_changes(original, modified)[0].changes
        assert delta["color"] == {"original": "#000000", "modified": "#ff0000"}
        assert delta["style"]["bold"] == {"original": False, "modified": True}

    def test_position_shift_is_reported(self):
        original = [_span("Valid Until: 2027-04-11", bbox=[72.0, 159.0, 174.0, 173.0])]
        modified = [_span("Valid Until: 2027-04-11", bbox=[72.0, 145.0, 174.0, 159.0])]
        delta = detect_style_changes(original, modified)[0].changes
        assert delta["position"]["dx"] == 0.0
        assert delta["position"]["dy"] == -14.0

    def test_unchanged_spans_are_skipped(self):
        original = [_span("Header"), _span("Registration Number: MH/2024/008421")]
        modified = [_span("Header"), _span("Registration Number: MH/2024/008421", size=9.0)]
        changes = detect_style_changes(original, modified)
        assert len(changes) == 1
        assert changes[0].text == "Registration Number: MH/2024/008421"

    def test_blank_spans_are_ignored(self):
        assert detect_style_changes([_span("   ")], [_span("   ")]) == []


# --------------------------------------------------------------------------- #
# Combined document change detection
# --------------------------------------------------------------------------- #
class TestDocumentChanges:
    def test_metadata_only_change_verdict(self):
        # Identical text, different typography: a change that a text-only diff
        # would report as "no difference".
        original = [_span("Status: Active")]
        modified = [_span("Status: Active", bold=True)]

        class _Fake:
            def __init__(self, spans):
                self._spans = spans
                self.pages = []

            def all_spans(self):
                return self._spans

        report = detect_document_changes(_Fake(original), _Fake(modified))
        assert report.changed is True
        assert report.hunks == []
        assert report.style_changes
        assert report.verdict() == "metadata_only_change"

    def test_text_change_without_metadata_warns(self):
        report = detect_document_changes("a b c", "a b d")
        assert report.changed is True
        assert any("span metadata" in w for w in report.warnings)

    def test_accepts_plain_strings(self):
        report = detect_document_changes("one two", "one three")
        assert isinstance(report, ChangeReport)
        assert report.changed is True

    def test_compare_metadata_can_be_disabled(self):
        original = [_span("Status: Active")]
        modified = [_span("Status: Active", bold=True)]

        class _Fake:
            def __init__(self, spans):
                self._spans = spans
                self.pages = []

            def all_spans(self):
                return self._spans

        report = detect_document_changes(
            _Fake(original), _Fake(modified), compare_metadata=False
        )
        assert report.style_changes == []
        assert report.changed is False


# --------------------------------------------------------------------------- #
# End-to-end over generated PDFs
# --------------------------------------------------------------------------- #
class TestPdfRoundTrip:
    def test_identical_pdfs_are_identical(self, tmp_pdf):
        lines = ["Registration Number: MH/2024/008421", "Status: Active"]
        a = extract_pdf_metadata(tmp_pdf("a.pdf", "Certificate", lines))
        b = extract_pdf_metadata(tmp_pdf("b.pdf", "Certificate", lines))
        report = detect_document_changes(a, b)
        assert report.changed is False
        assert report.verdict() == "identical"

    def test_changed_field_is_detected_in_pdfs(self, tmp_pdf):
        a = extract_pdf_metadata(
            tmp_pdf("a.pdf", "Certificate", ["Registration Number: MH/2024/008421"])
        )
        b = extract_pdf_metadata(
            tmp_pdf("b.pdf", "Certificate", ["Registration Number: MH/2024/008422"])
        )
        report = detect_document_changes(a, b)
        assert report.changed is True
        replaces = [h for h in report.hunks if h.type == "replace"]
        assert replaces
        assert any(h.char_edit_distance == 1 for h in replaces)

    def test_removed_line_shifts_following_spans(self, tmp_pdf):
        a = extract_pdf_metadata(
            tmp_pdf("a.pdf", "Certificate", ["Date of Issue: 2024-04-12", "Status: Active"])
        )
        b = extract_pdf_metadata(tmp_pdf("b.pdf", "Certificate", ["Status: Active"]))
        report = detect_document_changes(a, b)
        assert report.changed is True
        # The surviving line moved up, which the layout comparison must catch.
        assert any(
            "position" in change.changes for change in report.style_changes
        )
