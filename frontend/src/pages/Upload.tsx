import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { FileUp, Play, Trash2, Upload as UploadIcon } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  KeyValue,
  PageHeader,
  StatusBadge,
} from "../components/ui";
import { useTemplates, useUploadDocument } from "../hooks/queries";
import type { UploadResponse } from "../lib/types";
import { cn, duplicateLabel, formatMs, humanize, statusPill } from "../lib/utils";

const DOC_TYPES = [
  { value: "invoice", label: "Invoice / bill" },
  { value: "mark_sheet", label: "Mark sheet / transcript" },
  { value: "application_form", label: "Application form" },
  { value: "employment_letter", label: "Employment letter" },
  { value: "general_report", label: "General report" },
  { value: "certificate", label: "Certificate" },
  { value: "research_paper", label: "Research paper / publication" },
];

const ACCEPT = ".pdf,.docx,.png,.jpg,.jpeg,.txt";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("invoice");
  const [templateId, setTemplateId] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const templates = useTemplates();
  const upload = useUploadDocument();
  const result: UploadResponse | undefined = upload.data;

  function submit() {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    if (templateId) form.append("template_id", templateId);
    upload.mutate(form);
  }

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Pipeline"
        title="Upload a document"
        description="The file is stored locally, text is extracted, fields are validated, duplicates are detected against every stored document of the same type, and a full verification run is recorded."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.05fr_1fr]">
        <Card className="overflow-hidden">
          <CardHeader icon={<UploadIcon />} title="Select a file" subtitle={`Accepted: ${ACCEPT}`} />
          <CardBody className="space-y-3.5">
            <div
              role="button"
              tabIndex={0}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragOver(false);
                const dropped = event.dataTransfer.files?.[0];
                if (dropped) setFile(dropped);
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-card border border-dashed px-6 py-9 text-center transition-colors duration-fast",
                dragOver
                  ? "border-brand bg-brand-soft"
                  : "border-line-strong hover:border-brand/60 hover:bg-canvas-soft"
              )}
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-brand">
                <FileUp className="h-[18px] w-[18px]" />
              </span>
              <p className="mt-1 text-[13px] font-medium text-txt">
                {file ? file.name : "Drop a file here, or click to browse"}
              </p>
              <p className="text-[11.5px] text-txt-faint">
                {file
                  ? `${(file.size / 1024).toFixed(1)} KB · ${file.type || "unknown type"}`
                  : "PDF, DOCX, PNG, JPG or TXT — up to 25 MB"}
              </p>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="dt-label">Document type</span>
                <select
                  className="dt-select mt-1"
                  value={docType}
                  onChange={(event) => setDocType(event.target.value)}
                >
                  {DOC_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="dt-label">Template</span>
                <select
                  className="dt-select mt-1"
                  value={templateId}
                  onChange={(event) => setTemplateId(event.target.value)}
                >
                  <option value="">Auto (custom template)</option>
                  {(templates.data ?? []).map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name} ({tpl.category})
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                icon={<Play />}
                disabled={!file || upload.isPending}
                onClick={submit}
              >
                {upload.isPending ? "Processing…" : "Run verification"}
              </Button>
              {file ? (
                <Button
                  variant="ghost"
                  icon={<Trash2 />}
                  disabled={upload.isPending}
                  onClick={() => {
                    setFile(null);
                    upload.reset();
                  }}
                >
                  Clear
                </Button>
              ) : null}
            </div>

            {upload.isError ? <ErrorState error={upload.error} /> : null}
          </CardBody>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader
            icon={<Play />}
            title="Verification result"
            subtitle={
              result ? "Produced by the algorithms, with real timings" : "Results appear here"
            }
          />
          <CardBody>
            {!result ? (
              <p className="py-10 text-center text-[12.5px] text-txt-faint">
                Upload a document to see the outcome, stage timings, findings and duplicate
                matches.
              </p>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge tone={statusPill(result.run.outcome.toLowerCase())}>
                    {humanize(result.run.outcome)}
                  </StatusBadge>
                  <StatusBadge tone={statusPill(result.run.validation_status)}>
                    Validation: {humanize(result.run.validation_status)}
                  </StatusBadge>
                  <StatusBadge tone={statusPill(result.run.duplicate_status)}>
                    {duplicateLabel(result.run.duplicate_status)}
                  </StatusBadge>
                  <StatusBadge tone="blue">
                    {humanize(result.run.review_recommendation)}
                  </StatusBadge>
                </div>

                {result.run.explanation ? (
                  <p className="rounded-panel border border-line bg-canvas-section px-3.5 py-3 text-[12.5px] leading-relaxed text-txt-muted">
                    {result.run.explanation}
                  </p>
                ) : null}

                <KeyValue
                  items={[
                    { label: "Pages", value: result.document.page_count ?? "—" },
                    { label: "Extraction", value: humanize(result.document.extraction_method) },
                    {
                      label: "Confidence",
                      value:
                        result.document.extraction_confidence !== null
                          ? `${(result.document.extraction_confidence * 100).toFixed(0)}%`
                          : "—",
                    },
                    { label: "OCR used", value: result.document.ocr_used ? "Yes" : "No" },
                    { label: "Processing time", value: formatMs(result.run.processing_ms) },
                    { label: "Pipeline stages", value: result.stage_timings.length },
                  ]}
                />

                {result.warnings.length > 0 ? (
                  <div className="rounded-panel border border-pill-amber bg-pill-amber/40 px-3.5 py-3">
                    <p className="dt-label text-pill-amber-txt">Warnings</p>
                    <ul className="mt-1.5 space-y-1 text-[12.5px] text-txt-muted">
                      {result.warnings.map((warning, index) => (
                        <li key={index}>• {warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div>
                  <p className="dt-label mb-2">Stage timings (topological order)</p>
                  <ol className="space-y-1.5">
                    {result.stage_timings.map((stage) => (
                      <li
                        key={stage.stage}
                        className="flex items-baseline justify-between gap-3 border-b border-line-soft pb-1.5 last:border-b-0"
                      >
                        <span
                          className="min-w-0 truncate text-[12.5px] text-txt-muted"
                          title={stage.label}
                        >
                          {stage.label}
                        </span>
                        <span className="dt-mono shrink-0 tabular-nums text-txt-faint">
                          {formatMs(stage.elapsed_ms)}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="flex gap-2">
                  <Link to={`/documents/${result.document.id}`}>
                    <Button variant="primary">Open document</Button>
                  </Link>
                  <Link to="/duplicates">
                    <Button variant="ghost">View duplicates</Button>
                  </Link>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
