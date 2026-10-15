"""Deterministic verification rule engine (rules R001..R008).

Design contract
---------------
* **Deterministic.** The same inputs always produce the same findings, the same
  outcome and the same recommendation. No randomness, no model inference, no
  clock-dependent behaviour.
* **Separate status dimensions.** ``validation_status`` (are the fields present
  and well-formed?), ``duplicate_status`` (is there a twin document?) and
  ``review_recommendation`` (what should a human do?) are computed and stored
  independently. Collapsing them into one number is how verification systems
  start lying; the headline ``outcome`` is then derived from all three.
* **Explainable.** Every firing rule appends a human-readable message and a
  machine-readable ``details_json`` payload, and ``explanation`` is the joined
  narrative. There is no hidden rule and no rule without a text explanation.
* **No authenticity claims.** DocuTrace never reports a document as
  "forged", "genuine" or "legally valid". The worst thing it says is that a
  rule fired and a human should look.

Rule table
----------
=====  ==========================================  =============================
Rule   Trigger                                     Severity
=====  ==========================================  =============================
R000   Every rule ran and nothing needed flagging  info
R001   A required field is missing                 critical
R002   A field value is invalid                     warning
R003   Byte-identical file hash                    critical
R004   Identical normalized text                    critical
R005   Near-duplicate above threshold              warning
R006   Critical field mismatch vs matched doc      critical
R007   Structural issue (reliable detection)       warning
R008   Low OCR confidence                           info
=====  ==========================================  =============================
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.models.models import (
    DuplicateStatus,
    FieldStatus,
    ReviewRecommendation,
    ValidationStatus,
    VerificationOutcome,
)

# Rule identifiers.
R000 = "R000"
R001 = "R001"
R002 = "R002"
R003 = "R003"
R004 = "R004"
R005 = "R005"
R006 = "R006"
R007 = "R007"
R008 = "R008"

RULE_DESCRIPTIONS: Dict[str, str] = {
    R000: "All template checks passed",
    R001: "Required field missing",
    R002: "Invalid field value",
    R003: "Exact (file-hash) duplicate",
    R004: "Normalized-text duplicate",
    R005: "Near-duplicate candidate",
    R006: "Critical field mismatch against a matched document",
    R007: "Structural issue",
    R008: "Low OCR confidence",
}


@dataclass
class Finding:
    """One rule result, ready to persist as a ``verification_findings`` row."""

    rule_id: str
    severity: str
    category: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass
class VerificationInputs:
    """Everything the rule engine needs (already computed by other services)."""

    processing_error: Optional[str] = None
    fields: Sequence[Any] = field(default_factory=list)
    required_missing: Sequence[str] = field(default_factory=list)
    invalid_fields: Sequence[str] = field(default_factory=list)
    critical_field_values: Dict[str, str] = field(default_factory=dict)
    duplicate_status: str = DuplicateStatus.UNIQUE
    duplicate_matches: Sequence[Dict[str, Any]] = field(default_factory=list)
    similarity_score: Optional[float] = None
    similarity_threshold: float = 0.85
    matcher_critical_mismatches: Sequence[Dict[str, Any]] = field(default_factory=list)
    structural_issues: Sequence[str] = field(default_factory=list)
    structure_uncertain: bool = False
    extraction_confidence: Optional[float] = None
    ocr_used: bool = False
    ocr_confidence_threshold: float = 0.75
    #: Non-fatal notes from the extractor (OCR unavailable, sparse/bitmap page,
    #: unreadable page). Surfaced through R008 so they reach the findings a
    #: reviewer actually reads, instead of being discarded.
    extraction_warnings: Sequence[str] = field(default_factory=list)
    template_name: str = "custom"
    thresholds: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing_error": self.processing_error,
            "field_count": len(self.fields),
            "required_missing": list(self.required_missing),
            "invalid_fields": list(self.invalid_fields),
            "duplicate_status": self.duplicate_status,
            "duplicate_matches": list(self.duplicate_matches),
            "similarity_score": self.similarity_score,
            "similarity_threshold": self.similarity_threshold,
            "structural_issues": list(self.structural_issues),
            "structure_uncertain": self.structure_uncertain,
            "extraction_confidence": self.extraction_confidence,
            "ocr_used": self.ocr_used,
            "template_name": self.template_name,
        }


@dataclass
class VerificationDecision:
    """The computed outcome of one verification."""

    outcome: str
    validation_status: str
    duplicate_status: str
    review_recommendation: str
    similarity_score: Optional[float]
    findings: List[Finding] = field(default_factory=list)
    rules_fired: List[str] = field(default_factory=list)
    explanation: str = ""
    thresholds: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "validation_status": self.validation_status,
            "duplicate_status": self.duplicate_status,
            "review_recommendation": self.review_recommendation,
            "similarity_score": self.similarity_score,
            "findings": [finding.to_dict() for finding in self.findings],
            "rules_fired": list(self.rules_fired),
            "explanation": self.explanation,
        }


# --------------------------------------------------------------------------- #
# Rule evaluation
# --------------------------------------------------------------------------- #
def _rule_r000(inputs: VerificationInputs) -> Finding:
    """Informational finding: the rule engine ran and raised nothing.

    A clean document is a *result*, not an absence of one. Emitting this row
    keeps an audit trail proving the checks were executed — previously a clean
    run stored no findings, so a reviewer could not distinguish "passed every
    check" from "the rules never ran".
    """
    return Finding(
        rule_id=R000,
        severity="info",
        category="validation",
        message=(
            f"All template checks for {inputs.template_name!r} passed; no "
            f"duplicate or near-duplicate candidate met the reporting thresholds."
        ),
        details={
            "template": inputs.template_name,
            "rules_evaluated": len(_RULES),
        },
    )


def _rule_r001(inputs: VerificationInputs) -> Optional[Finding]:
    missing = [name for name in inputs.required_missing if name]
    if not missing:
        return None
    return Finding(
        rule_id=R001,
        severity="critical",
        category="field_validation",
        message=(
            f"{len(missing)} required field(s) were not found in the document: "
            f"{', '.join(missing)}."
        ),
        details={"missing_fields": list(missing), "template": inputs.template_name},
    )


def _rule_r002(inputs: VerificationInputs) -> Optional[Finding]:
    invalid = [name for name in inputs.invalid_fields if name]
    if not invalid:
        return None
    return Finding(
        rule_id=R002,
        severity="warning",
        category="field_validation",
        message=(
            f"{len(invalid)} field value(s) failed their type or pattern check: "
            f"{', '.join(invalid)}."
        ),
        details={"invalid_fields": list(invalid), "template": inputs.template_name},
    )


def _rule_r003(inputs: VerificationInputs) -> Optional[Finding]:
    if inputs.duplicate_status != DuplicateStatus.EXACT:
        return None
    matched = _matched_documents(inputs)
    return Finding(
        rule_id=R003,
        severity="critical",
        category="duplicate",
        message=(
            "This file is byte-identical to a previously uploaded document "
            f"({', '.join(matched) or 'unknown'}) — the SHA-256 file fingerprint "
            "matches exactly."
        ),
        details={"matched_documents": matched, "stage": "file_hash"},
    )


def _rule_r004(inputs: VerificationInputs) -> Optional[Finding]:
    if inputs.duplicate_status != DuplicateStatus.CONTENT:
        return None
    matched = _matched_documents(inputs)
    return Finding(
        rule_id=R004,
        severity="critical",
        category="duplicate",
        message=(
            "This document's normalized text is identical to another uploaded "
            f"document ({', '.join(matched) or 'unknown'}): same content, "
            "different file bytes."
        ),
        details={"matched_documents": matched, "stage": "normalized_text_hash"},
    )


def _rule_r005(inputs: VerificationInputs) -> Optional[Finding]:
    if inputs.duplicate_status != DuplicateStatus.NEAR:
        return None
    matched = _matched_documents(inputs)
    target = ", ".join(matched) or "another document"
    score = inputs.similarity_score
    if score is not None:
        message = (
            f"This document is a near-duplicate of {target} (similarity "
            f"{score:.4f} >= threshold {inputs.similarity_threshold})."
        )
    else:
        message = f"This document is a near-duplicate of {target}."
    return Finding(
        rule_id=R005,
        severity="warning",
        category="duplicate",
        message=message,
        details={
            "matched_documents": matched,
            "similarity_score": score,
            "threshold": inputs.similarity_threshold,
        },
    )


def _rule_r006(inputs: VerificationInputs) -> Optional[Finding]:
    mismatches = [
        entry for entry in inputs.matcher_critical_mismatches
        if not entry.get("equal")
    ]
    if not mismatches:
        return None
    names = [str(entry.get("field", "?")) for entry in mismatches]
    return Finding(
        rule_id=R006,
        severity="critical",
        category="field_consistency",
        message=(
            f"{len(mismatches)} critical field(s) differ from the matched document: "
            f"{', '.join(names)}. The two documents are not the same record."
        ),
        details={"critical_mismatches": list(mismatches)},
    )


def _describe_issue(issue: Any) -> str:
    """Render one structural issue as a short human-readable phrase."""
    if isinstance(issue, dict):
        kind = str(issue.get("type", "issue")).replace("_", " ")
        detail = issue.get("detail") or issue.get("section") or issue.get("message")
        return f"{kind} ({detail})" if detail else kind
    return str(issue)


def _rule_r007(inputs: VerificationInputs) -> Optional[Finding]:
    if inputs.structure_uncertain:
        return None  # cannot claim structure problems from an unreadable document
    issues = [issue for issue in inputs.structural_issues if issue]
    if not issues:
        return None
    descriptions = [_describe_issue(issue) for issue in issues]
    return Finding(
        rule_id=R007,
        severity="warning",
        category="structure",
        message=(
            f"The document structure deviates from template "
            f"{inputs.template_name!r}: {'; '.join(descriptions)}."
        ),
        details={"issues": list(issues), "template": inputs.template_name},
    )


def _rule_r008(inputs: VerificationInputs) -> Optional[Finding]:
    confidence = inputs.extraction_confidence
    warnings = [w for w in (inputs.extraction_warnings or []) if w]
    low_confidence = (
        confidence is not None and confidence < inputs.ocr_confidence_threshold
    )

    # Fire on either signal. Extraction warnings matter on their own: a page
    # that is a bitmap scan needs a human, even if the pages that *did* extract
    # pull the length-weighted mean back above the threshold.
    if not low_confidence and not warnings:
        return None

    parts = []
    if low_confidence:
        parts.append(
            f"Extraction confidence is {confidence:.2f}, below the "
            f"{inputs.ocr_confidence_threshold:.2f} threshold"
            + (" (OCR was used for part of this document)" if inputs.ocr_used else "")
            + "."
        )
    parts.append(
        "Some pages could not be read as text, so the fields below may be "
        "incomplete; this document likely needs manual review."
    )
    parts.extend(warnings)

    return Finding(
        rule_id=R008,
        severity="info" if not low_confidence else "warning",
        category="extraction",
        message=" ".join(parts),
        details={
            "confidence": confidence,
            "threshold": inputs.ocr_confidence_threshold,
            "ocr_used": inputs.ocr_used,
            "warnings": warnings,
        },
    )


_RULES = (
    ("R001", _rule_r001),
    ("R002", _rule_r002),
    ("R003", _rule_r003),
    ("R004", _rule_r004),
    ("R005", _rule_r005),
    ("R006", _rule_r006),
    ("R007", _rule_r007),
    ("R008", _rule_r008),
)


def _matched_documents(inputs: VerificationInputs) -> List[str]:
    names: List[str] = []
    for match in inputs.duplicate_matches:
        label = match.get("filename") or match.get("document_id")
        if label and label not in names:
            names.append(str(label))
    return names


# --------------------------------------------------------------------------- #
# Outcome derivation
# --------------------------------------------------------------------------- #
def _derive_outcome(
    findings: Sequence[Finding], inputs: VerificationInputs
) -> str:
    """Map fired rules to the headline outcome (precedence, not a vote)."""
    fired = {finding.rule_id for finding in findings}
    if inputs.processing_error:
        return VerificationOutcome.PROCESSING_ERROR
    if R003 in fired:
        return VerificationOutcome.EXACT_DUPLICATE
    if R004 in fired:
        return VerificationOutcome.CONTENT_DUPLICATE
    if R005 in fired:
        return VerificationOutcome.NEAR_DUPLICATE_CANDIDATE
    if R001 in fired:
        return VerificationOutcome.VALIDATION_FAILED
    if R002 in fired:
        return VerificationOutcome.VALIDATION_FAILED
    if R006 in fired:
        return VerificationOutcome.INCONSISTENT_FIELDS
    if R007 in fired or R008 in fired:
        return VerificationOutcome.MANUAL_REVIEW_REQUIRED
    return VerificationOutcome.VALIDATION_PASSED


def _derive_validation_status(findings: Sequence[Finding]) -> str:
    """Did the field/format checks pass?

    ``NOT_RUN`` is reserved for the processing-error case, which ``decide()``
    handles before it gets here. Mapping "no findings" to ``NOT_RUN`` made a
    document that satisfied every rule look like it had never been validated.
    An empty result set is a *pass*, so report it as one.
    """
    fired = {finding.rule_id for finding in findings}
    if R001 in fired or R002 in fired:
        return ValidationStatus.FAILED
    return ValidationStatus.PASSED


def _derive_recommendation(outcome: str, findings: Sequence[Finding]) -> str:
    """What a human operator should do next (never an authenticity verdict)."""
    if outcome == VerificationOutcome.PROCESSING_ERROR:
        return ReviewRecommendation.RETRY
    if outcome in {
        VerificationOutcome.EXACT_DUPLICATE,
        VerificationOutcome.CONTENT_DUPLICATE,
    }:
        # A duplicate upload is normally rejected, but only a human knows
        # whether the resubmission was intentional (e.g. a re-issued document).
        return ReviewRecommendation.REJECT
    if outcome in {
        VerificationOutcome.NEAR_DUPLICATE_CANDIDATE,
        VerificationOutcome.INCONSISTENT_FIELDS,
        VerificationOutcome.MANUAL_REVIEW_REQUIRED,
        VerificationOutcome.VALIDATION_FAILED,
    }:
        return ReviewRecommendation.MANUAL_REVIEW
    return ReviewRecommendation.APPROVE


def _build_explanation(
    outcome: str,
    findings: Sequence[Finding],
    inputs: VerificationInputs,
) -> str:
    """Join the fired rules into a narrative a reviewer can act on."""
    lines: List[str] = []
    if inputs.processing_error:
        lines.append(
            f"Processing failed: {inputs.processing_error}. No verification "
            f"conclusions were drawn."
        )
        return "\n".join(lines)

    # ``findings`` is never empty here: a clean run carries the informational
    # R000 row, and the processing-error case returns earlier.
    for finding in findings:
        lines.append(f"[{finding.rule_id}] {finding.message}")

    outcome_sentences = {
        VerificationOutcome.EXACT_DUPLICATE: (
            "The uploaded file is a byte-identical copy of a document already in "
            "the store."
        ),
        VerificationOutcome.CONTENT_DUPLICATE: (
            "The uploaded document has the same content as an existing document, "
            "even though the file bytes differ."
        ),
        VerificationOutcome.NEAR_DUPLICATE_CANDIDATE: (
            "The document closely resembles an existing one; a human should "
            "confirm whether this is a legitimate resubmission."
        ),
        VerificationOutcome.VALIDATION_FAILED: (
            "The document did not satisfy its template's required-field or "
            "value-format rules."
        ),
        VerificationOutcome.INCONSISTENT_FIELDS: (
            "The document matches another document closely but disagrees on one "
            "or more critical fields, so the two are not the same record."
        ),
        VerificationOutcome.MANUAL_REVIEW_REQUIRED: (
            "Automated checks were inconclusive (structural uncertainty or low "
            "extraction confidence); manual review is recommended."
        ),
    }
    if outcome in outcome_sentences:
        lines.append(outcome_sentences[outcome])
    lines.append(
        "This outcome is an automated similarity/consistency assessment only; it "
        "is not a determination of authenticity, legality or forgery."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def decide(inputs: VerificationInputs) -> VerificationDecision:
    """Run every rule and derive the outcome, statuses and explanation."""
    findings: List[Finding] = []
    for rule_id, rule in _RULES:
        finding = rule(inputs)
        if finding is not None:
            findings.append(finding)

    # Every detector was quiet. Record that as a result (R000) so the run has an
    # audit trail. Skipped on a processing error, where nothing was evaluated.
    if not findings and not inputs.processing_error:
        findings.append(_rule_r000(inputs))

    outcome = _derive_outcome(findings, inputs)
    validation_status = (
        ValidationStatus.NOT_RUN if inputs.processing_error else _derive_validation_status(findings)
    )
    recommendation = _derive_recommendation(outcome, findings)
    explanation = _build_explanation(outcome, findings, inputs)

    return VerificationDecision(
        outcome=outcome,
        validation_status=validation_status,
        duplicate_status=inputs.duplicate_status or DuplicateStatus.UNIQUE,
        review_recommendation=recommendation,
        similarity_score=inputs.similarity_score,
        findings=findings,
        rules_fired=[finding.rule_id for finding in findings],
        explanation=explanation,
        thresholds=dict(inputs.thresholds),
    )


def describe_rules() -> List[Dict[str, str]]:
    """Return the rule table for the API/algorithm documentation endpoints."""
    return [
        {"rule_id": rule_id, "description": description}
        for rule_id, description in sorted(RULE_DESCRIPTIONS.items())
    ]
