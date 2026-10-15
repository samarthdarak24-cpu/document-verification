"""Pydantic v2 request/response models for the DocuTrace API.

Conventions
-----------
* ORM reads use ``from_attributes=True`` so the routers can hand SQLAlchemy rows
  straight to the response models without a manual mapping layer.
* Status fields use ``Literal[...]`` unions rather than free-form ``str``: the
  database stores plain strings, but the API contract is explicit, so a typo in
  the database surfaces as a 500-level validation error during development rather
  than as a silently accepted bogus status.
* Every response model is ``model_config = ConfigDict(from_attributes=True)``
  where it mirrors a table, and JSON-serialisable (no datetimes leak through
  unformatted except where ``datetime`` is intentional).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Optional, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Shared ORM-read configuration.
ORM_CONFIG = ConfigDict(from_attributes=True)

T = TypeVar("T")

# --------------------------------------------------------------------------- #
# Shared literals
# --------------------------------------------------------------------------- #
UploadStatusLiteral = Literal["pending", "processing", "completed", "failed"]
ValidationStatusLiteral = Literal["not_run", "passed", "failed"]
DuplicateStatusLiteral = Literal[
    "unique", "exact_duplicate", "content_duplicate", "near_duplicate"
]
OutcomeLiteral = Literal[
    "VALIDATION_PASSED",
    "VALIDATION_FAILED",
    "EXACT_DUPLICATE",
    "CONTENT_DUPLICATE",
    "NEAR_DUPLICATE_CANDIDATE",
    "INCONSISTENT_FIELDS",
    "MANUAL_REVIEW_REQUIRED",
    "PROCESSING_ERROR",
]
ReviewRecommendationLiteral = Literal["approve", "manual_review", "reject", "retry"]
FieldStatusLiteral = Literal["present", "missing", "invalid", "not_checked"]
FieldSourceLiteral = Literal[
    "template_label", "regex", "kmp_label", "bipartite_match", "layout_analysis", "ocr"
]
SeverityLiteral = Literal["info", "warning", "critical"]
DocTypeLiteral = Literal[
    "invoice",
    "mark_sheet",
    "application_form",
    "employment_letter",
    "general_report",
    "research_paper",
    "custom",
    "unknown",
]


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    """``GET /api/health``."""

    status: Literal["ok"] = "ok"
    version: str
    app: str = "DocuTrace"
    database: str = "ok"
    timestamp: str


# --------------------------------------------------------------------------- #
# Generic pagination
# --------------------------------------------------------------------------- #
class Page(BaseModel, Generic[T]):
    """A page of results plus the totals needed to render a paginator."""

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
class TemplateFieldOut(BaseModel):
    """One expected field of a template."""

    model_config = ORM_CONFIG

    id: str
    name: str
    data_type: str
    required: bool
    validation_pattern: Optional[str] = None
    critical: bool
    position: int


class TemplateOut(BaseModel):
    """A verification template."""

    model_config = ORM_CONFIG

    id: str
    name: str
    category: str
    description: Optional[str] = None
    required_fields: List[str] = Field(default_factory=list)
    optional_fields: List[str] = Field(default_factory=list)
    critical_fields: List[str] = Field(default_factory=list)
    expected_sections: List[str] = Field(default_factory=list)
    section_order: List[str] = Field(default_factory=list)
    aliases: Dict[str, List[str]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    fields: List[TemplateFieldOut] = Field(default_factory=list)


class TemplateFieldIn(BaseModel):
    """A template field in a create/update payload."""

    name: str = Field(min_length=1, max_length=128)
    data_type: str = Field(default="text", max_length=32)
    required: bool = True
    validation_pattern: Optional[str] = Field(default=None, max_length=512)
    critical: bool = False
    position: int = 0


class TemplateCreate(BaseModel):
    """``POST /api/templates``."""

    name: str = Field(min_length=1, max_length=128)
    category: str = Field(default="custom", max_length=64)
    description: Optional[str] = None
    required_fields: List[str] = Field(default_factory=list)
    optional_fields: List[str] = Field(default_factory=list)
    critical_fields: List[str] = Field(default_factory=list)
    expected_sections: List[str] = Field(default_factory=list)
    section_order: List[str] = Field(default_factory=list)
    aliases: Dict[str, List[str]] = Field(default_factory=dict)
    fields: List[TemplateFieldIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _normalise_name(cls, value: str) -> str:
        return value.strip()


class TemplateUpdate(BaseModel):
    """``PUT /api/templates/{id}`` (partial update)."""

    category: Optional[str] = None
    description: Optional[str] = None
    required_fields: Optional[List[str]] = None
    optional_fields: Optional[List[str]] = None
    critical_fields: Optional[List[str]] = None
    expected_sections: Optional[List[str]] = None
    section_order: Optional[List[str]] = None
    aliases: Optional[Dict[str, List[str]]] = None
    fields: Optional[List[TemplateFieldIn]] = None


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
class ExtractedFieldOut(BaseModel):
    """One extracted field."""

    model_config = ORM_CONFIG

    id: str
    document_id: str
    field_name: str
    field_value: Optional[str] = None
    field_type: str
    status: FieldStatusLiteral
    confidence: float
    source: FieldSourceLiteral
    location: Optional[Dict[str, Any]] = None


class DocumentOut(BaseModel):
    """A document row as returned by the API."""

    model_config = ORM_CONFIG

    id: str
    filename: str
    stored_name: str
    relative_path: str
    mime_type: str
    file_size: int
    file_sha256: str
    normalized_text_hash: Optional[str] = None
    doc_type: str
    upload_status: UploadStatusLiteral
    validation_status: ValidationStatusLiteral
    duplicate_status: DuplicateStatusLiteral
    similarity_score: Optional[float] = None
    processing_duration_ms: Optional[int] = None
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extraction_confidence: Optional[float] = None
    ocr_used: bool
    text_excerpt: Optional[str] = None
    uploaded_at: datetime
    error_message: Optional[str] = None

    @field_validator("uploaded_at", mode="before")
    @classmethod
    def _naive_as_utc(cls, value: Any) -> Any:
        """Store UTC-naive timestamps; label them so clients can parse them."""
        if isinstance(value, datetime):
            return value
        return value


class DocumentDetailOut(DocumentOut):
    """A document plus its extracted fields and run count."""

    fields: List[ExtractedFieldOut] = Field(default_factory=list)
    verification_run_count: int = 0


class DocumentTextOut(BaseModel):
    """``GET /api/documents/{id}/text``."""

    document_id: str
    filename: str
    original_excerpt: Optional[str] = None
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extraction_confidence: Optional[float] = None
    ocr_used: bool
    warnings: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
class StageTiming(BaseModel):
    """One pipeline stage's wall-clock duration."""

    stage: str
    label: str
    elapsed_ms: float
    detail: Dict[str, Any] = Field(default_factory=dict)


class VerificationFindingOut(BaseModel):
    """A rule finding."""

    model_config = ORM_CONFIG

    id: str
    rule_id: str
    severity: SeverityLiteral
    category: str
    message: str
    details_json: Optional[Dict[str, Any]] = None


class SimilarityMatchOut(BaseModel):
    """A recorded similarity match."""

    model_config = ORM_CONFIG

    id: str
    source_document_id: str
    target_document_id: str
    text_similarity: float
    edit_similarity: float
    overall_score: float
    match_type: str
    explanation: Optional[str] = None
    field_differences: List[Dict[str, Any]] = Field(default_factory=list)


class VerificationRunOut(BaseModel):
    """A verification run."""

    model_config = ORM_CONFIG

    id: str
    document_id: str
    template_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    outcome: OutcomeLiteral
    validation_status: ValidationStatusLiteral
    duplicate_status: DuplicateStatusLiteral
    review_recommendation: ReviewRecommendationLiteral
    similarity_score: Optional[float] = None
    processing_ms: Optional[int] = None
    explanation: Optional[str] = None
    thresholds: Dict[str, Any] = Field(default_factory=dict)


class VerificationRunDetailOut(VerificationRunOut):
    """A verification run with its findings, matches and algorithm rows."""

    findings: List[VerificationFindingOut] = Field(default_factory=list)
    similarity_matches: List[SimilarityMatchOut] = Field(default_factory=list)
    algorithm_runs: List["AlgorithmRunOut"] = Field(default_factory=list)
    pipeline_order: List[str] = Field(default_factory=list)
    stage_timings: List[StageTiming] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """``POST /api/documents/upload`` — the document plus the run it produced."""

    document: DocumentOut
    run: VerificationRunOut
    stage_timings: List[StageTiming] = Field(default_factory=list)
    pipeline_order: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)


class ReVerifyResponse(BaseModel):
    """``POST /api/verification/{document_id}``."""

    document: DocumentOut
    run: VerificationRunOut
    warnings: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Structure & fields (nested inside document detail responses)
# --------------------------------------------------------------------------- #
class StructureSectionOut(BaseModel):
    """A detected/evidenced document section."""

    section: str
    label: Optional[str] = None
    page: Optional[int] = None
    line: Optional[int] = None


class StructureOut(BaseModel):
    """Structural verification details."""

    uncertain: bool
    heuristic: str
    headings: List[Dict[str, Any]] = Field(default_factory=list)
    sections: List[StructureSectionOut] = Field(default_factory=list)
    unverified_sections: List[str] = Field(default_factory=list)
    present: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    order_ok: Optional[bool] = None
    dfs_visited: Optional[int] = None
    dfs_max_depth: Optional[int] = None
    bfs_visited: Optional[int] = None
    signature: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
class CompareRequest(BaseModel):
    """``POST /api/compare``."""

    source_document_id: Optional[str] = None
    target_document_id: Optional[str] = None
    source_text: Optional[str] = None
    target_text: Optional[str] = None
    source_label: Optional[str] = None
    target_label: Optional[str] = None
    compare_structure: bool = True

    @field_validator("source_text", "target_text")
    @classmethod
    def _validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value) > 2_000_000:
            raise ValueError("Raw text is limited to 2,000,000 characters.")
        return value


class ComparisonDetailOut(BaseModel):
    """The measured comparison payload."""

    source_tokens: int
    target_tokens: int
    compared_source_tokens: int
    compared_target_tokens: int
    truncated: bool
    truncation_note: Optional[str] = None
    text_similarity: float
    edit_similarity: float
    overall_score: float
    lcs_length: int
    edit_distance: int
    words_added: int
    words_removed: int
    words_unchanged: int
    substitutions: int
    insertions: List[str] = Field(default_factory=list)
    deletions: List[str] = Field(default_factory=list)
    replacements: List[Dict[str, Optional[str]]] = Field(default_factory=list)
    field_differences: List[Dict[str, Any]] = Field(default_factory=list)
    structure: Optional[Dict[str, Any]] = None
    elapsed_ms: float
    notes: List[str] = Field(default_factory=list)


class CompareResponse(BaseModel):
    """``POST /api/compare`` response (also the payload for the PDF export)."""

    source_document: Dict[str, Any] = Field(default_factory=dict)
    target_document: Dict[str, Any] = Field(default_factory=dict)
    comparison: ComparisonDetailOut
    verdict: str
    algorithms_executed: List[str] = Field(default_factory=list)
    compared_at: str


class CompareExportRequest(BaseModel):
    """``POST /api/compare/export`` — a CompareResponse plus optional metadata."""

    payload: CompareResponse
    comparison_id: Optional[str] = None
    title: Optional[str] = None
    generated_by: Optional[str] = None


# --------------------------------------------------------------------------- #
# Change detection & PDF layout metadata
# --------------------------------------------------------------------------- #
class TextChangeHunkOut(BaseModel):
    """One contiguous region of text difference."""

    type: Literal["insert", "delete", "replace"]
    removed_text: str = ""
    added_text: str = ""
    removed_tokens: List[str] = Field(default_factory=list)
    added_tokens: List[str] = Field(default_factory=list)
    removed_token_count: int = 0
    added_token_count: int = 0
    char_edit_distance: int = 0
    char_operations: List[Dict[str, Any]] = Field(default_factory=list)
    original_index: Optional[int] = None
    modified_index: Optional[int] = None


class StyleChangeOut(BaseModel):
    """A typographic change for a span whose text is otherwise unchanged."""

    text: str
    page: int
    changes: Dict[str, Any] = Field(default_factory=dict)


class ChangeReportOut(BaseModel):
    """The measured change payload (mirrors ``ChangeReport.to_dict``)."""

    changed: bool
    verdict: str
    text_similarity: float
    edit_similarity: float
    lcs_length: int
    original_token_count: int
    modified_token_count: int
    unchanged_tokens: int
    added_tokens: int
    removed_tokens: int
    hunk_count: int
    hunks: List[TextChangeHunkOut] = Field(default_factory=list)
    style_change_count: int = 0
    style_changes: List[StyleChangeOut] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    algorithms_executed: List[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0


class ChangeDetectRequest(BaseModel):
    """``POST /api/changes/detect`` — compare two stored documents."""

    source_document_id: str
    target_document_id: str
    compare_metadata: bool = True
    max_tokens: int = Field(default=4000, ge=1, le=50_000)


class ChangeDetectResponse(BaseModel):
    """``POST /api/changes/detect`` response."""

    source_document: Dict[str, Any] = Field(default_factory=dict)
    target_document: Dict[str, Any] = Field(default_factory=dict)
    report: ChangeReportOut
    compared_at: str


class TextChangeRequest(BaseModel):
    """``POST /api/changes/text`` — compare two raw texts (no stored file)."""

    original_text: str
    modified_text: str
    max_tokens: int = Field(default=4000, ge=1, le=50_000)

    @field_validator("original_text", "modified_text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        if len(value) > 2_000_000:
            raise ValueError("Raw text is limited to 2,000,000 characters.")
        return value


class TextChangeResponse(BaseModel):
    """``POST /api/changes/text`` response."""

    report: ChangeReportOut
    compared_at: str


class PdfMetadataOut(BaseModel):
    """``GET /api/documents/{id}/pdf-metadata``."""

    document_id: str
    filename: str
    page_count: int
    span_count: int
    is_encrypted: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    style_summary: Dict[str, Any] = Field(default_factory=dict)
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    truncated: bool = False
    elapsed_ms: float = 0.0


# --------------------------------------------------------------------------- #
# Duplicates
# --------------------------------------------------------------------------- #
class DuplicateDocumentRef(BaseModel):
    """A document referenced by a duplicate group."""

    id: str
    filename: str
    doc_type: str
    duplicate_status: DuplicateStatusLiteral
    uploaded_at: datetime


class DuplicateGroupOut(BaseModel):
    """A duplicate group."""

    model_config = ORM_CONFIG

    id: str
    hash_type: Literal["file", "normalized_text"]
    hash_value: str
    group_type: Literal["exact", "content"]
    document_ids: List[str] = Field(default_factory=list)
    created_at: datetime


class DuplicateGroupDetailOut(DuplicateGroupOut):
    """A duplicate group with its resolved documents."""

    documents: List[DuplicateDocumentRef] = Field(default_factory=list)


class DuplicateSummaryOut(BaseModel):
    """``GET /api/duplicates`` overview."""

    total_groups: int
    exact_groups: int
    content_groups: int
    documents_flagged: int
    by_status: Dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Algorithms
# --------------------------------------------------------------------------- #
class AlgorithmRunOut(BaseModel):
    """One recorded algorithm execution."""

    model_config = ORM_CONFIG

    id: str
    document_id: Optional[str] = None
    run_id: Optional[str] = None
    algorithm: str
    input_summary: Optional[str] = None
    execution_time_ms: float
    operation_count: int
    result_summary: Optional[Dict[str, Any]] = None
    created_at: datetime


class AlgorithmInfoOut(BaseModel):
    """Metadata about one algorithm (for the Algorithm Laboratory UI)."""

    name: str
    title: str
    unit: str
    complexity_time: str
    complexity_space: str
    description: str
    parameters: List[Dict[str, Any]] = Field(default_factory=list)


class AlgorithmRunRequest(BaseModel):
    """``POST /api/algorithms/run`` — run an algorithm on the caller's input."""

    algorithm: str = Field(min_length=1, max_length=64)
    inputs: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("inputs")
    @classmethod
    def _bound_inputs(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(json_dumps(value)) > 500_000:
            raise ValueError("Inputs are limited to 500,000 characters serialized.")
        return value


def json_dumps(value: Any) -> str:  # pragma: no cover - helper for validation
    import json

    return json.dumps(value, default=str)


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #
class BenchmarkRowOut(BaseModel):
    """One measured benchmark row.

    ``id`` / ``created_at`` are only present once the row has been persisted, so
    they are optional: the same schema validates both freshly measured rows
    returned by ``POST /api/benchmarks/run`` and stored rows.
    """

    model_config = ORM_CONFIG

    id: Optional[str] = None
    algorithm: str
    input_size: int
    dataset_type: str
    case_type: str
    execution_time_ms: float
    memory_bytes: int
    operations: int
    repeats: int
    created_at: Optional[datetime] = None


class BenchmarkRequest(BaseModel):
    """``POST /api/benchmarks/run``."""

    algorithms: Optional[List[str]] = None
    datasets: Optional[List[str]] = None
    sizes: Optional[List[int]] = None
    repeats: int = Field(default=3, ge=1, le=10)
    persist: bool = True


class BenchmarkResponse(BaseModel):
    """Result of a benchmark run."""

    rows: List[BenchmarkRowOut]
    stored: int
    summary: Dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: float


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
class ReportOut(BaseModel):
    """A generated report row."""

    model_config = ORM_CONFIG

    id: str
    run_id: Optional[str] = None
    document_id: Optional[str] = None
    comparison_id: Optional[str] = None
    report_uuid: str
    report_type: Literal["verification", "comparison"]
    relative_path: str
    created_at: datetime


class ReportGenerateRequest(BaseModel):
    """``POST /api/reports/{run_id}/generate``."""

    format: Literal["pdf", "json"] = "pdf"


class ReportExportRequest(BaseModel):
    """``POST /api/reports/export`` — render a comparison report from a payload."""

    payload: CompareResponse
    comparison_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class SettingOut(BaseModel):
    """One application setting."""

    model_config = ORM_CONFIG

    id: str
    key: str
    value_json: Any = None
    updated_at: datetime


class SettingUpdate(BaseModel):
    """``PUT /api/settings/{key}``."""

    value: Any


class SettingsResponse(BaseModel):
    """``GET /api/settings``."""

    settings: Dict[str, Any] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
class AnalyticsOverviewOut(BaseModel):
    """``GET /api/analytics/overview`` — aggregate counts, all computed in SQL."""

    documents_total: int
    documents_by_status: Dict[str, int] = Field(default_factory=dict)
    documents_by_type: Dict[str, int] = Field(default_factory=dict)
    documents_by_duplicate_status: Dict[str, int] = Field(default_factory=dict)
    runs_by_outcome: Dict[str, int] = Field(default_factory=dict)
    findings_by_rule: Dict[str, int] = Field(default_factory=dict)
    findings_by_severity: Dict[str, int] = Field(default_factory=dict)
    ocr_usage: Dict[str, int] = Field(default_factory=dict)
    extraction_methods: Dict[str, int] = Field(default_factory=dict)
    average_similarity: Optional[float] = None
    average_processing_ms: Optional[float] = None
    average_confidence: Optional[float] = None
    duplicate_groups: int = 0
    reports_generated: int = 0


class AlgorithmUsageOut(BaseModel):
    """Algorithm usage across recorded runs."""

    algorithm: str
    executions: int
    total_ms: float
    max_ms: float
    avg_operations: float


class AnalyticsDetailOut(BaseModel):
    """``GET /api/analytics/algorithms``."""

    algorithms: List[AlgorithmUsageOut] = Field(default_factory=list)
    benchmarks: Dict[str, Any] = Field(default_factory=dict)


VerificationRunDetailOut.model_rebuild()
