/**
 * Release schedule as a Gantt bar chart (spec section 26).
 *
 * Planned dates are drawn as the bar and actual progress as a fill inside it,
 * so a release that is 40% done but 80% through its window reads as behind at
 * a glance without needing a separate variance column.
 */

import clsx from "clsx";
import { differenceInCalendarDays, format, parseISO } from "date-fns";

import { EmptyState, HealthPill } from "@/components/ui/primitives";
import { shortDate } from "@/lib/format";
import type { Health } from "@/types/api";

export interface TimelineRelease {
  id: string;
  code: string;
  name: string;
  sequence: number;
  status: string;
  health: Health;
  completion_percent: number;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  estimated_hours: number;
  actual_hours: number;
  delay_days: number;
}

const BAR_TONE: Record<Health, string> = {
  GREEN: "bg-rag-green",
  AMBER: "bg-rag-amber",
  RED: "bg-rag-red",
};

export function ReleaseTimeline({
  releases,
  onSelect,
}: {
  releases: TimelineRelease[];
  onSelect?: (releaseId: string) => void;
}) {
  const dated = releases.filter((r) => r.planned_start && r.planned_end);

  if (dated.length === 0) {
    return (
      <EmptyState
        title="No scheduled releases"
        description="Releases appear on the timeline once they have planned start and end dates."
      />
    );
  }

  const starts = dated.map((r) => parseISO(r.planned_start!).getTime());
  const ends = dated.map((r) => parseISO(r.planned_end!).getTime());
  const min = new Date(Math.min(...starts));
  const max = new Date(Math.max(...ends));
  const span = Math.max(1, differenceInCalendarDays(max, min));

  const today = new Date();
  const todayOffset = differenceInCalendarDays(today, min);
  const todayVisible = todayOffset >= 0 && todayOffset <= span;

  const position = (release: TimelineRelease) => {
    const start = parseISO(release.planned_start!);
    const end = parseISO(release.planned_end!);
    const left = (differenceInCalendarDays(start, min) / span) * 100;
    const width = Math.max(
      1.5,
      (Math.max(1, differenceInCalendarDays(end, start)) / span) * 100,
    );
    return { left: `${left}%`, width: `${Math.min(width, 100 - left)}%` };
  };

  return (
    <div>
      <div className="mb-2 flex justify-between px-1 text-2xs text-ink-500">
        <span>{format(min, "d MMM yyyy")}</span>
        <span>{format(max, "d MMM yyyy")}</span>
      </div>

      <div className="relative space-y-1.5">
        {todayVisible && (
          <div
            className="pointer-events-none absolute inset-y-0 z-10 w-px bg-signal-500"
            style={{ left: `calc(14rem + ${(todayOffset / span) * 100}% * 0.7)` }}
            aria-hidden
          />
        )}

        {releases.map((release) => {
          const scheduled = Boolean(release.planned_start && release.planned_end);
          return (
            <div
              key={release.id}
              className={clsx(
                "flex items-center gap-3 rounded px-1 py-1",
                onSelect && "cursor-pointer hover:bg-ink-50",
              )}
              onClick={onSelect ? () => onSelect(release.id) : undefined}
            >
              <div className="w-56 shrink-0">
                <p className="truncate text-xs font-medium text-ink-900" title={release.name}>
                  {release.name}
                </p>
                <p className="font-mono text-2xs text-ink-400">{release.code}</p>
              </div>

              <div className="relative h-6 flex-1 rounded bg-ink-100">
                {scheduled ? (
                  <div
                    className="absolute inset-y-0 overflow-hidden rounded"
                    style={position(release)}
                    title={`${shortDate(release.planned_start)} → ${shortDate(
                      release.planned_end,
                    )} · ${release.completion_percent.toFixed(0)}% complete`}
                  >
                    <div className="h-full w-full bg-ink-200" />
                    <div
                      className={clsx(
                        "absolute inset-y-0 left-0 rounded-l",
                        BAR_TONE[release.health],
                      )}
                      style={{ width: `${Math.min(100, release.completion_percent)}%` }}
                    />
                    <span className="absolute inset-0 flex items-center justify-center text-2xs font-medium text-white mix-blend-luminosity">
                      {release.completion_percent.toFixed(0)}%
                    </span>
                  </div>
                ) : (
                  <span className="absolute inset-0 flex items-center pl-2 text-2xs text-ink-400">
                    Not scheduled
                  </span>
                )}
              </div>

              <div className="flex w-28 shrink-0 items-center justify-end gap-1.5">
                {release.delay_days > 0 && (
                  <span className="text-2xs font-medium text-rag-red">
                    +{release.delay_days}d
                  </span>
                )}
                <HealthPill health={release.health} />
              </div>
            </div>
          );
        })}
      </div>

      {todayVisible && (
        <p className="mt-2 px-1 text-2xs text-ink-400">
          The vertical line marks today. Bars are the planned window; the filled
          portion is actual completion.
        </p>
      )}
    </div>
  );
}
