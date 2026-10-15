/**
 * All server state lives here.
 *
 * Each hook wraps one API call with TanStack Query, so components stay free of
 * fetch logic and caching/invalidation is handled in one place.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export const keys = {
  health: ["health"] as const,
  documents: (params: object) => ["documents", params] as const,
  document: (id: string) => ["document", id] as const,
  documentText: (id: string) => ["document", id, "text"] as const,
  documentStructure: (id: string) => ["document", id, "structure"] as const,
  verifications: (params: object) => ["verifications", params] as const,
  verification: (id: string) => ["verification", id] as const,
  duplicates: (params: object) => ["duplicates", params] as const,
  duplicatesSummary: ["duplicates", "summary"] as const,
  duplicateGroup: (id: string) => ["duplicates", id] as const,
  templates: ["templates"] as const,
  template: (id: string) => ["template", id] as const,
  algorithms: ["algorithms"] as const,
  algorithmHistory: (params: object) => ["algorithms", "history", params] as const,
  benchmarkOptions: ["benchmarks", "options"] as const,
  benchmarks: (params: object) => ["benchmarks", params] as const,
  benchmarkSummary: ["benchmarks", "summary"] as const,
  reports: (params: object) => ["reports", params] as const,
  report: (id: string) => ["report", id] as const,
  analyticsOverview: ["analytics", "overview"] as const,
  analyticsAlgorithms: ["analytics", "algorithms"] as const,
  settings: ["settings"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.health,
    refetchInterval: 30_000,
  });
}

// ---- documents ----------------------------------------------------------- //
export function useDocuments(params: Parameters<typeof api.listDocuments>[0] = {}) {
  return useQuery({
    queryKey: keys.documents(params),
    queryFn: () => api.listDocuments(params),
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: keys.document(id ?? ""),
    queryFn: () => api.getDocument(id!),
    enabled: Boolean(id),
  });
}

export function useDocumentText(id: string | undefined) {
  return useQuery({
    queryKey: keys.documentText(id ?? ""),
    queryFn: () => api.getDocumentText(id!),
    enabled: Boolean(id),
  });
}

export function useDocumentStructure(id: string | undefined) {
  return useQuery({
    queryKey: keys.documentStructure(id ?? ""),
    queryFn: () => api.getDocumentStructure(id!),
    enabled: Boolean(id),
  });
}

export function useUploadDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => api.uploadDocument(form),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["documents"] });
      client.invalidateQueries({ queryKey: ["duplicates"] });
      client.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

export function useDeleteDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteDocument(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["documents"] });
      client.invalidateQueries({ queryKey: ["duplicates"] });
      client.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

// ---- verification -------------------------------------------------------- //
export function useVerifications(params: Parameters<typeof api.listVerifications>[0] = {}) {
  return useQuery({
    queryKey: keys.verifications(params),
    queryFn: () => api.listVerifications(params),
  });
}

export function useVerification(runId: string | undefined) {
  return useQuery({
    queryKey: keys.verification(runId ?? ""),
    queryFn: () => api.getVerification(runId!),
    enabled: Boolean(runId),
  });
}

export function useVerifyDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, templateId }: { documentId: string; templateId?: string }) =>
      api.verifyDocument(documentId, templateId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["documents"] });
      client.invalidateQueries({ queryKey: ["verifications"] });
      client.invalidateQueries({ queryKey: ["duplicates"] });
    },
  });
}

// ---- comparison ---------------------------------------------------------- //
export function useCompare() {
  return useMutation({
    mutationFn: ({
      sourceDocumentId,
      targetDocumentId,
    }: {
      sourceDocumentId: string;
      targetDocumentId: string;
    }) => api.compare(sourceDocumentId, targetDocumentId),
  });
}

export function useFieldDiff() {
  return useMutation({
    mutationFn: ({
      sourceDocumentId,
      targetDocumentId,
    }: {
      sourceDocumentId: string;
      targetDocumentId: string;
    }) => api.fieldDiff(sourceDocumentId, targetDocumentId),
  });
}

// ---- duplicates ---------------------------------------------------------- //
export function useDuplicates(params: Parameters<typeof api.listDuplicates>[0] = {}) {
  return useQuery({
    queryKey: keys.duplicates(params),
    queryFn: () => api.listDuplicates(params),
  });
}

export function useDuplicatesSummary() {
  return useQuery({
    queryKey: keys.duplicatesSummary,
    queryFn: api.duplicatesSummary,
  });
}

export function useDuplicateGroup(id: string | undefined) {
  return useQuery({
    queryKey: keys.duplicateGroup(id ?? ""),
    queryFn: () => api.getDuplicateGroup(id!),
    enabled: Boolean(id),
  });
}

// ---- templates ----------------------------------------------------------- //
export function useTemplates() {
  return useQuery({ queryKey: keys.templates, queryFn: api.listTemplates });
}

export function useTemplate(id: string | undefined) {
  return useQuery({
    queryKey: keys.template(id ?? ""),
    queryFn: () => api.getTemplate(id!),
    enabled: Boolean(id),
  });
}

export function useSaveTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Parameters<typeof api.createTemplate>[0] }) =>
      id ? api.updateTemplate(id, body) : api.createTemplate(body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useDeleteTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["templates"] }),
  });
}

// ---- algorithms ---------------------------------------------------------- //
export function useAlgorithms() {
  return useQuery({ queryKey: keys.algorithms, queryFn: api.listAlgorithms });
}

export function useRunAlgorithm() {
  return useMutation({
    mutationFn: ({ algorithm, inputs }: { algorithm: string; inputs: Record<string, unknown> }) =>
      api.runAlgorithm(algorithm, inputs),
  });
}

export function useAlgorithmHistory(params: Parameters<typeof api.algorithmHistory>[0] = {}) {
  return useQuery({
    queryKey: keys.algorithmHistory(params),
    queryFn: () => api.algorithmHistory(params),
  });
}

// ---- benchmarks ---------------------------------------------------------- //
export function useBenchmarkOptions() {
  return useQuery({ queryKey: keys.benchmarkOptions, queryFn: api.benchmarkOptions });
}

export function useBenchmarks(params: Parameters<typeof api.listBenchmarks>[0] = {}) {
  return useQuery({
    queryKey: keys.benchmarks(params),
    queryFn: () => api.listBenchmarks(params),
  });
}

export function useBenchmarkSummary() {
  return useQuery({ queryKey: keys.benchmarkSummary, queryFn: api.benchmarkSummary });
}

export function useRunBenchmarks() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof api.runBenchmarks>[0]) => api.runBenchmarks(body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["benchmarks"] });
    },
  });
}

// ---- reports ------------------------------------------------------------- //
export function useReports(params: Parameters<typeof api.listReports>[0] = {}) {
  return useQuery({ queryKey: keys.reports(params), queryFn: () => api.listReports(params) });
}

export function useReport(id: string | undefined) {
  return useQuery({
    queryKey: keys.report(id ?? ""),
    queryFn: () => api.getReport(id!),
    enabled: Boolean(id),
  });
}

export function useReportJson(id: string | undefined) {
  return useQuery({
    queryKey: [...keys.report(id ?? ""), "json"],
    queryFn: () => api.reportJson(id!),
    enabled: Boolean(id),
  });
}

export function useGenerateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, format }: { runId: string; format?: "pdf" | "json" }) =>
      api.generateReport(runId, format ?? "pdf"),
    onSuccess: () => client.invalidateQueries({ queryKey: ["reports"] }),
  });
}

// ---- analytics ----------------------------------------------------------- //
export function useAnalyticsOverview() {
  return useQuery({ queryKey: keys.analyticsOverview, queryFn: api.analyticsOverview });
}

export function useAnalyticsAlgorithms() {
  return useQuery({ queryKey: keys.analyticsAlgorithms, queryFn: api.analyticsAlgorithms });
}

// ---- settings ------------------------------------------------------------ //
export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.listSettings });
}

export function useUpdateSetting() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: Record<string, unknown> }) =>
      api.updateSetting(key, value),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings"] }),
  });
}

export function useResetSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.resetSettings(),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings"] }),
  });
}
