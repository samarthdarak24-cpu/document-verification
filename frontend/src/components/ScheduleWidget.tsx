/**
 * Schedule widget — a compact weekly calendar strip above a list of events.
 *
 * The calendar is driven by `date-fns` over real dates so the strip, the
 * selected day and the events below always agree with each other.
 */

import { useMemo } from "react";
import {
  addDays,
  endOfWeek,
  format,
  isSameDay,
  startOfWeek,
} from "date-fns";
import { CalendarDays, ChevronLeft, ChevronRight, Clock, MoreHorizontal } from "lucide-react";
import { Avatar, CardHeader, IconButton } from "./ui";
import { cn } from "../lib/utils";

export interface ScheduleEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  /** Accent colour for the left indicator bar. */
  accent: string;
  icon?: React.ReactNode;
  participants: string[];
}

export function WeeklyCalendar({
  selected,
  onSelect,
  weekOffset,
  onWeekChange,
}: {
  selected: Date;
  onSelect: (date: Date) => void;
  weekOffset: number;
  onWeekChange: (offset: number) => void;
}) {
  const days = useMemo(() => {
    const base = addDays(new Date(), weekOffset * 7);
    const start = startOfWeek(base, { weekStartsOn: 1 });
    const end = endOfWeek(base, { weekStartsOn: 1 });
    const out: Date[] = [];
    let cursor = start;
    while (cursor <= end) {
      out.push(cursor);
      cursor = addDays(cursor, 1);
    }
    return out;
  }, [weekOffset]);

  const today = new Date();

  return (
    <div className="px-4 pt-3">
      <div className="mb-2.5 flex items-center justify-between">
        <p className="text-meta font-medium text-txt-muted">
          {format(days[0], "d MMM")} – {format(days[days.length - 1], "d MMM yyyy")}
        </p>
        <div className="flex items-center gap-0.5">
          <IconButton label="Previous week" onClick={() => onWeekChange(weekOffset - 1)}>
            <ChevronLeft className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton label="Next week" onClick={() => onWeekChange(weekOffset + 1)}>
            <ChevronRight className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const isSelected = isSameDay(day, selected);
          const isToday = isSameDay(day, today);
          return (
            <button
              key={day.toISOString()}
              type="button"
              onClick={() => onSelect(day)}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-lg border py-1.5 transition-colors duration-fast",
                isSelected
                  ? "border-transparent bg-pill-lavender text-pill-lavender-txt"
                  : "border-transparent text-txt-muted hover:bg-canvas-hover hover:text-txt"
              )}
            >
              <span className="text-[10.5px] font-medium uppercase tracking-wide">
                {format(day, "EEEEE")}
              </span>
              <span
                className={cn(
                  "text-[13px] font-semibold leading-none",
                  isSelected ? "text-pill-lavender-txt" : "text-txt"
                )}
              >
                {format(day, "d")}
              </span>
              <span
                className={cn(
                  "h-1 w-1 rounded-full",
                  isToday && !isSelected ? "bg-brand" : "bg-transparent"
                )}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ScheduleWidget({
  events,
  selected,
  onSelect,
  weekOffset,
  onWeekChange,
}: {
  events: ScheduleEvent[];
  selected: Date;
  onSelect: (date: Date) => void;
  weekOffset: number;
  onWeekChange: (offset: number) => void;
}) {
  return (
    <div className="dt-card flex flex-col">
      <CardHeader
        icon={<CalendarDays />}
        title="Schedule"
        actions={
          <IconButton label="Schedule options">
            <MoreHorizontal className="h-4 w-4" />
          </IconButton>
        }
      />

      <WeeklyCalendar
        selected={selected}
        onSelect={onSelect}
        weekOffset={weekOffset}
        onWeekChange={onWeekChange}
      />

      <div className="mt-3 flex-1 px-4 pb-3">
        {events.length === 0 ? (
          <p className="py-6 text-center text-[12.5px] text-txt-faint">
            No events scheduled for this day.
          </p>
        ) : (
          <ul>
            {events.map((event, index) => (
              <li
                key={event.id}
                className={cn(
                  "flex items-center gap-3 py-2.5",
                  index > 0 && "border-t border-dashed border-line"
                )}
              >
                <span
                  className="h-8 w-[3px] shrink-0 rounded-full"
                  style={{ backgroundColor: event.accent }}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {event.icon ? (
                      <span className="shrink-0 text-txt-muted [&>svg]:h-3.5 [&>svg]:w-3.5">
                        {event.icon}
                      </span>
                    ) : null}
                    <p className="truncate text-[12.5px] font-medium text-txt">{event.title}</p>
                  </div>
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] text-txt-faint">
                    <Clock className="h-3 w-3" />
                    {format(event.start, "hh:mm a")} to {format(event.end, "hh:mm a")}
                  </p>
                </div>

                <div className="flex shrink-0 items-center -space-x-1.5">
                  {event.participants.slice(0, 3).map((person) => (
                    <Avatar key={person} name={person} size={20} className="ring-2 ring-canvas" />
                  ))}
                </div>

                <IconButton label="Event options" className="shrink-0">
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
