"""Template-driven field extraction and validation.

How a field is found
--------------------
1. **Label search with KMP.** For every template field, its canonical name and
   each of its template aliases are searched in the extracted text with
   :func:`app.algorithms.kmp.kmp_search` — the same O(n+m) exact matcher the DAA
   core provides. Searching (rather than regex-scanning) keeps the label lookup
   linear and produces a precise character offset, which becomes the field's
   *location* (page + line) in the report.
2. **Value capture.** The text following the label up to the end of that line is
   the candidate value; leading label punctuation (``:`` ``-`` ``|``) is trimmed.
   End-of-line capture is deliberate: on an invoice the next line is almost
   always another label, so the value cannot bleed into a neighbouring field.
3. **Pattern / type check.** If the template declares a ``validation_pattern``
   (e.g. ``\\b[A-Z]{2}\\d{4}\\b`` for an invoice number) the *matched substring*
   becomes the value, which strips OCR noise such as "Invoice No: INV1234 (copy)".
   Otherwise the declared ``data_type`` drives a type check (date parseable,
   amount numeric, email well-formed, identifier non-empty).

Alignment (bipartite)
---------------------
:func:`align_fields` runs the maximum-bipartite-matching model over
``{expected template fields} x {labels discovered in the document}``. This is the
Unit V integration: it assigns each discovered label to at most one expected
field and vice versa, so two similar labels cannot both claim the same expected
field (inflating the match count) and one label cannot be counted twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.algorithms.bipartite_matching import bipartite_match, build_matching_problem
from app.algorithms.kmp import kmp_search
from app.services import ServiceError
from app.services.extraction import ExtractionResult
from app.services.normalization import (
    collapse_whitespace,
    normalize_label,
    parse_date,
)

#: Value leading-separator stripper.
_LEADING_SEPARATORS = "^\\s*[:>=\\-\u2013\u2014|\\u2022\\t]"

#: Field statuses (mirrors ``app.models.models.FieldStatus``).
STATUS_PRESENT = "present"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"
STATUS_NOT_CHECKED = "not_checked"

#: Field sources (mirrors ``app.models.models.FieldSource``).
SOURCE_TEMPLATE_LABEL = "template_label"
SOURCE_REGEX = "regex"
SOURCE_KMP_LABEL = "kmp_label"
SOURCE_BIPARTITE_MATCH = "bipartite_match"
SOURCE_LAYOUT_ANALYSIS = "layout_analysis"
SOURCE_OCR = "ocr"

#: Email sanity pattern (used only when the template declares ``data_type=email``).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

#: A line of the form "Some Label: some value" in a template-less document.
_INLINE_LABEL_RE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 /#&_.()-]{1,48}?)\s*[:\u2231]\s*(?P<value>\S.*)$"
)


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #
@dataclass
class TemplateFieldSpec:
    """A template field in the shape the services want (decoupled from the ORM)."""

    name: str
    data_type: str = "text"
    required: bool = True
    validation_pattern: Optional[str] = None
    critical: bool = False
    aliases: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "required": self.required,
            "validation_pattern": self.validation_pattern,
            "critical": self.critical,
            "aliases": list(self.aliases),
        }


@dataclass
class TemplateSpec:
    """A template in the shape the services want."""

    name: str
    category: str = "custom"
    required_fields: Tuple[str, ...] = ()
    optional_fields: Tuple[str, ...] = ()
    critical_fields: Tuple[str, ...] = ()
    expected_sections: Tuple[str, ...] = ()
    section_order: Tuple[str, ...] = ()
    aliases: Dict[str, List[str]] = field(default_factory=dict)
    fields: Tuple[TemplateFieldSpec, ...] = ()

    @property
    def critical_set(self) -> set:
        return set(name.lower() for name in self.critical_fields)

    @property
    def required_set(self) -> set:
        if self.required_fields:
            return set(name.lower() for name in self.required_fields)
        return {spec.name.lower() for spec in self.fields if spec.required}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "critical_fields": list(self.critical_fields),
            "expected_sections": list(self.expected_sections),
            "aliases": dict(self.aliases),
            "fields": [spec.to_dict() for spec in self.fields],
        }


def _spec_field_from_raw(
    item: Any, template_aliases: Dict[str, List[str]]
) -> Optional[TemplateFieldSpec]:
    """Adapt a raw template field entry (dict or positional tuple) to a spec.

    ``DEFAULT_TEMPLATES`` declares fields positionally
    ``(name, data_type, required, validation_pattern, critical, position)`` for
    compactness, while API payloads declare them as objects; both are accepted.
    """
    if isinstance(item, dict):
        name = item.get("name", "")
        if not name:
            return None
        return TemplateFieldSpec(
            name=name,
            data_type=item.get("data_type", "text"),
            required=bool(item.get("required", True)),
            validation_pattern=item.get("validation_pattern"),
            critical=bool(item.get("critical", False)),
            aliases=tuple(template_aliases.get(name, ())),
        )
    if isinstance(item, (list, tuple)) and item:
        name = str(item[0])
        if not name:
            return None
        return TemplateFieldSpec(
            name=name,
            data_type=str(item[1]) if len(item) > 1 else "text",
            required=bool(item[2]) if len(item) > 2 else True,
            validation_pattern=item[3] if len(item) > 3 else None,
            critical=bool(item[4]) if len(item) > 4 else False,
            aliases=tuple(template_aliases.get(name, ())),
        )
    return None


def template_spec_from(template: Any) -> TemplateSpec:
    """Adapt an ORM ``DocumentTemplate`` (or a plain dict) to a :class:`TemplateSpec`."""
    if template is None:
        return TemplateSpec(name="custom")
    if isinstance(template, dict):
        raw_fields = template.get("fields") or []
        aliases: Dict[str, List[str]] = {
            key: list(value) for key, value in (template.get("aliases") or {}).items()
        }
        fields = tuple(
            spec
            for spec in (
                _spec_field_from_raw(item, aliases) for item in raw_fields
            )
            if spec is not None
        )
        return TemplateSpec(
            name=template.get("name", "custom"),
            category=template.get("category", "custom"),
            required_fields=tuple(template.get("required_fields") or ()),
            optional_fields=tuple(template.get("optional_fields") or ()),
            critical_fields=tuple(template.get("critical_fields") or ()),
            expected_sections=tuple(template.get("expected_sections") or ()),
            section_order=tuple(template.get("section_order") or ()),
            aliases=aliases,
            fields=fields,
        )

    # ORM object.
    aliases: Dict[str, List[str]] = {}
    for key, value in (getattr(template, "aliases", None) or {}).items():
        aliases[key] = list(value) if isinstance(value, (list, tuple, set)) else [str(value)]
    fields = tuple(
        TemplateFieldSpec(
            name=field_def.name,
            data_type=field_def.data_type or "text",
            required=bool(field_def.required),
            validation_pattern=field_def.validation_pattern,
            critical=bool(field_def.critical),
            aliases=tuple(aliases.get(field_def.name, ())),
        )
        for field_def in getattr(template, "fields", []) or []
    )
    return TemplateSpec(
        name=getattr(template, "name", "custom"),
        category=getattr(template, "category", "custom"),
        required_fields=tuple(getattr(template, "required_fields", None) or ()),
        optional_fields=tuple(getattr(template, "optional_fields", None) or ()),
        critical_fields=tuple(getattr(template, "critical_fields", None) or ()),
        expected_sections=tuple(getattr(template, "expected_sections", None) or ()),
        section_order=tuple(getattr(template, "section_order", None) or ()),
        aliases=aliases,
        fields=fields,
    )


@dataclass
class FieldExtraction:
    """One extracted (and possibly validated) field."""

    field_name: str
    field_value: Optional[str]
    field_type: str
    status: str
    confidence: float
    source: str
    location: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)
    critical: bool = False
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "field_value": self.field_value,
            "field_type": self.field_type,
            "status": self.status,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "location": self.location,
            "notes": list(self.notes),
            "critical": self.critical,
            "required": self.required,
        }


@dataclass
class FieldValidationResult:
    """Aggregate outcome of the field stage."""

    fields: List[FieldExtraction] = field(default_factory=list)
    template_name: str = "custom"
    required_present: List[str] = field(default_factory=list)
    required_missing: List[str] = field(default_factory=list)
    invalid_fields: List[str] = field(default_factory=list)
    not_checked_fields: List[str] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)
    matching: Optional[Dict[str, Any]] = None
    document_labels: List[str] = field(default_factory=list)
    kmp_comparisons: int = 0
    notes: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_name": self.template_name,
            "fields": [item.to_dict() for item in self.fields],
            "required_present": list(self.required_present),
            "required_missing": list(self.required_missing),
            "invalid_fields": list(self.invalid_fields),
            "not_checked_fields": list(self.not_checked_fields),
            "critical_issues": list(self.critical_issues),
            "document_labels": list(self.document_labels),
            "matching": self.matching,
            "kmp_comparisons": self.kmp_comparisons,
            "notes": list(self.notes),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }

    def as_map(self) -> Dict[str, FieldExtraction]:
        return {item.field_name.lower(): item for item in self.fields}


# --------------------------------------------------------------------------- #
# Value checks
# --------------------------------------------------------------------------- #
def check_value_type(value: str, data_type: str) -> Tuple[bool, str]:
    """Return ``(ok, normalized_value)`` for ``value`` against ``data_type``."""
    cleaned = collapse_whitespace(value)
    kind = (data_type or "text").lower()
    if kind in {"date", "datetime"}:
        parsed = parse_date(cleaned)
        return (parsed is not None), (parsed or cleaned)
    if kind in {"amount", "number", "numeric", "currency", "float"}:
        candidate = cleaned
        candidate = re.sub(r"(?i)\b(INR|USD|EUR|GBP|AED|SAR|AUD|CAD)\b", "", candidate)
        candidate = candidate.replace(",", "").replace("₹", "").replace("$", "")
        candidate = candidate.replace("Rs", "").replace("rs", "").strip()
        try:
            float(candidate)
            return True, candidate
        except ValueError:
            return False, cleaned
    if kind == "email":
        return bool(_EMAIL_RE.match(cleaned)), cleaned
    if kind == "id":
        return bool(cleaned), cleaned
    # text / unknown
    return bool(cleaned), cleaned


def _apply_pattern(
    value: str, line: str, pattern: Optional[str]
) -> Tuple[Optional[str], bool, Optional[str]]:
    """Apply a template pattern.

    Returns ``(refined_value, matched, note)``. The pattern is searched in the
    captured value first and then in the whole line, so "Invoice No: INV1234
    (copy)" still yields ``INV1234``.

    A pattern the template author wrote with a capturing group does **not**
    truncate the value: the refined value is always the full match. Patterns such
    as ``\\d[\\d,]*(\\.\\d{1,2})?`` carry an optional group that legitimately
    matches ``.00``, and taking it would turn ``1,50,000.00`` into ``.00``.
    Template patterns should therefore be written to match exactly the value
    text they expect.
    """
    if not pattern:
        return None, False, None
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return None, False, f"Template pattern is invalid ({exc}); type check used."
    for source in (value, line):
        if not source:
            continue
        match = compiled.search(source)
        if match:
            return match.group(0).strip(), True, None
    return None, False, (
        f"Value {value!r} does not match the required pattern {pattern!r}."
    )


# --------------------------------------------------------------------------- #
# KMP label search
# --------------------------------------------------------------------------- #
def _search_variants(label: str) -> List[str]:
    """The literal strings to search for one label.

    ``"total_amount"`` never appears in a document (documents write
    "Total Amount"), so the underscore variant is searched alongside the
    original. Both are exact literals, which keeps KMP's linear guarantee.
    """
    variants = [label]
    spaced = label.replace("_", " ")
    if spaced != label:
        variants.append(spaced)
    return variants


def _is_word_boundary_match(text: str, index: int, label: str) -> bool:
    """True when the match at ``index`` is a whole label, not a word fragment.

    "to" inside "Total Amount" is *not* a buyer-label match; "total" at the
    start of "Total Amount" is. Without this check short aliases hijack long
    labels and the captured value becomes garbage.
    """
    if index > 0 and text[index - 1].isalnum():
        return False
    end = index + len(label)
    return end >= len(text) or not text[end].isalnum()


@dataclass
class LabelHit:
    """One label occurrence found by KMP."""

    page: int
    line: int
    char_index: int
    label: str
    matched_label: str
    case_insensitive: bool
    comparisons: int


def find_label(
    text: str, page: int, labels: Sequence[str]
) -> Tuple[Optional[LabelHit], int]:
    """Find the first occurrence of any label in ``text`` using KMP.

    Returns ``(hit, comparisons)``. Labels are tried **longest first**, so the
    canonical ``"Date of Birth"`` wins over the short alias ``"Date"``, and each
    hit must sit on a word boundary. The exact-case search runs first; a
    case-insensitive search is only attempted when it is length-safe
    (``str.lower()`` may change the length of some Unicode characters, which
    would invalidate the returned offsets).
    """
    comparisons = 0
    if not text or not labels:
        return None, comparisons

    ordered = sorted(
        {variant for label in labels for variant in _search_variants(label)},
        key=lambda item: (-len(item), item),
    )

    def scan(haystack: str, case_insensitive: bool) -> Optional[LabelHit]:
        nonlocal comparisons
        for label in ordered:
            result = kmp_search(haystack, label)
            comparisons += result.comparisons
            for index in result.matches:
                if _is_word_boundary_match(haystack, index, label):
                    return _hit(
                        text, page, index, label, label, case_insensitive,
                        comparisons,
                    )
        return None

    hit = scan(text, False)
    if hit is not None:
        return hit, comparisons

    lowered = text.lower()
    if len(lowered) == len(text):
        hit = scan(lowered, True)
        if hit is not None:
            return hit, comparisons
    return None, comparisons


def _hit(
    text: str,
    page: int,
    index: int,
    label: str,
    matched_label: str,
    case_insensitive: bool,
    comparisons: int,
) -> LabelHit:
    line = text.count("\n", 0, index) + 1
    return LabelHit(
        page=page,
        line=line,
        char_index=index,
        label=label,
        matched_label=matched_label,
        case_insensitive=case_insensitive,
        comparisons=comparisons,
    )


def _value_after_label(text: str, index: int, label: str) -> Tuple[str, str]:
    """Return ``(value, line)`` for the label match starting at ``index``."""
    start = index + len(label)
    end = text.find("\n", start)
    if end == -1:
        end = len(text)
    line = text[start:end]
    value = re.sub(_LEADING_SEPARATORS, "", line).strip()
    return value, line.strip()


# --------------------------------------------------------------------------- #
# Generic label:value scan (template-less documents)
# --------------------------------------------------------------------------- #
def scan_inline_labels(text: str) -> List[Dict[str, Any]]:
    """Collect ``Label: value`` pairs from a document with no template.

    This is what makes the ``custom`` template useful: the fields come from the
    document's *own* labels, so nothing is invented — every reported field is a
    line the document actually contains.
    """
    found: List[Dict[str, Any]] = []
    seen: set = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        match = _INLINE_LABEL_RE.match(raw_line)
        if not match:
            continue
        label = normalize_label(match.group("label"))
        value = match.group("value").strip()
        if not label or not value or label in seen:
            continue
        seen.add(label)
        found.append({"label": label, "value": value, "line": line_number})
        if len(found) >= 60:
            break
    return found


def _extract_academic_metadata(text: str) -> Dict[str, str]:
    """Heuristic extraction for research papers, preprints and academic articles."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title_lines: List[str] = []
    author_lines: List[str] = []
    dept_lines: List[str] = []

    state = "title"
    for ln in lines:
        if re.search(r"^\s*Abstract\b", ln, re.I):
            break
        if state == "title":
            if re.search(r"(?i)\b(Prof\.?|Dr\.?|Mr\.?|Ms\.?|Department|Faculty|University|Institute)\b", ln):
                state = "authors"
                if re.search(r"(?i)\b(Prof\.?|Dr\.?|Mr\.?|Ms\.?)\b", ln):
                    author_lines.append(ln)
            else:
                title_lines.append(ln)
        elif state == "authors":
            if re.search(r"(?i)\b(Department|Institute|Technology|University|College|Division)\b", ln):
                if ln not in dept_lines:
                    dept_lines.append(ln)
            elif re.search(r"(?i)\b(Pune|Maharashtra|India|USA|UK|Canada|Germany|France)\b", ln):
                if ln not in dept_lines:
                    dept_lines.append(ln)
            elif "@" not in ln:
                if ln not in author_lines:
                    author_lines.append(ln)

    title = " ".join(title_lines).strip()
    authors = ", ".join(author_lines).strip()
    dept = ", ".join(dept_lines).strip()

    ab_match = re.search(
        r"Abstract[—\-\s:](.*?)(?=\b(Index Terms|Keywords|I\.\s*INTRODUCTION|1\.\s*Introduction)\b|$)",
        text,
        re.DOTALL | re.I,
    )
    abstract = " ".join(ab_match.group(1).split()) if ab_match else ""

    kw_match = re.search(
        r"(?:Index Terms|Keywords)[—\-\s:](.*?)(?=\b(I\.\s*INTRODUCTION|1\.\s*Introduction)\b|$)",
        text,
        re.DOTALL | re.I,
    )
    keywords = " ".join(kw_match.group(1).split()) if kw_match else ""

    emails = list(dict.fromkeys(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)))

    c_match = re.search(
        r"(?i)(?:[IVXLCDM]+\.|\d+\.)?\s*CONCLU[A-Z\s]*\n(.*?)(?=\n\s*(?:[IVXLCDM]+\.|\d+\.)?\s*REF|\Z)",
        text,
        re.DOTALL,
    )
    conclusion = " ".join(c_match.group(1).split())[:500] if c_match else ""

    conf_match = re.search(r"(?i)\b(CAISAIS[-\s]?2026|[A-Z]{3,10}\s+20\d\d|IEEE|ACM|Springer|Conference)\b", text)
    conference = conf_match.group(0).strip() if conf_match else ""

    return {
        "title": title,
        "authors": authors,
        "author": authors,
        "department": dept,
        "abstract": abstract,
        "summary": abstract,
        "keywords": keywords,
        "email": ", ".join(emails[:5]),
        "conclusion": conclusion,
        "conference": conference,
    }


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def extract_and_validate_fields(
    extraction: ExtractionResult,
    template: Any,
    *,
    alignment_threshold: float = 0.6,
) -> FieldValidationResult:
    """Extract every template field from ``extraction`` and validate it."""
    import time

    started = time.perf_counter()
    spec = template_spec_from(template)
    result = FieldValidationResult(template_name=spec.name)
    texts = [(page.page, page.text) for page in extraction.pages if page.text.strip()]
    if not texts and extraction.full_text.strip():
        texts = [(1, extraction.full_text)]

    academic_meta: Dict[str, str] = {}
    if (
        spec.name in {"research_paper", "general_report"}
        or spec.category in {"academic", "report"}
        or re.search(r"\bAbstract[—\-\s:]", extraction.full_text)
    ):
        academic_meta = _extract_academic_metadata(extraction.full_text)

    if not spec.fields:
        # ---- Template-less path: report the document's own labels ---------- #
        for item in scan_inline_labels(extraction.full_text):
            result.fields.append(
                FieldExtraction(
                    field_name=item["label"],
                    field_value=item["value"],
                    field_type="text",
                    status=STATUS_NOT_CHECKED,
                    confidence=0.6,
                    source=SOURCE_TEMPLATE_LABEL,
                    location={"page": 1, "line": item["line"], "label": item["label"]},
                    notes=["No template selected: no required fields were checked."],
                    required=False,
                )
            )
        result.not_checked_fields = [item.field_name for item in result.fields]
        result.notes.append(
            "Template 'custom' declares no required fields; document labels were "
            "collected for reporting only."
        )
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    # ---- Template path ---------------------------------------------------- #
    # Pass 1: locate every field's label. The *document's* labels collected here
    # (not the template's field names) are what the bipartite matching aligns
    # below — aligning the template against itself would be a tautology.
    document_labels: List[str] = []
    discovered: List[Dict[str, Any]] = []
    for spec_field in spec.fields:
        labels = [spec_field.name, *spec_field.aliases]
        best_hit: Optional[LabelHit] = None
        best_value = ""
        best_line = ""
        for page_number, page_text in texts:
            hit, comparisons = find_label(page_text, page_number, labels)
            result.kmp_comparisons += comparisons
            if hit is None:
                continue
            value, line = _value_after_label(
                page_text, hit.char_index, hit.matched_label
            )
            if hit.matched_label not in document_labels:
                document_labels.append(hit.matched_label)
            if value:
                best_hit = hit
                best_value = value
                best_line = line
                break
            if best_hit is None:
                best_hit, best_value, best_line = hit, value, line

        discovered.append(
            {
                "spec": spec_field,
                "hit": best_hit,
                "value": best_value,
                "line": best_line,
            }
        )

    if not document_labels:
        # No template label matched: fall back to the document's own labels so
        # the matching step still has a right-hand side.
        for item in scan_inline_labels(extraction.full_text):
            if item["label"] not in document_labels:
                document_labels.append(item["label"])
        result.notes.append(
            "No template label matched the document directly; the bipartite "
            "alignment used labels parsed from the document text."
        )

    matching = align_fields(spec, document_labels, alignment_threshold)
    result.matching = matching
    result.document_labels = document_labels

    for item in discovered:
        spec_field: TemplateFieldSpec = item["spec"]
        hit: Optional[LabelHit] = item["hit"]
        value: str = item["value"]
        line: str = item["line"]
        notes: List[str] = []

        source = SOURCE_KMP_LABEL
        if hit is None:
            fallback_val = academic_meta.get(spec_field.name)
            if fallback_val:
                value = fallback_val
                hit = LabelHit(
                    page=1,
                    line=1,
                    char_index=0,
                    label=spec_field.name,
                    matched_label=spec_field.name,
                    case_insensitive=False,
                    comparisons=0,
                )
                source = SOURCE_LAYOUT_ANALYSIS
                notes.append("Extracted using academic document layout heuristics.")
            else:
                result.fields.append(
                    FieldExtraction(
                        field_name=spec_field.name,
                        field_value=None,
                        field_type=spec_field.data_type,
                        status=STATUS_MISSING,
                        confidence=0.0,
                        source=SOURCE_KMP_LABEL,
                        location=None,
                        notes=[f"No label found for {spec_field.name!r} "
                              f"(searched {len([spec_field.name, *spec_field.aliases])} variants)."],
                        critical=spec_field.critical,
                        required=spec_field.required,
                    )
                )
                continue
        elif spec_field.name in {"abstract", "summary"} and academic_meta.get(spec_field.name) and len(value) < 120:
            value = academic_meta[spec_field.name]
            notes.append("Extended multi-line abstract captured.")

        if hit.case_insensitive:
            notes.append("Label matched case-insensitively.")
        location = {"page": hit.page, "line": hit.line, "label": hit.matched_label}

        if not value:
            fallback_val = academic_meta.get(spec_field.name)
            if fallback_val:
                value = fallback_val
                source = SOURCE_LAYOUT_ANALYSIS
                notes.append("Extracted using academic document layout heuristics.")
            else:
                result.fields.append(
                    FieldExtraction(
                        field_name=spec_field.name,
                        field_value=None,
                        field_type=spec_field.data_type,
                        status=STATUS_MISSING,
                        confidence=0.5,
                        source=source,
                        location=location,
                        notes=["Label found but no value on the same line."],
                        critical=spec_field.critical,
                        required=spec_field.required,
                    )
                )
                continue

        refined, matched, pattern_note = _apply_pattern(value, line, spec_field.validation_pattern)
        if matched:
            value = refined or value
            source = SOURCE_REGEX
        elif pattern_note:
            notes.append(pattern_note)

        ok, checked = check_value_type(value, spec_field.data_type)
        if not ok:
            notes.append(f"Value {value!r} is not a valid {spec_field.data_type}.")
        status = STATUS_PRESENT if ok else STATUS_INVALID
        confidence = 0.95 if matched else (0.9 if ok else 0.6)

        result.fields.append(
            FieldExtraction(
                field_name=spec_field.name,
                field_value=value,
                field_type=spec_field.data_type,
                status=status,
                confidence=confidence,
                source=source,
                location=location,
                notes=notes,
                critical=spec_field.critical,
                required=spec_field.required,
            )
        )

    # ---- Aggregate -------------------------------------------------------- #
    for item in result.fields:
        if item.status == STATUS_MISSING and item.required:
            result.required_missing.append(item.field_name)
        elif item.status == STATUS_PRESENT:
            result.required_present.append(item.field_name)
        if item.status == STATUS_INVALID:
            result.invalid_fields.append(item.field_name)
        if item.status == STATUS_NOT_CHECKED:
            result.not_checked_fields.append(item.field_name)
        if item.critical and item.status in {STATUS_MISSING, STATUS_INVALID}:
            result.critical_issues.append(item.field_name)

    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result


# --------------------------------------------------------------------------- #
# Bipartite alignment (Unit V)
# --------------------------------------------------------------------------- #
def align_fields(
    spec: TemplateSpec,
    discovered_labels: Sequence[str],
    threshold: float = 0.6,
) -> Dict[str, Any]:
    """Align template fields to discovered labels via maximum bipartite matching.

    Returns the matching result plus the derived per-field source, which the
    pipeline writes into ``extracted_fields.source`` as ``"bipartite_match"``
    for fields whose label was confirmed by the matching rather than by a direct
    KMP hit.
    """
    expected = [
        {"name": spec_field.name, "data_type": spec_field.data_type}
        for spec_field in spec.fields
    ]
    extracted = [{"label": label} for label in discovered_labels]
    problem = build_matching_problem(
        expected, extracted, similarity_threshold=threshold, aliases=spec.aliases
    )
    matching = bipartite_match(problem)
    matched_pairs = sorted(matching.matching)
    unmatched_expected = list(matching.unmatched_expected)
    return {
        "algorithm": "bipartite_match (Edmonds-Karp)",
        "matching_size": matching.max_matching_size,
        "pairs": [{"expected": left, "extracted": right} for left, right in matched_pairs],
        "unmatched_expected": unmatched_expected,
        "unmatched_extracted": list(matching.unmatched_extracted),
        "edge_rules": {
            rule: sum(1 for edge in matching.edge_details if edge.get("rule") == rule)
            for rule in {"exact_label", "alias", "similar_label"}
        },
        "augmenting_paths": len(matching.augmenting_paths),
        "elapsed_ns": matching.elapsed_ns,
    }


def apply_alignment_sources(result: FieldValidationResult) -> FieldValidationResult:
    """Mark fields confirmed by the bipartite matching with that source."""
    matching = result.matching or {}
    confirmed = {pair["expected"] for pair in matching.get("pairs", [])}
    for item in result.fields:
        if item.field_name in confirmed and item.source == SOURCE_KMP_LABEL:
            item.source = SOURCE_BIPARTITE_MATCH
    return result


def require_template(template: Any, name: Optional[str] = None) -> Any:
    """Return ``template`` or raise :class:`ServiceError` (defensive helper)."""
    if template is None:
        label = name or "<unknown>"
        raise ServiceError(
            f"Template {label!r} was not found and is required by this operation.",
            "template_not_found",
        )
    return template


def iter_field_names(fields: Iterable[FieldExtraction]) -> List[str]:
    """Return the field names of ``fields`` (helper for the API layer)."""
    return [item.field_name for item in fields]
