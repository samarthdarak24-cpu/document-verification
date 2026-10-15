/** Shared API types — mirrors the backend Pydantic schemas. */

export type ValidationStatus = "passed" | "passed_with_warnings" | "failed" | "not_run";
export type DuplicateStatus =
  | "unique"
  | "content_duplicate"
  | "near_duplicate"
  | "exact_duplicate";
export type ReviewRecommendation = "accept" | "manual_review" | "reject" | "retry";
export type UploadStatus = "processing" | "completed" | "failed";

export interface HealthResponse {
  status: string;
  version: string;
  app: string;
  database: string;
  timestamp: string;
}

export interface DocumentOut {
  id: string;
  filename: string;
  mime_type: string | null;
  doc_type: string;
  upload_status: UploadStatus;
  file_size: number | null;
  page_count: number | null;
  extraction_method: string | null;
  extraction_confidence: number | null;
  ocr_used: boolean;
  file_sha256: string | null;
  normalized_text_hash: string | null;
  text_excerpt: string | null;
  validation_status: ValidationStatus;
  duplicate_status: DuplicateStatus;
  similarity_score: number | null;
  processing_duration_ms: number | null;
  uploaded_at: string;
  error_message: string | null;
}

export interface ExtractedFieldOut {
  id: string;
  document_id: string;
  field_name: string;
  field_value: string | null;
  field_type: string;
  status: string;
  confidence: number;
  source: string;
  location: Record<string, unknown> | null;
}

export interface DocumentDetailOut extends DocumentOut {
  fields: ExtractedFieldOut[];
  verification_run_count: number;
}

export interface DocumentTextOut {
  document_id: string;
  filename: string;
  original_excerpt: string | null;
  page_count: number | null;
  extraction_method: string | null;
  extraction_confidence: number | null;
  ocr_used: boolean;
  warnings: string[];
}

export interface StageTiming {
  stage: string;
  label: string;
  elapsed_ms: number;
  detail: Record<string, unknown>;
  algorithms: string[];
}

export interface VerificationRunOut {
  id: string;
  document_id: string;
  template_id: string | null;
  started_at: string;
  completed_at: string | null;
  outcome: string;
  validation_status: ValidationStatus;
  duplicate_status: DuplicateStatus;
  review_recommendation: ReviewRecommendation;
  similarity_score: number | null;
  explanation: string | null;
  processing_ms: number | null;
}

export interface FindingOut {
  id: string;
  rule_id: string;
  severity: string;
  category: string;
  message: string;
  details: Record<string, unknown> | null;
}

export interface SimilarityMatchOut {
  id: string;
  source_document_id: string | null;
  target_document_id: string;
  text_similarity: number;
  edit_similarity: number;
  overall_score: number;
  match_type: string;
  explanation: string | null;
}

export interface UploadResponse {
  document: DocumentOut;
  run: VerificationRunOut;
  stage_timings: StageTiming[];
  pipeline_order: string[];
  warnings: string[];
  extraction_warnings: string[];
}

export interface VerificationDetailOut {
  run: VerificationRunOut;
  document: DocumentOut;
  findings: FindingOut[];
  matches: SimilarityMatchOut[];
  stage_timings?: StageTiming[];
  pipeline_order?: string[];
}

export interface TemplateFieldOut {
  id: string;
  name: string;
  data_type: string;
  required: boolean;
  validation_pattern: string | null;
  critical: boolean;
  position: number;
}

export interface TemplateOut {
  id: string;
  name: string;
  category: string;
  description: string | null;
  required_fields: string[];
  optional_fields: string[];
  critical_fields: string[];
  expected_sections: string[];
  section_order: string[];
  aliases: Record<string, string[]>;
  created_at: string;
  updated_at: string;
  fields: TemplateFieldOut[];
}

export interface AlgorithmParameter {
  name: string;
  type: string;
  label: string;
  required?: boolean;
  default?: unknown;
}

export interface AlgorithmInfo {
  name: string;
  title: string;
  unit: string;
  complexity_time: string;
  complexity_space: string;
  description: string;
  parameters: AlgorithmParameter[];
}

export interface AlgorithmRunOut {
  algorithm: string;
  execution_time_ms: number;
  operation_count: number;
  input_summary: string | null;
  result_summary: Record<string, unknown> | null;
  created_at: string;
  document_id?: string | null;
}

export interface BenchmarkRowOut {
  id: string | null;
  algorithm: string;
  input_size: number;
  dataset_type: string;
  case_type: string;
  execution_time_ms: number;
  memory_bytes: number;
  operations: number;
  repeats: number;
  created_at: string | null;
}

export interface BenchmarkRunResponse {
  rows: BenchmarkRowOut[];
  stored: number;
  summary: Record<string, unknown>;
  elapsed_ms: number;
}

export interface ReportOut {
  id: string;
  run_id: string | null;
  document_id: string | null;
  report_uuid: string;
  report_type: string;
  relative_path: string | null;
  created_at: string;
}

export interface DuplicateGroupOut {
  id: string;
  group_type: string;
  hash_type: string;
  hash_value: string;
  document_ids: string[];
  member_count: number;
  canonical_document_id: string | null;
  created_at: string;
}

export interface DuplicatesSummary {
  total_groups: number;
  exact_groups: number;
  content_groups: number;
  documents_flagged: number;
  by_status: Record<string, number>;
}

export interface AnalyticsOverview {
  documents: Record<string, number>;
  runs: Record<string, number>;
  duplicates: DuplicatesSummary;
  fields?: Record<string, number>;
  algorithms?: Record<string, number>;
  coverage?: Record<string, number>;
  storage?: Record<string, unknown>;
}

export interface CompareResult {
  source_document_id: string;
  target_document_id: string;
  overall_score: number;
  text_similarity: number;
  edit_similarity: number;
  token_overlap?: number;
  field_differences: Array<Record<string, unknown>>;
  critical_mismatches: Array<Record<string, unknown>>;
  explanation?: string;
  stage_timings?: StageTiming[];
  matched_tokens_preview?: unknown;
}

export interface SettingItem {
  key: string;
  value: Record<string, unknown>;
  description: string | null;
  updated_at: string;
}
