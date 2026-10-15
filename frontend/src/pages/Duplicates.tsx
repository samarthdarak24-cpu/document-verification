import { Link } from "react-router-dom";
import { Copy, FileStack, Layers, Upload } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatTile,
  StatusBadge,
} from "../components/ui";
import { useDuplicates, useDuplicatesSummary } from "../hooks/queries";
import { duplicateLabel, formatDateTime, formatInt, humanize, statusPill } from "../lib/utils";

export default function Duplicates() {
  const summary = useDuplicatesSummary();
  const groups = useDuplicates({ limit: 100 });

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Duplicate detection"
        title="Duplicate groups"
        description="Groups are created only from content fingerprints — never from filenames. An exact group shares a byte-identical file hash; a content group shares a normalized-text hash."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          icon={<Layers />}
          label="Total groups"
          value={summary.isLoading ? "…" : formatInt(summary.data?.total_groups ?? 0)}
        />
        <StatTile
          icon={<Copy />}
          label="Exact duplicates"
          value={summary.isLoading ? "…" : formatInt(summary.data?.exact_groups ?? 0)}
        />
        <StatTile
          icon={<Copy />}
          label="Content duplicates"
          value={summary.isLoading ? "…" : formatInt(summary.data?.content_groups ?? 0)}
        />
        <StatTile
          icon={<FileStack />}
          label="Documents flagged"
          value={summary.isLoading ? "…" : formatInt(summary.data?.documents_flagged ?? 0)}
        />
      </div>

      {summary.data?.by_status ? (
        <Card className="mt-5">
          <CardHeader icon={<Layers />} title="Documents by duplicate status" />
          <CardBody>
            <div className="flex flex-wrap gap-2">
              {Object.entries(summary.data.by_status).map(([status, count]) => (
                <StatusBadge key={status} tone={statusPill(status)} className="px-2.5 py-1">
                  {duplicateLabel(status)} · {count}
                </StatusBadge>
              ))}
            </div>
          </CardBody>
        </Card>
      ) : null}

      <Card className="mt-5 overflow-hidden">
        <CardHeader
          icon={<Layers />}
          title="Detected groups"
          subtitle="Sorted by creation time, newest first"
        />
        {groups.isLoading ? (
          <Spinner label="Loading groups" />
        ) : groups.isError ? (
          <CardBody>
            <ErrorState error={groups.error} />
          </CardBody>
        ) : (groups.data ?? []).length === 0 ? (
          <EmptyState
            icon={<Layers />}
            title="No duplicate groups"
            description="Every stored document is currently unique. Upload a copy of an existing document to see grouping in action."
            action={
              <Link to="/upload">
                <Button variant="primary" icon={<Upload />}>
                  Upload a document
                </Button>
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="dt-table min-w-[560px]">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Fingerprint</th>
                  <th className="text-right">Members</th>
                  <th className="text-right">Created</th>
                </tr>
              </thead>
              <tbody>
                {(groups.data ?? []).map((group) => (
                  <tr key={group.id}>
                    <td>
                      <StatusBadge tone={group.group_type === "exact" ? "rose" : "amber"}>
                        {humanize(group.group_type)}
                      </StatusBadge>
                    </td>
                    <td className="dt-mono text-[11.5px] text-txt-muted">
                      {humanize(group.hash_type)}: {group.hash_value.slice(0, 20)}…
                    </td>
                    <td className="text-right tabular-nums text-[12.5px]">
                      {group.member_count}
                    </td>
                    <td className="text-right text-[12px] text-txt-faint">
                      {formatDateTime(group.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
