/**
 * Notes widget — a compact checklist with circular checkboxes.
 *
 * Completed items show a filled violet checkbox and struck-through title, and
 * stay in place rather than jumping, so the list does not reorder under the
 * user's cursor while they click.
 */

import { Check, FileText } from "lucide-react";
import { CardHeader } from "./ui";
import { cn } from "../lib/utils";

export interface NoteItem {
  id: string;
  title: string;
  description?: string;
  done: boolean;
}

export function NotesWidget({
  notes,
  onToggle,
}: {
  notes: NoteItem[];
  onToggle: (id: string) => void;
}) {
  const remaining = notes.filter((note) => !note.done).length;

  return (
    <div className="dt-card flex flex-col">
      <CardHeader
        icon={<FileText />}
        title="Notes"
        subtitle={remaining > 0 ? `${remaining} open` : "All done"}
      />

      <div className="flex-1 px-4 py-1.5">
        {notes.length === 0 ? (
          <p className="py-6 text-center text-[12.5px] text-txt-faint">No notes yet.</p>
        ) : (
          <ul>
            {notes.map((note, index) => (
              <li
                key={note.id}
                className={cn("py-2.5", index > 0 && "border-t border-dashed border-line")}
              >
                <label className="flex cursor-pointer items-start gap-2.5">
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={note.done}
                    onClick={() => onToggle(note.id)}
                    className={cn(
                      "mt-0.5 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border transition-colors duration-fast",
                      note.done
                        ? "border-transparent bg-[#8B5CF6] text-white"
                        : "border-line-strong bg-canvas hover:border-brand"
                    )}
                  >
                    {note.done ? <Check className="h-2.5 w-2.5" strokeWidth={3} /> : null}
                  </button>
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block text-[12.5px] font-medium leading-snug",
                        note.done ? "text-txt-faint line-through" : "text-txt"
                      )}
                    >
                      {note.title}
                    </span>
                    {note.description ? (
                      <span className="mt-0.5 block text-[11.5px] leading-relaxed text-txt-faint">
                        {note.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
