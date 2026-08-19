/**
 * Display formatting.
 *
 * The rule that matters here: the API returns `null` for "not enough data to
 * compute this", which is different from zero. These helpers render that as a
 * dash so a dashboard never claims 0% efficiency for work nobody has started.
 */

import { differenceInCalendarDays, format, formatDistanceToNowStrict, parseISO } from "date-fns";

export const DASH = "—";

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${value.toFixed(digits)}%`;
}

export function hours(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${value.toFixed(digits)}h`;
}

/** Signed variance, where positive means over plan. */
export function variance(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}h`;
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return DASH;
  try {
    return format(parseISO(value), "d MMM yyyy");
  } catch {
    return DASH;
  }
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  try {
    return format(parseISO(value), "d MMM yyyy, HH:mm");
  } catch {
    return DASH;
  }
}

export function relative(value: string | null | undefined): string {
  if (!value) return DASH;
  try {
    return `${formatDistanceToNowStrict(parseISO(value))} ago`;
  } catch {
    return DASH;
  }
}

/**
 * Days until a date; negative means it has passed. Returns null when there is
 * no date, so callers can distinguish "no deadline" from "due today".
 */
export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  try {
    return differenceInCalendarDays(parseISO(value), new Date());
  } catch {
    return null;
  }
}

export function dueLabel(value: string | null | undefined): string {
  const days = daysUntil(value);
  if (days === null) return "No due date";
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days > 0) return `Due in ${days} days`;
  return `${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} overdue`;
}

export function durationHours(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  if (value < 24) return `${value.toFixed(1)}h`;
  const days = value / 24;
  return `${days.toFixed(1)}d`;
}

export function initials(fullName: string | null | undefined): string {
  if (!fullName) return "?";
  const parts = fullName.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

/**
 * Today in the *browser's* timezone, as YYYY-MM-DD.
 *
 * `new Date().toISOString().slice(0,10)` is the UTC date, which is a different
 * day from the user's for part of every 24 hours. Using it to pre-fill or cap
 * a date input hands someone west of UTC a tomorrow the server will reject,
 * and someone east of UTC a yesterday.
 */
export function localToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** Local date N days back, same reasoning as localToday. */
export function localDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const offset = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - offset).toISOString().slice(0, 10);
}
