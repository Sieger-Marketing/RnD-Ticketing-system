/**
 * Shared display primitives.
 *
 * Status and health are rendered by dedicated components rather than ad-hoc
 * colour classes, so a status means the same colour on every screen and a new
 * status only needs adding in one place.
 */

import clsx from "clsx";
import { AlertCircle, AlertTriangle, CheckCircle2, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { DASH, num, percent } from "@/lib/format";
import type { Health, Priority, TaskStatus, UtilizationBand } from "@/types/api";

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function Card({
  title,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("card", className)}>
      {(title || action) && (
        <header className="card-header">
          <h2 className="card-title">{title}</h2>
          {action}
        </header>
      )}
      <div className={bodyClassName ?? "p-4"}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-col gap-3 sm:mb-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-lg font-semibold text-ink-900 sm:text-xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 text-xs text-ink-500 sm:text-sm">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">
          {actions}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status vocabulary
// ---------------------------------------------------------------------------

const TASK_STATUS_STYLES: Record<TaskStatus, string> = {
  "Not Started": "bg-ink-100 text-ink-700",
  Assigned: "bg-cream-300 text-ink-700",
  "In Progress": "bg-signal-50 text-signal-700",
  Blocked: "bg-rag-redBg text-rag-red",
  "Submitted for Review": "bg-rag-amberBg text-rag-amber",
  "Under Review": "bg-rag-amberBg text-rag-amber",
  "Revision Required": "bg-rag-amberBg text-rag-amber",
  Approved: "bg-rag-greenBg text-rag-green",
  Completed: "bg-rag-greenBg text-rag-green",
  Cancelled: "bg-ink-100 text-ink-400 line-through",
};

const GENERIC_STATUS_STYLES: Record<string, string> = {
  Draft: "bg-ink-100 text-ink-700",
  Planning: "bg-cream-300 text-ink-700",
  "In Progress": "bg-signal-50 text-signal-700",
  "Design In Progress": "bg-signal-50 text-signal-700",
  "Internal Review": "bg-rag-amberBg text-rag-amber",
  "Customer Review": "bg-rag-amberBg text-rag-amber",
  Revision: "bg-rag-amberBg text-rag-amber",
  Approved: "bg-rag-greenBg text-rag-green",
  Completed: "bg-rag-greenBg text-rag-green",
  "On Hold": "bg-ink-200 text-ink-700",
  Cancelled: "bg-ink-100 text-ink-400 line-through",
  "Not Started": "bg-ink-100 text-ink-700",
  Assigned: "bg-cream-300 text-ink-700",
  Open: "bg-rag-amberBg text-rag-amber",
  Resolved: "bg-rag-greenBg text-rag-green",
  Pending: "bg-rag-amberBg text-rag-amber",
};

export function StatusBadge({ status }: { status: string }) {
  const style =
    TASK_STATUS_STYLES[status as TaskStatus] ??
    GENERIC_STATUS_STYLES[status] ??
    "bg-ink-100 text-ink-700";
  return (
    <span
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded px-1.5 py-0.5 text-2xs font-medium",
        style,
      )}
    >
      {status}
    </span>
  );
}

const HEALTH_STYLES: Record<Health, string> = {
  GREEN: "bg-rag-greenBg text-rag-green",
  AMBER: "bg-rag-amberBg text-rag-amber",
  RED: "bg-rag-redBg text-rag-red",
};

export function HealthPill({ health, label }: { health: Health; label?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold",
        HEALTH_STYLES[health],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label ?? health}
    </span>
  );
}

const PRIORITY_STYLES: Record<Priority, string> = {
  Low: "text-ink-500",
  Medium: "text-ink-700",
  High: "text-rag-amber font-semibold",
  Critical: "text-rag-red font-semibold",
};

export function PriorityLabel({ priority }: { priority: Priority }) {
  return <span className={clsx("text-xs", PRIORITY_STYLES[priority])}>{priority}</span>;
}

const BAND_STYLES: Record<UtilizationBand, string> = {
  Underutilized: "bg-cream-300 text-ink-700",
  Healthy: "bg-rag-greenBg text-rag-green",
  "High Load": "bg-rag-amberBg text-rag-amber",
  Overloaded: "bg-rag-redBg text-rag-red",
  "No Data": "bg-ink-100 text-ink-500",
};

export function UtilizationBadge({
  band,
  value,
}: {
  band: UtilizationBand;
  value: number | null;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-2xs font-medium",
        BAND_STYLES[band],
      )}
      title={band}
    >
      {percent(value)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

export function ProgressBar({
  value,
  tone = "neutral",
}: {
  value: number;
  tone?: "neutral" | "green" | "amber" | "red";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const toneClass = {
    neutral: "bg-ink-700",
    green: "bg-rag-green",
    amber: "bg-rag-amber",
    red: "bg-rag-red",
  }[tone];
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-200">
        <div
          className={clsx("h-full rounded-full transition-all", toneClass)}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-2xs text-ink-600">
        {Math.round(clamped)}%
      </span>
    </div>
  );
}

export function KpiCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
  icon?: ReactNode;
}) {
  const toneClass = {
    neutral: "text-ink-900",
    good: "text-rag-green",
    warn: "text-rag-amber",
    bad: "text-rag-red",
  }[tone];
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-2xs font-medium uppercase tracking-wide text-ink-500">
          {label}
        </p>
        {icon && <span className="text-ink-300">{icon}</span>}
      </div>
      <p className={clsx("mt-1 text-2xl font-semibold tabular", toneClass)}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

/**
 * Colour a KPI by whether it is good or bad.
 * `higherIsBetter` matters: 90% on-time is good, 90% rework is a crisis.
 */
export function toneFor(
  value: number | null | undefined,
  { good, warn, higherIsBetter = true }: { good: number; warn: number; higherIsBetter?: boolean },
): "neutral" | "good" | "warn" | "bad" {
  if (value === null || value === undefined) return "neutral";
  if (higherIsBetter) {
    if (value >= good) return "good";
    if (value >= warn) return "warn";
    return "bad";
  }
  if (value <= good) return "good";
  if (value <= warn) return "warn";
  return "bad";
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("h-4 w-4 animate-spin", className)} />;
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-500">
      <Spinner />
      {label}…
    </div>
  );
}

export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((__, c) => (
            <div
              key={c}
              className="h-4 flex-1 animate-pulse rounded bg-ink-100"
              style={{ animationDelay: `${(r * cols + c) * 40}ms` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <span className="text-ink-300">{icon ?? <Inbox className="h-7 w-7" />}</span>
      <p className="text-sm font-medium text-ink-800">{title}</p>
      {description && <p className="max-w-sm text-xs text-ink-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <AlertCircle className="h-7 w-7 text-rag-red" />
      <p className="text-sm font-medium text-ink-800">{title}</p>
      {message && <p className="max-w-md text-xs text-ink-500">{message}</p>}
      {onRetry && (
        <button type="button" className="btn-secondary mt-2" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function InlineAlert({
  tone = "warn",
  children,
}: {
  tone?: "warn" | "error" | "success" | "info";
  children: ReactNode;
}) {
  const config = {
    warn: { cls: "bg-rag-amberBg text-rag-amber", Icon: AlertTriangle },
    error: { cls: "bg-rag-redBg text-rag-red", Icon: AlertCircle },
    success: { cls: "bg-rag-greenBg text-rag-green", Icon: CheckCircle2 },
    info: { cls: "bg-signal-50 text-signal-700", Icon: AlertCircle },
  }[tone];
  const { Icon } = config;
  return (
    <div
      className={clsx(
        "flex items-start gap-2 rounded-md px-3 py-2 text-xs",
        config.cls,
      )}
      role={tone === "error" ? "alert" : undefined}
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-2xs uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular text-ink-900">{value ?? DASH}</dd>
    </div>
  );
}

export function Avatar({ name }: { name: string | null | undefined }) {
  const label = (name ?? "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0] ?? "")
    .join("")
    .toUpperCase();
  return (
    <span
      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-200 text-2xs font-semibold text-ink-700"
      title={name ?? undefined}
    >
      {label || "?"}
    </span>
  );
}

export function CountBadge({ count }: { count: number }) {
  return (
    <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-ink-200 px-1.5 text-2xs font-semibold text-ink-700">
      {num(count)}
    </span>
  );
}
