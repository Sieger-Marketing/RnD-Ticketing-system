/**
 * Building a manual time entry that the server will accept.
 *
 * `POST /api/time/entries` takes an optional `started_at` / `ended_at`. When
 * they are omitted the server invents the interval: 09:00 UTC on the entry
 * date, running for `hours`. It then refuses any entry whose interval overlaps
 * an existing one. Together those two rules mean a second entry logged on the
 * same day is *always* rejected as overlapping, because both were handed the
 * same invented 09:00 start. Logging a normal day's work in two pieces was
 * impossible.
 *
 * So the client supplies the interval. New work is stacked after whatever the
 * person already logged that day, which is both what actually happened and
 * what keeps the intervals disjoint.
 *
 * The server stores `hours` verbatim and never reconciles it against the
 * interval, so the two must be built together or the KPIs and the timeline
 * will disagree.
 */

import type { TimeEntry } from "@/types/api";

/** Where a day starts when there is nothing to stack behind. */
const DEFAULT_START_HOUR = 9;

export interface ManualEntryInput {
  taskId: string;
  /** YYYY-MM-DD in the user's timezone. */
  entryDate: string;
  hours: number;
  description?: string;
  /** Entries the user already has; only the same date is considered. */
  existing: TimeEntry[];
}

export interface ManualEntryPayload {
  task_id: string;
  entry_date: string;
  hours: number;
  description?: string;
  started_at: string;
  ended_at: string;
}

export function buildManualEntry({
  taskId,
  entryDate,
  hours,
  description,
  existing,
}: ManualEntryInput): ManualEntryPayload {
  const sameDay = existing.filter(
    (entry) => entry.entry_date === entryDate && !entry.is_running && entry.ended_at,
  );

  // Start where the day's last entry finished. A running entry is excluded
  // because it has no end yet; stopping it will write its own interval.
  const lastEnd = sameDay.reduce<number | null>((latest, entry) => {
    const ended = entry.ended_at ? new Date(entry.ended_at).getTime() : null;
    if (ended === null || Number.isNaN(ended)) return latest;
    return latest === null || ended > latest ? ended : latest;
  }, null);

  const start =
    lastEnd !== null
      ? new Date(lastEnd)
      : (() => {
          // Local 09:00 on the entry date, expressed as a real instant.
          const [year, month, day] = entryDate.split("-").map(Number);
          return new Date(
            year ?? 1970,
            (month ?? 1) - 1,
            day ?? 1,
            DEFAULT_START_HOUR,
            0,
            0,
            0,
          );
        })();

  const end = new Date(start.getTime() + hours * 3_600_000);

  return {
    task_id: taskId,
    entry_date: entryDate,
    hours,
    ...(description ? { description } : {}),
    started_at: start.toISOString(),
    ended_at: end.toISOString(),
  };
}
