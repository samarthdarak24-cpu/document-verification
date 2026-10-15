import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  Clock3,
  Download,
  ExternalLink,
  FileText,
  GitFork,
  Layers,
  Play,
  ScrollText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "../lib/api";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  ProgressBar,
  Spinner,
  StatTile,
  StatusBadge,
} from "../components/ui";
import {
  useDocument,
  useDocumentStructure,
  useDocumentText,
  useGenerateReport,
  useVerifications,
  useVerifyDocument,
} from "../hooks/queries";
import {
  duplicateLabel,
  formatBytes,
  formatDateTime,
  formatMs,
  humanize,
  pct,
  statusPill,
} from "../lib/utils";

export default function DocumentDetail() {
  const { id = "" } = useParams();
  const document = useDocument(id);
  const text = useDocumentText(id);
  const structure = useDocumentStructure(id);
  const verifications = useVerifications({ document_id: id, page_size: 10 });
  const verify = useVerifyDocument();
  const report = useGenerateReport();

  if (document.isLoading) return <Spinner label="Loading document" />;
  if (document.isError) return <ErrorState error={document.error} />;
  if (!document.data) return <EmptyState title="Document not found" />;

  const doc = document.data;
  const latestRun = verifications.data?.[0];

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Document"
        title={doc.filename}
        description={`Uploaded ${formatDateTime(doc.uploaded_at)} · ${humanize(doc.doc_type)}`}
        actions={
          <>
            <Button
              variant="primary"
              icon={<Play />}
              disabled={verify.isPending}
              onClick={() => verify.mutate({ documentId: id })}
            >
              {verify.isPending ? "Re-verifying…" : "Re-verify"}
            </Button>
            {latestRun ? (
              <Button
                variant="secondary"
                icon={<ScrollText />}
                disabled={report.isPending}
                onClick={() => report.mutate({ runId: latestRun.id, format: "pdf" })}
              >
                {report.isPending ? "Generating…" : "Generate PDF"}
              </Button>
            ) : null}
            <a
              className="dt-btn-secondary"
              href={api.documentDownloadUrl(id)}
              download={doc.filename}
            >
              <Download className="h-4 w-4" />
              Download
            </a>
          </>
        }
      />

      {verify.isError ? <ErrorState error={verify.error} /> : null}
      {report.isError ? <ErrorState error={report.error} /> : null}
      {report.isSuccess ? (
        <div className="mb-5 rounded-panel border border-pill-green bg-pill-green/40 px-4 py-2.5 text-[13px] text-pill-green-txt">
          PDF report generated.{" "}
          <Link to="/reports" className="font-medium underline">
            Open Reports
          </Link>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          icon={<Sparkles />}
          label="Extraction"
          value={pct(doc.extraction_confidence, 0)}
          hint={humanize(doc.extraction_method)}
        />
        <StatTile
          icon={<Layers />}
          label="Pages"
          value={doc.page_count ?? "—"}
          hint={doc.ocr_used ? "OCR used" : "Digital text"}
        />
        <StatTile
          icon={<FileText />}
          label="File size"
          value={formatBytes(doc.file_size)}
          hint={doc.mime_type ?? undefined}
        />
        <StatTile
          icon={<Clock3 />}
          label="Processing"
          value={formatMs(doc.processing_duration_ms)}
          hint={`${doc.verification_run_count} run(s)`}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader
            icon={<ShieldCheck />}
            title="Verification status"
            subtitle="Three independent verdicts"
          />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap gap-1.5">
              <StatusBadge tone={statusPill(doc.validation_status)}>
                Validation: {humanize(doc.validation_status)}
              </StatusBadge>
              <StatusBadge tone={statusPill(doc.duplicate_status)}>
                Duplicate: {duplicateLabel(doc.duplicate_status)}
              </StatusBadge>
              {latestRun ? (
                <StatusBadge tone={statusPill(latestRun.review_recommendation)}>
                  {humanize(latestRun.review_recommendation)}
                </StatusBadge>
              ) : null}
            </div>

            {latestRun?.explanation ? (
              <p className="rounded-panel border border-line bg-canvas-section px-3.5 py-3 text-[13px] leading-relaxed text-txt-muted">
                {latestRun.explanation}
              </p>
            ) : null}

            {doc.similarity_score !== null && doc.similarity_score !== undefined ? (
              <div>
                <div className="mb-1.5 flex items-baseline justify-between">
                  <span className="dt-label">Highest similarity</span>
                  <span className="text-[13px] font-semibold tabular-nums text-txt">
                    {pct(doc.similarity_score)}
                  </span>
                </div>
                <ProgressBar value={doc.similarity_score} />
              </div>
            ) : null}

            <KeyValue
              items={[
                {
                  label: "File SHA-256",
                  value: (
                    <span className="dt-mono text-[11px]">
                      {doc.file_sha256?.slice(0, 32) ?? "—"}…
                    </span>
                  ),
                },
                {
                  label: "Normalized hash",
                  value: (
                    <span className="dt-mono text-[11px]">
                      {doc.normalized_text_hash?.slice(0, 32) ?? "—"}…
                    </span>
                  ),
                },
                { label: "Upload status", value: humanize(doc.upload_status) },
                { label: "Error", value: doc.error_message ?? "None" },
              ]}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            icon={<GitFork />}
            title="Extracted fields"
            subtitle="Located by KMP, aligned by bipartite matching"
          />
          {doc.fields.length === 0 ? (
            <EmptyState
              title="No fields extracted"
              description="This document type has no template fields, or none were found."
            />
          ) : (
            <table className="dt-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {doc.fields.map((field) => (
                  <tr key={field.id}>
                    <td className="font-medium text-txt">{humanize(field.field_name)}</td>
                    <td className="max-w-[220px] truncate" title={field.field_value ?? ""}>
                      {field.field_value ?? <span className="text-txt-faint">—</span>}
                    </td>
                    <td>
                      <StatusBadge tone={statusPill(field.status)}>
                        {humanize(field.status)}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_1fr]">
        <DocumentViewer
          documentId={id}
          filename={doc.filename}
          mimeType={doc.mime_type}
          text={text}
        />

        <Card>
          <CardHeader
            icon={<GitFork />}
            title="Detected structure"
            subtitle="DFS / BFS over the section tree (Unit I)"
          />
          <CardBody>
            {structure.isLoading ? (
              <Spinner label="Analysing structure" />
            ) : structure.isError ? (
              <ErrorState error={structure.error} />
            ) : (
              <StructureView data={structure.data ?? {}} />
            )}
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader
          icon={<Clock3 />}
          title="Verification runs"
          subtitle="Each re-verification is recorded separately"
        />
        {verifications.isLoading ? (
          <Spinner label="Loading runs" />
        ) : (verifications.data ?? []).length === 0 ? (
          <EmptyState title="No runs recorded" />
        ) : (
          <table className="dt-table">
            <thead>
              <tr>
                <th>Outcome</th>
                <th>Validation</th>
                <th>Duplicate</th>
                <th>Recommendation</th>
                <th className="text-right">Processing</th>
                <th className="text-right">Started</th>
              </tr>
            </thead>
            <tbody>
              {(verifications.data ?? []).map((run) => (
                <tr key={run.id}>
                  <td>
                    <StatusBadge tone={statusPill(run.outcome.toLowerCase())}>
                      {humanize(run.outcome)}
                    </StatusBadge>
                  </td>
                  <td>{humanize(run.validation_status)}</td>
                  <td>{humanize(run.duplicate_status)}</td>
                  <td>{humanize(run.review_recommendation)}</td>
                  <td className="text-right tabular-nums">{formatMs(run.processing_ms)}</td>
                  <td className="text-right text-[12px] text-txt-faint">
                    {formatDateTime(run.started_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

/**
 * Inline viewer for the stored original file.
 *
 * The file is served by `GET /api/documents/{id}/preview`, which sends
 * `Content-Disposition: inline` so the browser renders it instead of
 * downloading it. PDFs and images are embedded directly; anything else falls
 * back to a download prompt, since no browser can render it in-page.
 */
function DocumentViewer({
  documentId,
  filename,
  mimeType,
  text,
}: {
  documentId: string;
  filename: string;
  mimeType: string | null;
  text: ReturnType<typeof useDocumentText>;
}) {
  const [tab, setTab] = useState<"file" | "text">("file");
  const previewUrl = api.documentPreviewUrl(documentId);
  const isImage = (mimeType ?? "").startsWith("image/");
  const isPdf = (mimeType ?? "").includes("pdf");
  const canEmbed = isPdf || isImage;

  return (
    <Card className="flex flex-col">
      <CardHeader
        icon={<FileText />}
        title="Document viewer"
        subtitle={filename}
        actions={
          <>
            <SegmentedTabs value={tab} onChange={setTab} />
            <a
              className="dt-btn-ghost dt-btn-sm"
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              title="Open in a new tab"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          </>
        }
      />
      <CardBody className="flex-1">
        {tab === "file" ? (
          canEmbed ? (
            isImage ? (
              <img
                src={previewUrl}
                alt={filename}
                className="mx-auto max-h-[560px] w-auto rounded-panel border border-line"
              />
            ) : (
              <iframe
                src={previewUrl}
                title={filename}
                className="h-[560px] w-full rounded-panel border border-line bg-canvas-section"
              />
            )
          ) : (
            <div className="flex h-[560px] flex-col items-center justify-center gap-3 rounded-panel border border-dashed border-line bg-canvas-section px-6 text-center">
              <FileText className="h-7 w-7 text-txt-faint" />
              <p className="text-[13px] text-txt-muted">
                A {mimeType || "file"} cannot be previewed in the browser.
              </p>
              <a className="dt-btn-secondary" href={previewUrl} download={filename}>
                <Download className="h-4 w-4" />
                Download instead
              </a>
            </div>
          )
        ) : text.isLoading ? (
          <Spinner label="Loading text" />
        ) : text.isError ? (
          <ErrorState error={text.error} />
        ) : text.data?.original_excerpt ? (
          <>
            <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap rounded-panel border border-line bg-canvas-section p-3.5 font-mono text-[12px] leading-relaxed text-txt-muted">
              {text.data.original_excerpt}
            </pre>
            {text.data.warnings.length > 0 ? (
              <ul className="mt-3 space-y-1 text-[12px] text-pill-amber-txt">
                {text.data.warnings.map((w, i) => (
                  <li key={i}>• {w}</li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <p className="py-8 text-center text-sm text-txt-faint">
            No text could be extracted.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

/** Two-option segmented control used by the document viewer. */
function SegmentedTabs({
  value,
  onChange,
}: {
  value: "file" | "text";
  onChange: (next: "file" | "text") => void;
}) {
  const options: Array<{ id: "file" | "text"; label: string }> = [
    { id: "file", label: "Original file" },
    { id: "text", label: "Extracted text" },
  ];
  return (
    <div className="flex items-center rounded-control border border-line bg-canvas-section p-0.5">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          className={
            value === option.id
              ? "rounded-[7px] bg-brand px-2.5 py-1 text-[12px] font-medium text-white"
              : "rounded-[7px] px-2.5 py-1 text-[12px] font-medium text-txt-muted hover:text-txt"
          }
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function StructureView({ data }: { data: Record<string, unknown> }) {
  const uncertain = Boolean(data.uncertain);
  const validation = (data.validation ?? {}) as {
    present?: string[];
    missing?: string[];
    order_ok?: boolean;
  };
  const dfs = data.dfs as { visited_count?: number } | undefined;
  const bfs = data.bfs as { visited_count?: number } | undefined;

  return (
    <div className="space-y-4">
      {uncertain ? (
        <p className="flex gap-2 rounded-panel border border-pill-amber bg-pill-amber/40 px-3.5 py-3 text-[12.5px] text-pill-amber-txt">
          <AlertTriangle className="mt-px h-4 w-4 shrink-0" />
          <span>
            The structure could not be determined reliably from this document, so no sections are
            reported as missing.
          </span>
        </p>
      ) : null}

      <KeyValue
        items={[
          { label: "Heuristic", value: humanize(String(data.heuristic ?? "none")) },
          { label: "DFS visited", value: dfs?.visited_count ?? "—" },
          { label: "BFS visited", value: bfs?.visited_count ?? "—" },
          {
            label: "Order correct",
            value:
              validation.order_ok === undefined ? "—" : validation.order_ok ? "Yes" : "No",
          },
        ]}
      />

      {validation.present && validation.present.length > 0 ? (
        <div>
          <p className="dt-label mb-1.5">Sections present</p>
          <div className="flex flex-wrap gap-1.5">
            {validation.present.map((s) => (
              <StatusBadge key={s} tone="green">
                {s}
              </StatusBadge>
            ))}
          </div>
        </div>
      ) : null}

      {validation.missing && validation.missing.length > 0 ? (
        <div>
          <p className="dt-label mb-1.5">Sections missing</p>
          <div className="flex flex-wrap gap-1.5">
            {validation.missing.map((s) => (
              <StatusBadge key={s} tone="rose">
                {s}
              </StatusBadge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
