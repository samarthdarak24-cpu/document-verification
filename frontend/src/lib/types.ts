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

// ---- change detection & PDF layout metadata ------------------------------- //
// Mirrors `ChangeReportOut` / `PdfMetadataOut` in backend/app/schemas.

export type ChangeHunkType = "insert" | "delete" | "replace";

/** One character-level edit inside a `replace` hunk. */
export interface CharOperation {
  op: string;
  position: number;
  old: string | null;
  new: string | null;
}

/** One contiguous region of difference between two documents. */
export interface ChangeHunk {
  type: ChangeHunkType;
  removed_text: string;
  added_text: string;
  removed_tokens: string[];
  added_tokens: string[];
  removed_token_count: number;
  added_token_count: number;
  char_edit_distance: number;
  char_operations: CharOperation[];
  original_index: number | null;
  modified_index: number | null;
}

/** A typographic change for a span whose text is otherwise unchanged. */
export interface StyleChange {
  text: string;
  page: number;
  changes: Record<string, unknown>;
}

export interface ChangeReport {
  changed: boolean;
  verdict: string;
  text_similarity: number;
  edit_similarity: number;
  lcs_length: number;
  original_token_count: number;
  modified_token_count: number;
  unchanged_tokens: number;
  added_tokens: number;
  removed_tokens: number;
  hunk_count: number;
  hunks: ChangeHunk[];
  style_change_count: number;
  style_changes: StyleChange[];
  summary: Record<string, unknown>;
  warnings: string[];
  algorithms_executed: string[];
  elapsed_ms: number;
}

export interface ChangeDetectResponse {
  source_document: Record<string, unknown>;
  target_document: Record<string, unknown>;
  report: ChangeReport;
  compared_at: string;
}

export interface TextChangeResponse {
  report: ChangeReport;
  compared_at: string;
}

export interface StyleCount {
  value: string;
  count: number;
}

export interface PdfStyleSummary {
  span_count: number;
  fonts: StyleCount[];
  sizes: StyleCount[];
  colors: StyleCount[];
  styles: {
    bold: number;
    italic: number;
    serif: number;
    monospace: number;
    superscript: number;
  };
}

export interface PdfMetadataResponse {
  document_id: string;
  filename: string;
  page_count: number;
  span_count: number;
  is_encrypted: boolean;
  metadata: Record<string, unknown>;
  style_summary: PdfStyleSummary;
  pages: Array<Record<string, unknown>>;
  warnings: string[];
  truncated: boolean;
  elapsed_ms: number;
}

// ---- pdf-diff & interactive comparison types ------------------------------ //

export interface PdfDiffChange {
  id: string;
  type: "insert" | "delete" | "replace" | "style" | "visual_diagram";
  category: "numerical" | "date" | "registration_no" | "name_entity" | "font_only" | "visual_diagram" | "text";
  scope: "word" | "sentence" | "paragraph" | "formatting" | "diagram";
  section: string;
  page: number;
  removed_text: string;
  added_text: string;
  font_diff?: Record<string, any> | null;
  bbox: [number, number, number, number];
  bbox_original?: [number, number, number, number];
  bbox_modified?: [number, number, number, number];
  pdf_index: number;
  char_edit_distance?: number;
  char_operations?: Array<{ op: string; char?: string; a_char?: string; b_char?: string }>;
  description: string;
}

export interface SectionStat {
  section: string;
  status: "unchanged" | "modified" | "added" | "removed";
  changes_count: number;
  words_added: number;
  words_removed: number;
  style_changes: number;
  visual_changes: number;
  numerical_changes: number;
  date_changes: number;
  snippets: string[];
}

export interface SectionAnalysis {
  all_sections: string[];
  sections: SectionStat[];
  modified_sections_count: number;
  reordering?: {
    shared_sections: string[];
    inversion_count: number;
    reorder_score: number;
    reordered: boolean;
  } | null;
}

export interface PageDiffData {
  page: number;
  original_width: number;
  original_height: number;
  modified_width: number;
  modified_height: number;
  change_count: number;
  changes: PdfDiffChange[];
}

export interface VisualModificationRegion {
  page: number;
  kind: "figure" | "diagram" | "image" | "stamp_or_seal" | "graphic";
  bbox_pixel: [number, number, number, number];
  bbox_pdf: [number, number, number, number];
  area_pixels: number;
  change_severity: "minor" | "moderate" | "significant";
  description: string;
}

export interface ExtendedPdfDiffResult {
  comparison_id: string;
  source_document: {
    id?: string;
    filename: string;
    label: string;
    sha256: string;
    file_size: number;
    page_count: number;
  };
  target_document: {
    id?: string;
    filename: string;
    label: string;
    sha256: string;
    file_size: number;
    page_count: number;
  };
  verdict: string;
  summary: {
    total_changes: number;
    text_changes: number;
    numerical_changes: number;
    date_changes: number;
    registration_no_changes: number;
    name_changes: number;
    font_changes: number;
    visual_diagram_changes: number;
    sections_modified_count: number;
  };
  daa_algorithms: {
    lcs_similarity: number;
    lcs_length: number;
    edit_similarity: number;
    edit_distance: number;
    section_reorder_score: number;
    section_inversions: number;
    algorithms_executed: string[];
    timings_ms: Record<string, number>;
  };
  section_analysis: SectionAnalysis;
  changes: PdfDiffChange[];
  pages: PageDiffData[];
  visual_modifications: {
    visual_modifications_detected: boolean;
    region_count: number;
    modified_images_count: number;
    modified_drawings_count: number;
    regions: VisualModificationRegion[];
  };
  diff_image_base64?: string | null;
  diff_image_url?: string | null;
  elapsed_ms: number;
}

