/**
 * Thin typed wrapper over the DocuTrace REST API.
 *
 * All requests go to a relative `/api` prefix: in development Vite proxies that
 * to the FastAPI server on :8000, so no base URL or CORS configuration is needed.
 */

import type {
  AlgorithmInfo,
  AlgorithmRunOut,
  AnalyticsOverview,
  BenchmarkRunResponse,
  ChangeDetectResponse,
  CompareResult,
  DocumentDetailOut,
  DocumentOut,
  DocumentTextOut,
  DuplicateGroupOut,
  DuplicatesSummary,
  ExtendedPdfDiffResult,
  HealthResponse,
  PdfMetadataResponse,
  ReportOut,
  SettingItem,
  TemplateOut,
  TextChangeResponse,
  UploadResponse,
  VerificationDetailOut,
  VerificationRunOut,
} from "./types";

/** Shape of `GET /api/settings`: a key -> value map, plus the defaults. */
interface SettingsResponse {
  settings: Record<string, Record<string, unknown>>;
  defaults?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    let code: string | undefined;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) {
        detail = body.detail
          .map((item: { msg?: string; loc?: string[] }) =>
            item.msg ? `${item.loc?.join(".") ?? ""}: ${item.msg}`.trim() : "Invalid input"
          )
          .join("; ");
      }
      code = body?.code;
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

function unwrapItems<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && "items" in payload) {
    const items = (payload as { items: unknown }).items;
    if (Array.isArray(items)) return items as T[];
  }
  return [];
}

function query(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  // ---- documents --------------------------------------------------------- //
  listDocuments: async (params: {
    limit?: number;
    offset?: number;
    doc_type?: string;
    upload_status?: string;
    duplicate_status?: string;
    validation_status?: string;
    search?: string;
  } = {}) =>
    unwrapItems<DocumentOut>(
      await request<unknown>(`/documents${query(params as Record<string, string | number>)}`)
    ),

  getDocument: (id: string) => request<DocumentDetailOut>(`/documents/${id}`),
  getDocumentText: (id: string) => request<DocumentTextOut>(`/documents/${id}/text`),
  getDocumentStructure: (id: string) =>
    request<Record<string, unknown>>(`/documents/${id}/structure`),

  uploadDocument: (form: FormData) =>
    request<UploadResponse>("/documents/upload", { method: "POST", body: form }),

  deleteDocument: (id: string) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }),

  documentDownloadUrl: (id: string) => `/api/documents/${id}/download`,
  documentPreviewUrl: (id: string) => `/api/documents/${id}/preview`,

  // ---- verification ------------------------------------------------------ //
  // `GET /verifications` returns a page of *flat* run rows (`VerificationRunOut`),
  // not nested detail objects. Only `GET /verifications/{id}` returns the nested
  // `VerificationDetailOut` with its findings and matches.
  listVerifications: async (params: { page_size?: number; document_id?: string } = {}) =>
    unwrapItems<VerificationRunOut>(
      await request<unknown>(`/verifications${query(params)}`)
    ),

  getVerification: (runId: string) =>
    request<VerificationDetailOut>(`/verifications/${runId}`),

  verifyDocument: (documentId: string, templateId?: string) =>
    request<UploadResponse>(`/verify/${documentId}`, {
      method: "POST",
      body: JSON.stringify(templateId ? { template_id: templateId } : {}),
    }),

  // ---- comparison -------------------------------------------------------- //
  compare: (sourceDocumentId: string, targetDocumentId: string) =>
    request<CompareResult>("/compare", {
      method: "POST",
      body: JSON.stringify({
        source_document_id: sourceDocumentId,
        target_document_id: targetDocumentId,
      }),
    }),

  fieldDiff: (sourceDocumentId: string, targetDocumentId: string) =>
    request<CompareResult>("/compare/field-diff", {
      method: "POST",
      body: JSON.stringify({
        source_document_id: sourceDocumentId,
        target_document_id: targetDocumentId,
      }),
    }),

  comparePdfDiff: (params: {
    sourceDocumentId?: string;
    targetDocumentId?: string;
    originalFile?: File;
    modifiedFile?: File;
    renderImage?: boolean;
  }) => {
    if (params.originalFile && params.modifiedFile) {
      const formData = new FormData();
      formData.append("original_file", params.originalFile);
      formData.append("modified_file", params.modifiedFile);
      formData.append("render_image", String(params.renderImage ?? true));
      return request<ExtendedPdfDiffResult>("/compare/pdf-diff", {
        method: "POST",
        body: formData,
      });
    } else if (params.sourceDocumentId && params.targetDocumentId) {
      return request<ExtendedPdfDiffResult>("/compare/pdf-diff", {
        method: "POST",
        body: JSON.stringify({
          source_document_id: params.sourceDocumentId,
          target_document_id: params.targetDocumentId,
          render_image: params.renderImage ?? true,
        }),
      });
    }
    throw new Error("Provide either original and modified files, or document IDs.");
  },

  pageRenderUrl: (docOrTempId: string, page: number, dpi: number = 150) =>
    `/api/compare/page-render/${encodeURIComponent(docOrTempId)}/${page}?dpi=${dpi}`,

  diffImageUrl: (comparisonId: string) =>
    `/api/compare/diff-image/${comparisonId}`,

  exportPdfDiffReport: async (payload: unknown) => {
    const response = await fetch("/api/compare/pdf-diff/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Failed to generate PDF diff report");
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `docutrace-diff-report.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  // ---- change detection & layout metadata -------------------------------- //
  // `POST /changes/detect` aligns the two documents with LCS and refines each
  // changed region with edit distance; when both are PDFs it also compares the
  // span-level typography (font / size / colour / position).
  detectChanges: (
    sourceDocumentId: string,
    targetDocumentId: string,
    compareMetadata = true
  ) =>
    request<ChangeDetectResponse>("/changes/detect", {
      method: "POST",
      body: JSON.stringify({
        source_document_id: sourceDocumentId,
        target_document_id: targetDocumentId,
        compare_metadata: compareMetadata,
      }),
    }),

  // Raw-text variant — no stored file required.
  detectTextChanges: (originalText: string, modifiedText: string) =>
    request<TextChangeResponse>("/changes/text", {
      method: "POST",
      body: JSON.stringify({
        original_text: originalText,
        modified_text: modifiedText,
      }),
    }),

  // 400s for non-PDF documents (span metadata has no meaning for a DOCX/image).
  getPdfMetadata: (id: string, includeSpans = false) =>
    request<PdfMetadataResponse>(
      `/documents/${id}/pdf-metadata${includeSpans ? "?include_spans=true" : ""}`
    ),

  // ---- duplicates -------------------------------------------------------- //
  listDuplicates: async (params: { limit?: number; group_type?: string } = {}) =>
    unwrapItems<DuplicateGroupOut>(
      await request<unknown>(`/duplicates${query(params)}`)
    ),

  duplicatesSummary: () => request<DuplicatesSummary>("/duplicates/summary"),
  getDuplicateGroup: (groupId: string) =>
    request<Record<string, unknown>>(`/duplicates/${groupId}`),

  // ---- templates --------------------------------------------------------- //
  listTemplates: async () => unwrapItems<TemplateOut>(await request<unknown>("/templates")),
  getTemplate: (id: string) => request<TemplateOut>(`/templates/${id}`),
  createTemplate: (body: Partial<TemplateOut>) =>
    request<TemplateOut>("/templates", { method: "POST", body: JSON.stringify(body) }),
  updateTemplate: (id: string, body: Partial<TemplateOut>) =>
    request<TemplateOut>(`/templates/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTemplate: (id: string) => request<void>(`/templates/${id}`, { method: "DELETE" }),

  // ---- algorithms -------------------------------------------------------- //
  listAlgorithms: async () =>
    unwrapItems<AlgorithmInfo>(await request<unknown>("/algorithms")),

  runAlgorithm: (algorithm: string, inputs: Record<string, unknown>) =>
    request<Record<string, unknown>>("/algorithms/run", {
      method: "POST",
      body: JSON.stringify({ algorithm, inputs }),
    }),

  algorithmHistory: async (params: { limit?: number; algorithm?: string } = {}) =>
    unwrapItems<AlgorithmRunOut>(await request<unknown>(`/algorithms/history${query(params)}`)),

  // ---- benchmarks -------------------------------------------------------- //
  benchmarkOptions: () =>
    request<{ algorithms: string[]; datasets: string[]; sizes: number[] }>(
      "/benchmarks/options"
    ),
  listBenchmarks: async (params: { limit?: number; algorithm?: string } = {}) =>
    unwrapItems<BenchmarkRunResponse["rows"][number]>(
      await request<unknown>(`/benchmarks${query(params)}`)
    ),
  benchmarkSummary: () => request<Record<string, unknown>>("/benchmarks/summary"),
  runBenchmarks: (body: {
    algorithms?: string[];
    datasets?: string[];
    sizes?: number[];
    repeats?: number;
    persist?: boolean;
  }) => request<BenchmarkRunResponse>("/benchmarks/run", { method: "POST", body: JSON.stringify(body) }),

  // ---- reports ----------------------------------------------------------- //
  listReports: async (params: { limit?: number } = {}) =>
    unwrapItems<ReportOut>(await request<unknown>(`/reports${query(params)}`)),
  getReport: (id: string) => request<ReportOut>(`/reports/${id}`),
  reportJson: (id: string) => request<Record<string, unknown>>(`/reports/${id}/json`),
  reportDownloadUrl: (id: string) => `/api/reports/${id}/download`,
  generateReport: (runId: string, format: "pdf" | "json" = "pdf") =>
    request<{ report: ReportOut }>(`/reports/${runId}/generate`, {
      method: "POST",
      body: JSON.stringify({ format }),
    }),

  // ---- analytics --------------------------------------------------------- //
  analyticsOverview: () => request<AnalyticsOverview>("/analytics/overview"),
  analyticsAlgorithms: () => request<Record<string, unknown>>("/analytics/algorithms"),

  // ---- settings ---------------------------------------------------------- //
  // `GET /settings` returns a *map* of key -> value plus the defaults, not a
  // list. `unwrapItems` would see no "items" array and return [], so the page
  // rendered "no settings" while the backend held six of them. Normalise the
  // map into the row shape the editor expects.
  listSettings: async () => {
    const payload = await request<SettingsResponse>("/settings");
    return Object.entries(payload.settings ?? {}).map(([key, value]) => ({
      key,
      value: (value ?? {}) as Record<string, unknown>,
      description: null,
      updated_at: "",
    }));
  },
  updateSetting: (key: string, value: Record<string, unknown>) =>
    request<SettingItem>(`/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),
  resetSettings: () =>
    request<{ settings: Record<string, unknown> }>("/settings/reset", {
      method: "POST",
    }),
};
