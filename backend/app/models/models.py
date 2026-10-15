"""DocuTrace ORM models (SQLAlchemy 2.0 declarative style).

Conventions used by every model in this module
---------------------------------------------
* **UUID string primary keys** generated in Python (``uuid.uuid4().hex`` is not
  used so the value is also a valid RFC-4122 string). UUIDs keep identifiers
  unguessable and avoid leaking the row count in URLs.
* **UTC-naive timestamps** (``datetime.now(timezone.utc).replace(tzinfo=None)``).
  Every ``created_at`` / ``uploaded_at`` column is UTC; SQLite has no native
  timezone type, so storing naive-UTC once avoids the classic "some rows aware,
  some rows naive" comparison crash.
* **Status columns are plain strings** with the documented value sets listed in
  the small constant classes below them. String storage (rather than a native
  ENUM) keeps the schema portable across SQLite/PostgreSQL and keeps the API
  contract stable; the value sets are enforced by Pydantic ``Literal``s in
  :mod:`app.schemas.schemas` and by the deterministic rule engine in
  :mod:`app.services.verification`.
* **JSON columns** use SQLAlchemy's cross-dialect ``JSON`` type (stored as TEXT
  on SQLite), which is what lets a single row carry a whole threshold map or a
  list of field differences without a child table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def generate_uuid() -> str:
    """Return a fresh UUID4 string for use as a primary key."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (see module docstring)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_default_list() -> list:
    """Mutable default for JSON list columns (must be a callable, not ``[]``)."""
    return []


# --------------------------------------------------------------------------- #
# Status vocabularies (documented value sets)
# --------------------------------------------------------------------------- #
class UploadStatus:
    """``documents.upload_status``"""

    PENDING = "pending"          # row created, bytes not yet processed
    PROCESSING = "processing"    # pipeline is running
    COMPLETED = "completed"      # pipeline finished, verification ran
    FAILED = "failed"            # extraction/processing error (see error_message)


class ValidationStatus:
    """``documents.validation_status`` (field/structural validation only)."""

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


class DuplicateStatus:
    """``documents.duplicate_status``.

    ``unique`` / ``exact_duplicate`` (byte-identical file) /
    ``content_duplicate`` (identical after normalization) /
    ``near_duplicate`` (very similar, above the near-duplicate threshold).
    """

    UNIQUE = "unique"
    EXACT = "exact_duplicate"
    CONTENT = "content_duplicate"
    NEAR = "near_duplicate"


class VerificationOutcome:
    """``verification_runs.outcome`` — the headline result of a verification.

    Note the ordering matters for reporting: duplicates are reported *before*
    plain validation failures because an exact duplicate short-circuits the
    rest of the checks.
    """

    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    CONTENT_DUPLICATE = "CONTENT_DUPLICATE"
    NEAR_DUPLICATE_CANDIDATE = "NEAR_DUPLICATE_CANDIDATE"
    INCONSISTENT_FIELDS = "INCONSISTENT_FIELDS"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class ReviewRecommendation:
    """``verification_runs.review_recommendation`` (always review-oriented)."""

    APPROVE = "approve"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"
    RETRY = "retry"


class FieldStatus:
    """``extracted_fields.status``"""

    PRESENT = "present"
    MISSING = "missing"
    INVALID = "invalid"
    NOT_CHECKED = "not_checked"


class FieldSource:
    """``extracted_fields.source``"""

    TEMPLATE_LABEL = "template_label"
    REGEX = "regex"
    KMP_LABEL = "kmp_label"
    BIPARTITE_MATCH = "bipartite_match"
    LAYOUT_ANALYSIS = "layout_analysis"
    OCR = "ocr"


class Severity:
    """``verification_findings.severity``"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HashType:
    """``duplicate_groups.hash_type``"""

    FILE = "file"
    NORMALIZED_TEXT = "normalized_text"


class GroupType:
    """``duplicate_groups.group_type``"""

    EXACT = "exact"
    CONTENT = "content"


class ReportType:
    """``generated_reports.report_type``"""

    VERIFICATION = "verification"
    COMPARISON = "comparison"


# --------------------------------------------------------------------------- #
# 1. documents
# --------------------------------------------------------------------------- #
class Document(Base):
    """An uploaded document plus the outcome of processing it.

    ``file_sha256`` and ``normalized_text_hash`` are the two indexed
    fingerprints that make duplicate detection an O(1) index probe instead of a
    linear scan over prior uploads (see :mod:`app.algorithms.hashing`).
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    filename: Mapped[str] = mapped_column(String(512))
    stored_name: Mapped[str] = mapped_column(String(512))
    relative_path: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str] = mapped_column(String(255), default="")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)

    # Fingerprints (both indexed).
    file_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    normalized_text_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    # Classification.
    doc_type: Mapped[str] = mapped_column(
        String(64), default="unknown", index=True
    )
    upload_status: Mapped[str] = mapped_column(
        String(32), default=UploadStatus.PENDING
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), default=ValidationStatus.NOT_RUN
    )
    duplicate_status: Mapped[str] = mapped_column(
        String(32), default=DuplicateStatus.UNIQUE
    )

    # Headline numbers.
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processing_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extraction_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    text_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships.
    fields: Mapped[List["ExtractedField"]] = relationship(
        "ExtractedField",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ExtractedField.field_name",
    )
    verification_runs: Mapped[List["VerificationRun"]] = relationship(
        "VerificationRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="VerificationRun.started_at.desc()",
    )

    __table_args__ = (
        # ``file_sha256`` / ``normalized_text_hash`` / ``doc_type`` /
        # ``uploaded_at`` are single-column indexes declared inline above.
        Index("ix_documents_duplicate_status", "duplicate_status"),
        Index("ix_documents_upload_status", "upload_status"),
        Index("ix_documents_uploaded_at", "uploaded_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Document id={self.id[:8]} filename={self.filename!r} "
            f"type={self.doc_type} status={self.upload_status}>"
        )


# --------------------------------------------------------------------------- #
# 2. extracted_fields
# --------------------------------------------------------------------------- #
class ExtractedField(Base):
    """A single field extracted from a document and validated against a template."""

    __tablename__ = "extracted_fields"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(255))
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    field_type: Mapped[str] = mapped_column(String(64), default="text")
    status: Mapped[str] = mapped_column(
        String(32), default=FieldStatus.NOT_CHECKED
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default=FieldSource.TEMPLATE_LABEL)
    location: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, doc="{'page': int, 'line': int, 'label': str}"
    )

    document: Mapped["Document"] = relationship(
        "Document", back_populates="fields"
    )

    __table_args__ = (
        # ``document_id`` index is declared inline on the column above.
        Index("ix_extracted_fields_document_name", "document_id", "field_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ExtractedField {self.field_name}={self.field_value!r} "
            f"status={self.status}>"
        )


# --------------------------------------------------------------------------- #
# 3. document_templates
# --------------------------------------------------------------------------- #
class DocumentTemplate(Base):
    """A verification template: the expected fields/sections of a document class.

    ``aliases`` maps a canonical field name to accepted alternative labels, so a
    template can recognise ``"Invoice No"``, ``"Bill Number"`` and ``"Invoice #"``
    without duplicating the field definition.
    """

    __tablename__ = "document_templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="custom", index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    required_fields: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    optional_fields: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    critical_fields: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    expected_sections: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    section_order: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    aliases: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    fields: Mapped[List["TemplateField"]] = relationship(
        "TemplateField",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateField.position",
    )
    verification_runs: Mapped[List["VerificationRun"]] = relationship(
        "VerificationRun", back_populates="template"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DocumentTemplate {self.name!r} category={self.category!r}>"


# --------------------------------------------------------------------------- #
# 4. template_fields
# --------------------------------------------------------------------------- #
class TemplateField(Base):
    """One expected field of a :class:`DocumentTemplate`.

    ``validation_pattern`` is a regular expression the *extracted value* must
    match (e.g. ``\\b[A-Z]{2}\\d{4}\\b`` for an invoice number). ``critical``
    marks a field whose mismatch against a matched document is reported as an
    inconsistency rather than a cosmetic difference.
    """

    __tablename__ = "template_fields"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_templates.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    data_type: Mapped[str] = mapped_column(String(32), default="text")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_pattern: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped["DocumentTemplate"] = relationship(
        "DocumentTemplate", back_populates="fields"
    )

    # ``template_id`` index is declared inline on the column above.
    __table_args__ = (
        Index("ix_template_fields_template_name", "template_id", "name", unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<TemplateField {self.name!r} type={self.data_type} "
            f"required={self.required}>"
        )


# --------------------------------------------------------------------------- #
# 5. verification_runs
# --------------------------------------------------------------------------- #
class VerificationRun(Base):
    """One execution of the verification pipeline for a document.

    Keeps the three status dimensions separate on purpose:

    * ``validation_status``  — are the required fields present and well-formed?
    * ``duplicate_status``   — does an identical/near-identical document exist?
    * ``review_recommendation`` — what should a human operator do next?

    ``outcome`` is the single headline enum derived from all three.
    """

    __tablename__ = "verification_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    outcome: Mapped[str] = mapped_column(
        String(64), default=VerificationOutcome.MANUAL_REVIEW_REQUIRED, index=True
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), default=ValidationStatus.NOT_RUN
    )
    duplicate_status: Mapped[str] = mapped_column(
        String(32), default=DuplicateStatus.UNIQUE
    )
    review_recommendation: Mapped[str] = mapped_column(
        String(32), default=ReviewRecommendation.MANUAL_REVIEW
    )
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    thresholds_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    processing_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="verification_runs"
    )
    template: Mapped[Optional["DocumentTemplate"]] = relationship(
        "DocumentTemplate", back_populates="verification_runs"
    )
    findings: Mapped[List["VerificationFinding"]] = relationship(
        "VerificationFinding",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="VerificationFinding.rule_id",
    )
    similarity_matches: Mapped[List["SimilarityMatch"]] = relationship(
        "SimilarityMatch",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SimilarityMatch.overall_score.desc()",
    )
    reports: Mapped[List["GeneratedReport"]] = relationship(
        "GeneratedReport", back_populates="run"
    )

    __table_args__ = (
        # ``document_id`` / ``outcome`` indexes are declared inline above.
        Index("ix_verification_runs_template_id", "template_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationRun {self.id[:8]} outcome={self.outcome}>"


# --------------------------------------------------------------------------- #
# 6. verification_findings
# --------------------------------------------------------------------------- #
class VerificationFinding(Base):
    """One deterministic rule result (R001..R008) raised during a run."""

    __tablename__ = "verification_findings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("verification_runs.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(16), index=True)
    severity: Mapped[str] = mapped_column(String(16), default=Severity.INFO)
    category: Mapped[str] = mapped_column(String(64), default="general")
    message: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    run: Mapped["VerificationRun"] = relationship(
        "VerificationRun", back_populates="findings"
    )

    # ``run_id`` / ``rule_id`` indexes are declared inline on the columns above.

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationFinding {self.rule_id} {self.severity}>"


# --------------------------------------------------------------------------- #
# 7. similarity_matches
# --------------------------------------------------------------------------- #
class SimilarityMatch(Base):
    """A bounded, ranked document-to-document similarity result."""

    __tablename__ = "similarity_matches"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("verification_runs.id", ondelete="CASCADE"), index=True
    )
    source_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE")
    )
    target_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE")
    )

    text_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    edit_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(
        Float, default=0.0, index=True
    )
    match_type: Mapped[str] = mapped_column(
        String(32), default="near_duplicate"
    )
    field_differences_json: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["VerificationRun"] = relationship(
        "VerificationRun", back_populates="similarity_matches"
    )

    # ``run_id`` / ``overall_score`` indexes are declared inline above.
    __table_args__ = (Index("ix_similarity_matches_target", "target_document_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<SimilarityMatch {self.match_type} "
            f"overall={self.overall_score:.3f}>"
        )


# --------------------------------------------------------------------------- #
# 8. duplicate_groups
# --------------------------------------------------------------------------- #
class DuplicateGroup(Base):
    """A set of documents that share a fingerprint.

    Groups are keyed by (``hash_type``, ``hash_value``): ``file`` groups hold
    byte-identical files, ``normalized_text`` groups hold documents whose
    normalized text is identical. Documents are *never* grouped by filename —
    filenames are user-controlled metadata, not evidence of duplication.
    """

    __tablename__ = "duplicate_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    hash_type: Mapped[str] = mapped_column(String(32), default=HashType.FILE)
    hash_value: Mapped[str] = mapped_column(String(64), index=True)
    group_type: Mapped[str] = mapped_column(String(32), default=GroupType.EXACT)
    document_ids_json: Mapped[list] = mapped_column(JSON, default=_json_default_list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_duplicate_groups_hash_type_value", "hash_type", "hash_value"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<DuplicateGroup {self.group_type}/{self.hash_type} "
            f"n={len(self.document_ids_json or [])}>"
        )


# --------------------------------------------------------------------------- #
# 9. algorithm_runs
# --------------------------------------------------------------------------- #
class AlgorithmRun(Base):
    """Instrumentation row: one algorithm execution tied to a document/run.

    These rows are what make the "Algorithms executed with timings" section of
    every PDF report factual rather than decorative: each entry is a real
    measurement produced by the algorithm core's own ``time.perf_counter_ns``
    delta and operation counter.
    """

    __tablename__ = "algorithm_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=True,
    )

    algorithm: Mapped[str] = mapped_column(String(64), index=True)
    input_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    operation_count: Mapped[int] = mapped_column(Integer, default=0)
    result_summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_algorithm_runs_document_id", "document_id"),
        Index("ix_algorithm_runs_run_id", "run_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AlgorithmRun {self.algorithm} {self.execution_time_ms:.3f}ms>"


# --------------------------------------------------------------------------- #
# 10. benchmark_results
# --------------------------------------------------------------------------- #
class BenchmarkResult(Base):
    """One measured benchmark row (median of ``repeats`` timed repetitions)."""

    __tablename__ = "benchmark_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    algorithm: Mapped[str] = mapped_column(String(64), index=True)
    input_size: Mapped[int] = mapped_column(Integer, default=0)
    dataset_type: Mapped[str] = mapped_column(String(64), default="typical_case")
    case_type: Mapped[str] = mapped_column(
        String(32), default="average", doc="best | average | worst"
    )
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    operations: Mapped[int] = mapped_column(Integer, default=0)
    repeats: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )

    # ``algorithm`` index is declared inline on the column above.
    __table_args__ = (
        Index("ix_benchmark_results_lookup", "algorithm", "input_size", "dataset_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<BenchmarkResult {self.algorithm} n={self.input_size} "
            f"{self.execution_time_ms:.3f}ms>"
        )


# --------------------------------------------------------------------------- #
# 11. generated_reports
# --------------------------------------------------------------------------- #
class GeneratedReport(Base):
    """A PDF/JSON artifact rendered from *stored* run data only.

    Reports are reproducible artifacts: the renderer reads persisted rows and
    never re-runs an algorithm, so the same run id always yields the same
    document.
    """

    __tablename__ = "generated_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    #: Comparison exports are stateless: they are rendered from a client-supplied
    #: comparison payload, so this is a caller-provided correlation id rather
    #: than a foreign key.
    comparison_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )

    report_uuid: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=generate_uuid
    )
    report_type: Mapped[str] = mapped_column(
        String(32), default=ReportType.VERIFICATION
    )
    relative_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )

    run: Mapped[Optional["VerificationRun"]] = relationship(
        "VerificationRun", back_populates="reports"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GeneratedReport {self.report_type} {self.relative_path}>"


# --------------------------------------------------------------------------- #
# 12. application_settings
# --------------------------------------------------------------------------- #
class ApplicationSetting(Base):
    """A typed application setting (``key`` -> JSON value).

    Thresholds live here rather than in code so an operator can tune the
    verification policy without redeploying, while ``value_json`` keeps the
    value typed (number/bool/list/dict) instead of stringly-typed.
    """

    __tablename__ = "application_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ApplicationSetting {self.key}={self.value_json!r}>"
