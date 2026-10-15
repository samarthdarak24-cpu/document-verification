/**
 * Projects table.
 *
 * Mirrors the reference: a bordered container with a toolbar (list icon +
 * heading, a "This Week" style range dropdown, and a rounded "See All" button),
 * a light grey header row and compact ~44px rows with pastel status pills.
 *
 * Bound to real DocuTrace documents — the "task" is the file, the assignee is
 * derived from the file, and the status is the verification outcome.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  ListFilter,
  MessageSquare,
  Paperclip,
  Search,
  Users,
} from "lucide-react";
import { Avatar, StatusBadge } from "./ui";
import { cn, duplicateLabel, formatInt, statusPill } from "../lib/utils";
import type { DocumentOut } from "../lib/types";

type RangeKey = "all" | "today" | "week" | "month";

const RANGES: Array<{ key: RangeKey; label: string; days: number | null }> = [
  { key: "all", label: "All time", days: null },
  { key: "today", label: "Today", days: 1 },
  { key: "week", label: "This week", days: 7 },
  { key: "month", label: "This month", days: 30 },
];

function fileIcon(mime: string | null, filename: string) {
  const lower = (mime ?? "") + filename.toLowerCase();
  if (lower.includes("pdf")) return <FileText />;
  if (lower.includes("sheet") || lower.includes("csv") || lower.includes("xls"))
    return <FileSpreadsheet />;
  if (lower.includes("image") || /\.(png|jpe?g|bmp|gif|webp|tiff?)$/.test(lower))
    return <ImageIcon />;
  return <FileText />;
}

export function ProjectsTable({
  documents,
  total,
  isLoading,
}: {
  documents: DocumentOut[];
  total: number;
  isLoading: boolean;
}) {
  const [range, setRange] = useState<RangeKey>("week");
  const [rangeOpen, setRangeOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const active = RANGES.find((entry) => entry.key === range);
    const cutoff =
      active?.days == null ? null : Date.now() - active.days * 24 * 60 * 60 * 1000;

    return documents.filter((doc) => {
      if (cutoff !== null) {
        const uploaded = new Date(doc.uploaded_at).getTime();
        if (Number.isNaN(uploaded) || uploaded < cutoff) return false;
      }
      if (query.trim()) {
        const needle = query.trim().toLowerCase();
        if (
          !doc.filename.toLowerCase().includes(needle) &&
          !(doc.doc_type ?? "").toLowerCase().includes(needle) &&
          !(doc.duplicate_status ?? "").toLowerCase().includes(needle)
        ) {
          return false;
        }
      }
      return true;
    });
  }, [documents, range, query]);

  const activeLabel = RANGES.find((entry) => entry.key === range)?.label ?? "This week";

  return (
    <div className="dt-card overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-txt-muted [&>svg]:h-4 [&>svg]:w-4">
          <ListFilter />
        </span>
        <h3 className="text-section font-semibold text-txt">My Documents</h3>

        {/* Range dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setRangeOpen((open) => !open)}
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-canvas px-2.5 text-[12.5px] font-medium text-txt-muted transition-colors duration-fast hover:bg-canvas-hover hover:text-txt"
          >
            {activeLabel}
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
          {rangeOpen ? (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setRangeOpen(false)} aria-hidden />
              <div className="absolute left-0 top-8 z-20 w-36 animate-scale-in overflow-hidden rounded-panel border border-line bg-canvas py-1 shadow-pop">
                {RANGES.map((entry) => (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => {
                      setRange(entry.key);
                      setRangeOpen(false);
                    }}
                    className={cn(
                      "block w-full px-3 py-1.5 text-left text-[12.5px] transition-colors duration-fast",
                      entry.key === range
                        ? "bg-brand-soft font-medium text-brand"
                        : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                    )}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>

        {/* Search */}
        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-txt-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search documents"
            className="h-7 w-[170px] rounded-control border border-line bg-canvas pl-8 pr-2.5 text-[12.5px] text-txt placeholder:text-txt-faint focus:border-brand/60 focus:outline-none focus:ring-2 focus:ring-brand/15"
          />
        </div>

        <Link
          to="/documents"
          className="inline-flex h-7 items-center rounded-control border border-line bg-canvas px-3 text-[12.5px] font-medium text-txt transition-colors duration-fast hover:bg-canvas-hover"
        >
          See All
        </Link>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="dt-table min-w-[620px]">
          <thead>
            <tr>
              <th className="w-auto">
                <span className="inline-flex items-center gap-1.5">
                  <Paperclip className="h-3.5 w-3.5" />
                  Document Name
                </span>
              </th>
              <th className="w-[210px]">
                <span className="inline-flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  Assigned
                </span>
              </th>
              <th className="w-[160px]">
                <span className="inline-flex items-center gap-1.5">
                  <ListFilter className="h-3.5 w-3.5" />
                  Status
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <tr key={`skeleton-${index}`}>
                  <td>
                    <span className="block h-3 w-52 animate-pulse rounded bg-canvas-section" />
                  </td>
                  <td>
                    <span className="block h-3 w-28 animate-pulse rounded bg-canvas-section" />
                  </td>
                  <td>
                    <span className="block h-4 w-20 animate-pulse rounded-pill bg-canvas-section" />
                  </td>
                </tr>
              ))
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-10 text-center text-[12.5px] text-txt-faint">
                  {documents.length === 0
                    ? "No documents yet — upload one to begin."
                    : "No documents match this filter."}
                </td>
              </tr>
            ) : (
              filtered.slice(0, 8).map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div className="flex items-center gap-2.5">
                      <span className="shrink-0 text-txt-muted [&>svg]:h-4 [&>svg]:w-4">
                        {fileIcon(doc.mime_type, doc.filename)}
                      </span>
                      <Link
                        to={`/documents/${doc.id}`}
                        className="truncate text-[13px] font-medium text-txt hover:text-brand"
                        title={doc.filename}
                      >
                        {doc.filename}
                      </Link>
                      <span className="ml-auto flex shrink-0 items-center gap-3 pl-3 text-[11.5px] text-txt-faint">
                        <span className="inline-flex items-center gap-1">
                          <MessageSquare className="h-3 w-3" />
                          {formatInt(doc.page_count ?? 0)}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <Paperclip className="h-3 w-3" />
                          {doc.file_size ? Math.max(1, Math.round(doc.file_size / 256)) : 0}
                        </span>
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <Avatar name={doc.filename} size={22} />
                      <span className="truncate text-[12.5px] text-txt">
                        {doc.filename.replace(/\.[a-z0-9]+$/i, "").replace(/[_-]+/g, " ")}
                      </span>
                    </div>
                  </td>
                  <td>
                    <StatusBadge tone={statusPill(doc.duplicate_status)}>
                      {duplicateLabel(doc.duplicate_status)}
                    </StatusBadge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!isLoading && filtered.length > 0 ? (
        <div className="flex items-center justify-between border-t border-line px-4 py-2 text-meta text-txt-faint">
          <span>
            Showing {Math.min(filtered.length, 8)} of {formatInt(total)} documents
          </span>
          <span>{activeLabel}</span>
        </div>
      ) : null}
    </div>
  );
}
