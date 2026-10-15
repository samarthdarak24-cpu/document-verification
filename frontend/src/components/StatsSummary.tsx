/**
 * Compact horizontal statistics bar.
 *
 * One pill-shaped container split into three sections by thin vertical rules —
 * deliberately not three separate oversized metric cards.
 */

import type { ReactNode } from "react";

export interface StatSegment {
  icon: ReactNode;
  value: ReactNode;
  label: string;
}

export function StatsSummary({ segments }: { segments: StatSegment[] }) {
  return (
    <div className="inline-flex max-w-full flex-wrap items-stretch rounded-pill border border-line bg-canvas px-1.5 py-1.5">
      {segments.map((segment, index) => (
        <div key={segment.label} className="flex items-stretch">
          {index > 0 ? <span className="my-1 w-px shrink-0 bg-line" aria-hidden /> : null}
          <div className="flex items-center gap-2 px-3.5 py-0.5">
            <span className="shrink-0 text-txt-muted [&>svg]:h-[15px] [&>svg]:w-[15px]">
              {segment.icon}
            </span>
            <p className="whitespace-nowrap text-[13px] text-txt-muted">
              <span className="font-semibold text-txt">{segment.value}</span>{" "}
              {segment.label}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
