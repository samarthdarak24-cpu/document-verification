import { useState } from "react";
import { ArrowRight, GitCompare, Info, Play } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  Spinner,
  StatTile,
  StatusBadge,
} from "../components/ui";
import { useCompare, useDocuments, useFieldDiff } from "../hooks/queries";
import { humanize, pct } from "../lib/utils";

export default function Compare() {
  const documents = useDocuments({ limit: 200 });
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");

  const compare = useCompare();
  const fieldDiff = useFieldDiff();

  const ready = sourceId && targetId && sourceId !== targetId;
  const result = compare.data;
  const diff = fieldDiff.data;

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Dynamic Programming"
        title="Compare two documents"
        description="Runs the bounded LCS and edit-distance comparison between two stored documents, then lists the field values that differ."
      />

      <Card className="mb-5">
        <CardHeader icon={<GitCompare />} title="Select a pair" subtitle="Any two stored documents" />
        <CardBody>
          <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
            <label className="block">
              <span className="dt-label">Original (source)</span>
              <select
                className="dt-select mt-1"
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
              >
                <option value="">Select a document…</option>
                {(documents.data ?? []).map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.filename}
                  </option>
                ))}
              </select>
            </label>
            <span className="pb-2 text-center text-[12px] text-txt-faint">vs</span>
            <label className="block">
              <span className="dt-label">Modified (target)</span>
              <select
                className="dt-select mt-1"
                value={targetId}
                onChange={(event) => setTargetId(event.target.value)}
              >
                <option value="">Select a document…</option>
                {(documents.data ?? []).map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.filename}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="primary"
              icon={<Play />}
              disabled={!ready || compare.isPending}
              onClick={() => {
                compare.mutate({ sourceDocumentId: sourceId, targetDocumentId: targetId });
                fieldDiff.mutate({ sourceDocumentId: sourceId, targetDocumentId: targetId });
              }}
            >
              {compare.isPending ? "Comparing…" : "Compare"}
            </Button>
          </div>
          {sourceId && targetId && sourceId === targetId ? (
            <p className="mt-2.5 text-[12.5px] text-pill-amber-txt">
              Choose two different documents.
            </p>
          ) : null}
        </CardBody>
      </Card>

      {compare.isError ? <ErrorState error={compare.error} /> : null}

      {!result ? (
        <Card>
          <EmptyState
            icon={<GitCompare />}
            title="No comparison yet"
            description="Pick an original and a modified document to see the similarity breakdown."
          />
        </Card>
      ) : (
        <>
          {(() => {
            const comp = (result as any)?.comparison ?? result;
            const overallScore = result?.overall_score ?? comp?.overall_score ?? 0;
            const textSimilarity = result?.text_similarity ?? comp?.text_similarity ?? 0;
            const editSimilarity = result?.edit_similarity ?? comp?.edit_similarity ?? 0;
            const criticalMismatches =
              result?.critical_mismatches ??
              (comp?.field_differences ?? []).filter(
                (fd: any) => fd.critical && (!fd.equal || fd.mismatch)
              );
            const explanation =
              result?.explanation ??
              (result as any)?.verdict ??
              (comp?.notes && comp.notes.length > 0 ? comp.notes.join(" ") : null);
            const fieldDifferences: any[] =
              (diff as any)?.field_differences ??
              (diff as any)?.fields ??
              comp?.field_differences ??
              [];

            return (
              <>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <StatTile label="Overall score" value={pct(overallScore)} />
                  <StatTile label="Text similarity (LCS)" value={pct(textSimilarity)} />
                  <StatTile label="Edit similarity" value={pct(editSimilarity)} />
                  <StatTile
                    label="Critical mismatches"
                    value={criticalMismatches?.length ?? 0}
                  />
                </div>

                {explanation ? (
                  <Card className="mt-5">
                    <CardBody>
                      <p className="text-[12.5px] leading-relaxed text-txt-muted">
                        {explanation}
                      </p>
                    </CardBody>
                  </Card>
                ) : null}

                <Card className="mt-5 overflow-hidden">
                  <CardHeader
                    icon={<ArrowRight />}
                    title="Field differences"
                    subtitle="Values that differ between the two documents"
                  />
                  {fieldDifferences && fieldDifferences.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="dt-table min-w-[560px]">
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Source value</th>
                            <th>Target value</th>
                            <th>Critical</th>
                          </tr>
                        </thead>
                        <tbody>
                          {fieldDifferences.map((entry, index) => (
                            <tr key={index}>
                              <td className="font-medium">
                                {humanize(String(entry.field ?? entry.name ?? "—"))}
                              </td>
                              <td
                                className="max-w-[220px] truncate text-[12.5px] text-txt-muted"
                                title={String(entry.source ?? entry.source_value ?? "")}
                              >
                                {String(entry.source ?? entry.source_value ?? "—")}
                              </td>
                              <td
                                className="max-w-[220px] truncate text-[12.5px] text-txt-muted"
                                title={String(entry.target ?? entry.target_value ?? "")}
                              >
                                {String(entry.target ?? entry.target_value ?? "—")}
                              </td>
                              <td>
                                {entry.critical ? (
                                  <StatusBadge tone="amber">Critical</StatusBadge>
                                ) : (
                                  <span className="text-txt-faint">—</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : fieldDiff.isPending ? (
                    <Spinner label="Diffing fields" />
                  ) : (
                    <CardBody>
                      <p className="py-6 text-center text-[12.5px] text-txt-faint">
                        No field-level differences detected.
                      </p>
                    </CardBody>
                  )}
                </Card>
              </>
            );
          })()}
        </>
      )}

      <Card className="mt-5">
        <CardHeader icon={<Info />} title="What the numbers mean" />
        <CardBody>
          <KeyValue
            items={[
              {
                label: "Text similarity",
                value: "LCS length ÷ max token count — how much content is shared",
              },
              {
                label: "Edit similarity",
                value: "1 − (edit distance ÷ longest sequence) — how few edits separate them",
              },
              {
                label: "Overall score",
                value: "Weighted combination used for the duplicate decision",
              },
              {
                label: "Critical mismatch",
                value: "A template-critical field whose values disagree",
              },
            ]}
          />
        </CardBody>
      </Card>
    </div>
  );
}
