import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  Layers,
  Lightbulb,
  Sparkles,
  Zap,
} from "lucide-react";
import { ProjectsTable } from "../components/ProjectsTable";
import { ScheduleWidget, type ScheduleEvent } from "../components/ScheduleWidget";
import { NotesWidget, type NoteItem } from "../components/NotesWidget";
import { StatsSummary } from "../components/StatsSummary";
import { ErrorState } from "../components/ui";
import {
  useAnalyticsOverview,
  useDocuments,
  useDuplicatesSummary,
  useHealth,
} from "../hooks/queries";
import { formatInt } from "../lib/utils";

/** Time-of-day greeting, computed from the local clock. */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good Morning";
  if (hour < 17) return "Good Afternoon";
  return "Good Evening";
}

const NOTE_SEED: NoteItem[] = [
  {
    id: "n1",
    title: "Review flagged duplicates",
    description:
      "Four documents were grouped as exact or content duplicates. Confirm each pair is genuinely the same credential before clearing it.",
    done: false,
  },
  {
    id: "n2",
    title: "Tune the near-duplicate threshold",
    description:
      "One candidate scored 0.897, just under the content-duplicate cut-off. Decide whether the band needs widening.",
    done: false,
  },
  {
    id: "n3",
    title: "Re-run the benchmark grid",
    description: "301 measurements stored across 11 algorithms and five input sizes.",
    done: true,
  },
];

const EVENT_ACCENTS = ["#8B5CF6", "#3B65D9", "#22C55E", "#F59E0B", "#EC4899"];

export default function Dashboard() {
  const health = useHealth();
  const overview = useAnalyticsOverview();
  const duplicates = useDuplicatesSummary();
  const documents = useDocuments({ limit: 12 });

  const [notes, setNotes] = useState<NoteItem[]>(NOTE_SEED);
  const [selectedDay, setSelectedDay] = useState(new Date());
  const [weekOffset, setWeekOffset] = useState(0);

  const docs = documents.data ?? [];
  const total = overview.data?.documents?.total ?? docs.length;
  const completed = overview.data?.documents?.completed ?? 0;
  const flagged = duplicates.data?.documents_flagged ?? 0;
  const groupCount = duplicates.data?.total_groups ?? 0;
  const dbOk = health.data?.database === "ok";

  // Build a small schedule from the real documents so the widget reflects the
  // actual corpus rather than invented content. Documents are spread across the
  // selected day in one-hour slots.
  const events: ScheduleEvent[] = useMemo(() => {
    const base = new Date(selectedDay);
    base.setHours(10, 0, 0, 0);
    return docs.slice(0, 3).map((doc, index) => {
      const start = new Date(base.getTime() + index * 90 * 60 * 1000);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      return {
        id: doc.id,
        title: doc.filename.replace(/\.[a-z0-9]+$/i, "").replace(/[_-]+/g, " "),
        start,
        end,
        accent: EVENT_ACCENTS[index % EVENT_ACCENTS.length],
        icon: <FileText />,
        participants: [
          doc.filename.replace(/\.[a-z0-9]+$/i, ""),
          "Verification queue",
          "Review desk",
        ],
      };
    });
  }, [docs, selectedDay]);

  const toggleNote = (id: string) =>
    setNotes((prev) => prev.map((note) => (note.id === id ? { ...note, done: !note.done } : note)));

  return (
    <div className="animate-fade-up">
      {health.isError ? <ErrorState error={health.error} /> : null}

      {/* Header */}
      <header className="mb-5">
        <h1 className="text-greeting text-txt">
          {greeting()}, Reviewer
        </h1>
        <p className="mt-1 text-[13px] text-txt-muted">
          {dbOk ? "All systems operational" : "Backend degraded"} · local, deterministic
          verification
        </p>

        <div className="mt-4">
          <StatsSummary
            segments={[
              {
                icon: <Clock3 />,
                value: completed > 0 ? `${formatInt(completed)}` : "0",
                label: "Documents processed",
              },
              {
                icon: <CheckCircle2 />,
                value: `${formatInt(total)}`,
                label: "In the workspace",
              },
              {
                icon: <AlertTriangle />,
                value: `${formatInt(flagged)}`,
                label: "Flagged for review",
              },
            ]}
          />
        </div>
      </header>

      {/* Documents table */}
      <ProjectsTable documents={docs} total={total} isLoading={documents.isLoading} />

      {/* Bottom widgets */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ScheduleWidget
          events={events}
          selected={selectedDay}
          onSelect={setSelectedDay}
          weekOffset={weekOffset}
          onWeekChange={setWeekOffset}
        />
        <NotesWidget notes={notes} onToggle={toggleNote} />
      </div>

      {/* Secondary detail row */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="dt-card p-4">
          <div className="mb-2.5 flex items-center gap-2 text-txt-muted">
            <Layers className="h-4 w-4" />
            <h3 className="text-section font-semibold text-txt">Duplicate groups</h3>
          </div>
          <p className="text-[26px] font-semibold leading-none tracking-[-0.02em] text-txt">
            {formatInt(groupCount)}
          </p>
          <p className="mt-2 text-meta text-txt-faint">
            {formatInt(duplicates.data?.exact_groups ?? 0)} exact ·{" "}
            {formatInt(duplicates.data?.content_groups ?? 0)} content
          </p>
          <Link
            to="/duplicates"
            className="mt-3 inline-block text-[12.5px] font-medium text-brand hover:text-brand-hover"
          >
            Review groups →
          </Link>
        </div>

        <div className="dt-card p-4">
          <div className="mb-2.5 flex items-center gap-2 text-txt-muted">
            <Activity className="h-4 w-4" />
            <h3 className="text-section font-semibold text-txt">Verification outcomes</h3>
          </div>
          <OutcomeList runs={overview.data?.runs ?? {}} />
        </div>

        <div className="dt-card p-4">
          <div className="mb-2.5 flex items-center gap-2 text-txt-muted">
            <Lightbulb className="h-4 w-4" />
            <h3 className="text-section font-semibold text-txt">How it works</h3>
          </div>
          <ul className="space-y-2 text-[12.5px] leading-snug text-txt-muted">
            <li className="flex gap-2">
              <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" />
              Topological sort fixes the stage order from a 13-node DAG
            </li>
            <li className="flex gap-2">
              <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" />
              LCS and edit distance compare token sequences
            </li>
            <li className="flex gap-2">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" />
              Eight deterministic rules produce the recommendation
            </li>
          </ul>
          <Link
            to="/performance"
            className="mt-3 inline-block text-[12.5px] font-medium text-brand hover:text-brand-hover"
          >
            View performance →
          </Link>
        </div>
      </div>
    </div>
  );
}

function OutcomeList({ runs }: { runs: Record<string, number> }) {
  const entries = Object.entries(runs).filter(([, value]) => typeof value === "number");
  if (entries.length === 0) {
    return <p className="py-3 text-[12.5px] text-txt-faint">No verification runs yet.</p>;
  }
  const max = Math.max(...entries.map(([, value]) => value), 1);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);

  return (
    <div className="space-y-2.5">
      {entries.slice(0, 4).map(([outcome, count]) => (
        <div key={outcome}>
          <div className="mb-1 flex items-baseline justify-between gap-2">
            <span className="truncate text-[12px] text-txt-muted">
              {outcome.replace(/_/g, " ").toLowerCase()}
            </span>
            <span className="shrink-0 text-[11.5px] tabular-nums text-txt-faint">
              {count} · {Math.round((count / total) * 100)}%
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-canvas-section">
            <div
              className="h-full rounded-full bg-brand"
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
