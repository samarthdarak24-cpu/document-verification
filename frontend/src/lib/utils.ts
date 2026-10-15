import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names, resolving Tailwind conflicts last-wins. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a 0..1 ratio as a percentage string. */
export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Format a millisecond duration for display, choosing a sensible unit. */
export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  if (ms < 1000) return `${ms.toFixed(2)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Format a byte count using binary units. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Compact integer formatting with thousands separators. */
export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN");
}

/** Format an ISO timestamp as a readable local date-time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Human label for a snake_case identifier. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Deterministic colour token for a status string. */
export function statusTone(status: string | null | undefined): string {
  switch (status) {
    case "passed":
    case "unique":
    case "verified":
    case "accepted":
    case "ok":
    case "completed":
      return "text-status-pass bg-status-pass/10 border-status-pass/25";
    case "exact_duplicate":
    case "reject":
    case "failed":
    case "invalid":
    case "processing_error":
      return "text-status-fail bg-status-fail/10 border-status-fail/25";
    case "near_duplicate":
    case "content_duplicate":
    case "manual_review":
    case "flagged":
    case "warning":
    case "retry":
      return "text-status-warn bg-status-warn/10 border-status-warn/25";
    default:
      return "text-status-neutral bg-status-neutral/10 border-status-neutral/25";
  }
}

/**
 * Map a status string onto a soft pastel pill tone.
 *
 * Mirrors the reference design's convention: soft tinted background with a dark
 * readable label, one hue per state family.
 */
export function statusPill(
  status: string | null | undefined
):
  | "green"
  | "lavender"
  | "blue"
  | "amber"
  | "rose"
  | "slate" {
  switch (status) {
    case "passed":
    case "unique":
    case "verified":
    case "accepted":
    case "ok":
    case "completed":
      return "green";
    case "exact_duplicate":
    case "reject":
    case "failed":
    case "invalid":
    case "processing_error":
      return "rose";
    case "content_duplicate":
    case "manual_review":
    case "flagged":
    case "warning":
    case "retry":
      return "amber";
    case "near_duplicate":
      return "lavender";
    case "pending":
    case "queued":
    case "processing":
      return "blue";
    default:
      return "slate";
  }
}

/** Short, human label for a duplicate status. */
export function duplicateLabel(status: string | null | undefined): string {
  switch (status) {
    case "exact_duplicate":
      return "Exact duplicate";
    case "content_duplicate":
      return "Content duplicate";
    case "near_duplicate":
      return "Near duplicate";
    case "unique":
      return "Unique";
    default:
      return humanize(status);
  }
}

/** Initials for an avatar, derived from a filename or free-text name. */
export function initialsOf(value: string | null | undefined): string {
  if (!value) return "?";
  const cleaned = value.replace(/\.[a-z0-9]+$/i, "").replace(/[_\-.]+/g, " ").trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
