/**
 * The task table used across dashboards and lists.
 *
 * Columns are opt-in so the same component serves a designer's personal queue
 * (who cares about due date and status) and a manager's overdue list (who also
 * needs the assignee, the project and the delay reason).
 *
 * On a phone each row becomes a card: ten columns of task data cannot be read
 * by scrolling sideways, because the row you are reading leaves the screen
 * before the column you want arrives.
 */

import clsx from "clsx";
import { AlertTriangle, Play, Square } from "lucide-react";

import {
  Avatar,
  EmptyState,
  PriorityLabel,
  ProgressBar,
  Spinner,
  StatusBadge,
} from "@/components/ui/primitives";
import { ResponsiveTable, type Column } from "@/components/ui/ResponsiveTable";
import {
  useRunningTimer,
  useStartTimer,
  useStopTimer,
} from "@/hooks/queries";
import { P, useAuth } from "@/store/auth";
import { DASH, hours, shortDate } from "@/lib/format";
import type { TaskSummary } from "@/types/api";

export type TaskColumn =
  | "code"
  | "name"
  | "project"
  | "status"
  | "priority"
  | "assignee"
  | "due"
  | "progress"
  | "hours"
  | "delay"
  | "timer";

const DEFAULT_COLUMNS: TaskColumn[] = [
  "code",
  "name",
  "status",
  "priority",
  "due",
  "progress",
];


/**
 * Start or stop the clock without leaving the list.
 *
 * A designer lives on this list, and until now starting work meant opening the
 * task first -- which is the difference between a timer people use and one they
 * mean to. The running-timer query is shared, so a table of twenty rows still
 * asks once.
 *
 * Only ever offered on your own tasks: the API refuses anybody else's, so a
 * button here would produce nothing but an error.
 */
function TimerCell({ task }: { task: TaskSummary }) {
  const { can, user } = useAuth();
  const running = useRunningTimer();
  const start = useStartTimer();
  const stop = useStopTimer();

  if (!can(P.timeLogOwn) || task.assigned_to_id !== user?.id) return null;
  if (DONE_STATUSES.has(task.status)) return null;

  const onThisTask = running.data?.task_id === task.id;
  const busy = start.isPending || stop.isPending;

  if (onThisTask) {
    return (
      <button
        type="button"
        className="btn-danger px-2 py-0.5 text-2xs"
        onClick={(event) => {
          event.stopPropagation();
          stop.mutate();
        }}
        disabled={busy}
      >
        {busy ? <Spinner className="h-3 w-3" /> : <Square className="h-3 w-3" />}
        Stop
      </button>
    );
  }

  return (
    <button
      type="button"
      className="btn-secondary px-2 py-0.5 text-2xs"
      onClick={(event) => {
        // The row is a link to the task; starting the clock is not navigation.
        event.stopPropagation();
        start.mutate({ task_id: task.id });
      }}
      disabled={busy || Boolean(running.data)}
      title={
        running.data
          ? `A timer is already running on ${running.data.task_code}`
          : "Start work and the clock together"
      }
    >
      {busy ? <Spinner className="h-3 w-3" /> : <Play className="h-3 w-3" />}
      Start
    </button>
  );
}

//: Work that is finished has nothing left to time.
const DONE_STATUSES = new Set(["Completed", "Approved", "Cancelled"]);

export function TaskTable({
  tasks,
  columns = DEFAULT_COLUMNS,
  onSelect,
  emptyTitle = "No tasks",
  emptyDescription,
  maxRows,
}: {
  tasks: TaskSummary[];
  columns?: TaskColumn[];
  onSelect?: (task: TaskSummary) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  maxRows?: number;
}) {
  const rows = maxRows ? tasks.slice(0, maxRows) : tasks;
  const wanted = new Set(columns);

  const all: Record<TaskColumn, Column<TaskSummary>> = {
    code: {
      key: "code",
      header: "Task",
      mobile: "meta",
      cell: (t) => <span className="font-mono text-2xs text-ink-500">{t.code}</span>,
    },
    name: {
      key: "name",
      header: "Description",
      mobile: "primary",
      className: "max-w-[22rem]",
      cell: (t) => (
        <>
          <div className="flex items-center gap-1.5">
            <span className="truncate font-medium text-ink-900" title={t.name}>
              {t.name}
            </span>
            {t.blocker_reason && (
              <AlertTriangle
                className="h-3.5 w-3.5 shrink-0 text-rag-red"
                aria-label="Blocked"
              />
            )}
          </div>
          <span className="text-2xs text-ink-400">{t.task_type}</span>
        </>
      ),
    },
    project: {
      key: "project",
      header: "Project",
      mobile: "meta",
      cell: (t) => <span className="text-xs text-ink-600">{t.project_code ?? DASH}</span>,
    },
    assignee: {
      key: "assignee",
      header: "Assignee",
      mobile: "field",
      cell: (t) =>
        t.assigned_to_name ? (
          <span className="flex items-center gap-1.5">
            <Avatar name={t.assigned_to_name} />
            <span className="truncate text-xs">{t.assigned_to_name}</span>
          </span>
        ) : (
          <span className="text-xs text-ink-400">Unassigned</span>
        ),
    },
    status: {
      key: "status",
      header: "Status",
      mobile: "field",
      cell: (t) => <StatusBadge status={t.status} />,
    },
    priority: {
      key: "priority",
      header: "Priority",
      mobile: "field",
      cell: (t) => <PriorityLabel priority={t.priority} />,
    },
    due: {
      key: "due",
      header: "Due",
      mobile: "field",
      cell: (t) => (
        <span
          className={clsx(
            "text-xs",
            t.is_overdue ? "font-medium text-rag-red" : "text-ink-600",
          )}
        >
          {shortDate(t.planned_end)}
        </span>
      ),
    },
    progress: {
      key: "progress",
      header: "Progress",
      mobile: "field",
      headerClassName: "w-32",
      cell: (t) => (
        <ProgressBar
          value={t.completion_percent}
          tone={t.is_overdue ? "amber" : "neutral"}
        />
      ),
    },
    timer: {
      key: "timer",
      header: "",
      align: "right",
      mobile: "field",
      cell: (t) => <TimerCell task={t} />,
    },
    hours: {
      key: "hours",
      header: "Est / Act",
      align: "right",
      mobile: "field",
      cell: (t) => (
        <span className="text-xs tabular">
          <span className="text-ink-500">{hours(t.estimated_hours)}</span>
          <span className="mx-1 text-ink-300">/</span>
          <span
            className={clsx(
              t.actual_hours > t.estimated_hours && t.estimated_hours > 0
                ? "font-medium text-rag-amber"
                : "text-ink-800",
            )}
          >
            {hours(t.actual_hours)}
          </span>
        </span>
      ),
    },
    delay: {
      key: "delay",
      header: "Delay",
      mobile: "field",
      cell: (t) =>
        t.delay_days > 0 ? (
          <span className="text-xs font-medium text-rag-red">{t.delay_days}d</span>
        ) : (
          <span className="text-xs text-ink-400">{DASH}</span>
        ),
    },
  };

  const ordered = (
    // The order columns appear in, regardless of the order they were asked
    // for. A key missing from this list is silently dropped, so anything added
    // to TaskColumn has to be added here too. "timer" sits last: it is an
    // action, not data, and belongs at the end of the row.
    [
      "code", "name", "project", "assignee", "status", "priority",
      "due", "progress", "hours", "delay", "timer",
    ] as TaskColumn[]
  )
    .filter((key) => wanted.has(key))
    .map((key) => all[key]);

  return (
    <ResponsiveTable
      rows={rows}
      columns={ordered}
      rowKey={(t) => t.id}
      onRowClick={onSelect}
      minWidth="44rem"
      empty={<EmptyState title={emptyTitle} description={emptyDescription} />}
      footer={
        maxRows && tasks.length > maxRows ? (
          <p className="border-t border-ink-100 px-3 py-2 text-2xs text-ink-500">
            Showing {maxRows} of {tasks.length}
          </p>
        ) : undefined
      }
    />
  );
}
