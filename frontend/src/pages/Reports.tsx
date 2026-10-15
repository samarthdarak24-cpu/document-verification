import { useState } from "react";
import { Download, FileJson, FileText } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useReport, useReportJson, useReports } from "../hooks/queries";
import { cn, formatDateTime, humanize } from "../lib/utils";

export default function Reports() {
  const reports = useReports({ limit: 100 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const report = useReport(selectedId ?? undefined);
  const json = useReportJson(selectedId ?? undefined);

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Artifacts"
        title="Reports"
        description="Every verification run can produce a PDF and a JSON report. Both are rebuilt from the stored run, so they reflect exactly what the algorithms measured."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(240px,300px)_1fr]">
        <Card className="overflow-hidden self-start">
          <CardHeader
            icon={<FileText />}
            title="Generated reports"
            subtitle={`${reports.data?.length ?? 0} total`}
          />
          {reports.isLoading ? (
            <Spinner label="Loading reports" />
          ) : reports.isError ? (
            <CardBody>
              <ErrorState error={reports.error} />
            </CardBody>
          ) : (reports.data ?? []).length === 0 ? (
            <EmptyState
              icon={<FileText />}
              title="No reports yet"
              description="Upload a document, then generate a report from its detail page."
            />
          ) : (
            <ul>
              {(reports.data ?? []).map((item) => (
                <li key={item.id} className="border-b border-line-soft last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={cn(
                      "w-full px-4 py-2.5 text-left transition-colors duration-fast",
                      selectedId === item.id ? "bg-brand-soft" : "hover:bg-canvas-soft"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "text-[12.5px] font-medium",
                          selectedId === item.id ? "text-brand" : "text-txt"
                        )}
                      >
                        {humanize(item.report_type)}
                      </span>
                      <span className="shrink-0 text-[11px] text-txt-faint">
                        {formatDateTime(item.created_at)}
                      </span>
                    </div>
                    <p className="dt-mono mt-0.5 text-[11px] text-txt-faint">
                      {item.report_uuid.slice(0, 18)}…
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="overflow-hidden">
          {!selectedId ? (
            <CardBody>
              <p className="py-16 text-center text-[12.5px] text-txt-faint">
                Select a report to preview its contents and download it.
              </p>
            </CardBody>
          ) : (
            <>
              <CardHeader
                icon={<FileText />}
                title="Report detail"
                subtitle={report.data ? formatDateTime(report.data.created_at) : undefined}
                actions={
                  <div className="flex gap-1.5">
                    <a href={`/api/reports/${selectedId}/download`} target="_blank" rel="noreferrer">
                      <Button size="sm" icon={<Download />}>
                        PDF
                      </Button>
                    </a>
                    {report.data?.run_id ? (
                      <a href={`/api/reports/${selectedId}/json`} target="_blank" rel="noreferrer">
                        <Button size="sm" icon={<FileJson />}>
                          JSON
                        </Button>
                      </a>
                    ) : null}
                  </div>
                }
              />
              <CardBody>
                {report.isLoading || json.isLoading ? (
                  <Spinner label="Loading report" />
                ) : report.isError ? (
                  <ErrorState error={report.error} />
                ) : (
                  <div className="space-y-3.5">
                    <div className="flex flex-wrap gap-1.5">
                      <StatusBadge tone="blue">
                        {humanize(report.data?.report_type ?? "")}
                      </StatusBadge>
                      {report.data?.run_id ? (
                        <StatusBadge tone="slate">Run-linked</StatusBadge>
                      ) : null}
                    </div>
                    {report.data?.relative_path ? (
                      <p className="dt-mono text-[11px] text-txt-faint">
                        {report.data.relative_path}
                      </p>
                    ) : null}
                    <div>
                      <p className="dt-label mb-2">JSON preview</p>
                      {json.isError ? (
                        <ErrorState error={json.error} />
                      ) : (
                        <pre className="max-h-[440px] overflow-auto rounded-panel border border-line bg-canvas-section p-3.5 font-mono text-[11.5px] leading-relaxed text-txt-muted">
                          {json.data ? JSON.stringify(json.data, null, 2) : "—"}
                        </pre>
                      )}
                    </div>
                  </div>
                )}
              </CardBody>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
