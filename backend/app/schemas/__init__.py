"""Pydantic v2 request/response schemas for the DocuTrace API."""

from app.schemas.schemas import (
    ORM_CONFIG,
    AlgorithmInfoOut,
    AlgorithmRunOut,
    AlgorithmRunRequest,
    AlgorithmUsageOut,
    AnalyticsDetailOut,
    AnalyticsOverviewOut,
    BenchmarkRequest,
    BenchmarkResponse,
    BenchmarkRowOut,
    CompareExportRequest,
    CompareRequest,
    CompareResponse,
    ComparisonDetailOut,
    ChangeDetectRequest,
    ChangeDetectResponse,
    ChangeReportOut,
    DocumentDetailOut,
    DocumentOut,
    DocumentTextOut,
    DuplicateDocumentRef,
    DuplicateGroupDetailOut,
    DuplicateGroupOut,
    DuplicateSummaryOut,
    ExtractedFieldOut,
    HealthResponse,
    Page,
    PdfMetadataOut,
    ReVerifyResponse,
    ReportExportRequest,
    ReportGenerateRequest,
    ReportOut,
    SettingsResponse,
    SettingOut,
    SettingUpdate,
    SimilarityMatchOut,
    StageTiming,
    StructureOut,
    StructureSectionOut,
    StyleChangeOut,
    TemplateCreate,
    TemplateFieldIn,
    TemplateFieldOut,
    TemplateOut,
    TemplateUpdate,
    TextChangeHunkOut,
    TextChangeRequest,
    TextChangeResponse,
    UploadResponse,
    VerificationFindingOut,
    VerificationRunDetailOut,
    VerificationRunOut,
)

__all__ = [
    "ORM_CONFIG",
    "HealthResponse", "Page",
    # Templates
    "TemplateOut", "TemplateFieldOut", "TemplateCreate", "TemplateUpdate",
    "TemplateFieldIn",
    # Documents
    "DocumentOut", "DocumentDetailOut", "DocumentTextOut", "ExtractedFieldOut",
    # Verification
    "VerificationRunOut", "VerificationRunDetailOut", "VerificationFindingOut",
    "SimilarityMatchOut", "StageTiming", "UploadResponse", "ReVerifyResponse",
    # Structure
    "StructureOut", "StructureSectionOut",
    # Comparison
    "CompareRequest", "CompareResponse", "ComparisonDetailOut",
    "CompareExportRequest", "ReportExportRequest",
    # Change detection & PDF metadata
    "ChangeDetectRequest", "ChangeDetectResponse", "ChangeReportOut",
    "TextChangeRequest", "TextChangeResponse", "TextChangeHunkOut",
    "StyleChangeOut", "PdfMetadataOut",
    # Duplicates
    "DuplicateGroupOut", "DuplicateGroupDetailOut", "DuplicateSummaryOut",
    "DuplicateDocumentRef",
    # Algorithms
    "AlgorithmInfoOut", "AlgorithmRunOut", "AlgorithmRunRequest",
    # Benchmarks
    "BenchmarkRequest", "BenchmarkResponse", "BenchmarkRowOut",
    # Reports
    "ReportOut", "ReportGenerateRequest",
    # Settings
    "SettingOut", "SettingUpdate", "SettingsResponse",
    # Analytics
    "AnalyticsOverviewOut", "AnalyticsDetailOut", "AlgorithmUsageOut",
]
