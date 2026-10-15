import { useState } from "react";
import { Link } from "react-router-dom";
import { Search, Upload } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useDeleteDocument, useDocuments } from "../hooks/queries";
import {
  duplicateLabel,
  formatBytes,
  formatDateTime,
  formatInt,
  humanize,
  pct,
  statusPill,
} from "../lib/utils";

const DOC_TYPES = [
  "",
  "invoice",
  "mark_sheet",
  "application_form",
  "employment_letter",
  "general_report",
  "certificate",
  "research_paper",
  "unknown",
];

const DUP_STATUSES = ["", "unique", "near_duplicate", "content_duplicate", "exact_duplicate"];

export default function Documents() {
  const [docType, setDocType] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  const documents = useDocuments({
    limit: 100,
    doc_type: docType || undefined,
    duplicate_status: status || undefined,
    search: search || undefined,
  });
  const remove = useDeleteDocument();

  const rows = documents.data ?? [];

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description="Every stored upload, with its extraction confidence, verification status and duplicate classification."
        actions={
          <Link to="/upload">
            <Button variant="primary" icon={<Upload />}>
              Upload document
            </Button>
          </Link>
        }
      />

      <div className="mb-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-txt-faint" />
          <input
            className="dt-input pl-8"
            placeholder="Search filename…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <select className="dt-select" value={docType} onChange={(e) => setDocType(e.target.value)}>
          {DOC_TYPES.map((type) => (
            <option key={type || "all"} value={type}>
              {type ? humanize(type) : "All document types"}
            </option>
          ))}
        </select>
        <select className="dt-select" value={status} onChange={(e) => setStatus(e.target.value)}>
          {DUP_STATUSES.map((value) => (
            <option key={value || "all"} value={value}>
              {value ? duplicateLabel(value) : "All duplicate statuses"}
            </option>
          ))}
        </select>
      </div>

      <Card className="overflow-hidden">
        {documents.isLoading ? (
          <Spinner label="Loading documents" />
        ) : documents.isError ? (
          <CardBody>
            <ErrorState error={documents.error} />
          </CardBody>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No documents match"
            description="Adjust the filters, or upload a document to start the pipeline."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="dt-table min-w-[880px]">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Type</th>
                  <th>Validation</th>
                  <th>Duplicate</th>
                  <th className="text-right">Confidence</th>
                  <th className="text-right">Size</th>
                  <th className="text-right">Uploaded</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((doc) => (
                  <tr key={doc.id}>
                    <td className="max-w-[260px]">
                      <Link
                        to={`/documents/${doc.id}`}
                        className="block truncate text-[13px] font-medium text-txt hover:text-brand"
                        title={doc.filename}
                      >
                        {doc.filename}
                      </Link>
                      <span className="dt-mono text-[11px] text-txt-faint">
                        {doc.file_sha256 ? `${doc.file_sha256.slice(0, 12)}…` : "no hash"}
                      </span>
                    </td>
                    <td className="text-[12.5px] text-txt-muted">{humanize(doc.doc_type)}</td>
                    <td>
                      <StatusBadge tone={statusPill(doc.validation_status)}>
                        {humanize(doc.validation_status)}
                      </StatusBadge>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <StatusBadge tone={statusPill(doc.duplicate_status)}>
                          {duplicateLabel(doc.duplicate_status)}
                        </StatusBadge>
                        {doc.similarity_score !== null && doc.similarity_score !== undefined ? (
                          <span className="text-[11px] tabular-nums text-txt-faint">
                            {pct(doc.similarity_score, 0)}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="text-right tabular-nums text-[12.5px] text-txt-muted">
                      {doc.extraction_confidence !== null ? pct(doc.extraction_confidence, 0) : "—"}
                      {doc.ocr_used ? (
                        <span className="ml-1 text-[10px] uppercase text-pill-amber-txt">OCR</span>
                      ) : null}
                    </td>
                    <td className="text-right tabular-nums text-[12.5px] text-txt-muted">
                      {formatBytes(doc.file_size)}
                    </td>
                    <td className="whitespace-nowrap text-right text-[12px] text-txt-faint">
                      {formatDateTime(doc.uploaded_at)}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="text-[12px] font-medium text-pill-rose-txt hover:underline disabled:opacity-40"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (confirm(`Delete "${doc.filename}" and its reports?`)) {
                            remove.mutate(doc.id);
                          }
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {rows.length > 0 ? (
        <p className="mt-3 text-meta text-txt-faint">{formatInt(rows.length)} document(s) shown.</p>
      ) : null}
    </div>
  );
}
