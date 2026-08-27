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
import { AlertTriangle, Play, Square, UserPlus } from "lucide-react";
import { useState } from "react";

import { AssigneePicker } from "@/components/AssigneePicker";
import { FormError } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";

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
  useAssignTaskById,
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
  // task.assign specifically, not "assign or reassign": the picker loads the
  // assignment board, which requires task.assign on its own. Gating on either
  // would show the control to somebody whose dialog then 403s on open.
  const canAssign = useAuth((s) => s.can)(P.taskAssign);

  const [assigning, setAssigning] = useState<TaskSummary | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const assign = useAssignTaskById();

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
      // The name, and only the name: a code is precise but nobody holds
      // PRJ-0124 in their head, and showing both put the thing nobody reads
      // directly under the thing they do. The code is still on the task page
      // and is still what search matches, so nothing is lost by not printing
      // it on every row.
      //
      // Falls back to the code only when the name is genuinely missing, which
      // is better than an empty cell -- and is what shows until an API that
      // predates project_name is restarted.
      cell: (t) =>
        t.project_name || t.project_code ? (
          <span
            className="block truncate text-xs text-ink-800"
            title={t.project_code ?? undefined}
          >
            {t.project_name ?? t.project_code}
          </span>
        ) : (
          <span className="text-xs text-ink-400">{DASH}</span>
        ),
    },
    assignee: {
      key: "assignee",
      header: "Assignee",
      mobile: "field",
      // Assignable in place for anyone who may assign. Going to the task just
      // to set an owner meant a lead handing out a morning's work made a round
      // trip per task, which is where the unassigned rows in a long list come
      // from.
      cell: (t) => {
        const label = t.assigned_to_name ? (
          <span className="flex min-w-0 items-center gap-1.5">
            <Avatar name={t.assigned_to_name} />
            <span className="truncate text-xs">{t.assigned_to_name}</span>
          </span>
        ) : (
          <span className="text-xs text-ink-400">Unassigned</span>
        );

        if (!canAssign) return label;

        return (
          <button
            type="button"
            className="group flex min-w-0 items-center gap-1 rounded px-1 py-0.5 text-left hover:bg-ink-50"
            onClick={(event) => {
              // The row is a link to the task; assigning is not navigation.
              event.stopPropagation();
              assign.reset();
              // Seed from this row, not from whatever was picked last time --
              // otherwise opening the dialog on a second task pre-selects the
              // person just assigned to the first.
              setPickedId(t.assigned_to_id);
              setAssigning(t);
            }}
            title={t.assigned_to_name ? "Reassign this task" : "Assign this task"}
          >
            {label}
            <UserPlus className="h-3 w-3 shrink-0 text-ink-300 group-hover:text-signal-700" />
          </button>
        );
      },
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
    <>
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

      {assigning && (
        <Modal
          open
          onClose={() => setAssigning(null)}
          title={`Assign ${assigning.code}`}
          description={assigning.name}
          footer={
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setAssigning(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={assign.isPending}
                onClick={() =>
                  assign.mutate(
                    { taskId: assigning.id, assignedToId: pickedId },
                    { onSuccess: () => setAssigning(null) },
                  )
                }
              >
                {assign.isPending && <Spinner />}
                {pickedId ? "Assign" : "Leave unassigned"}
              </button>
            </>
          }
        >
          <div className="space-y-3">
            <FormError error={assign.error} />
            {/* No requiredSkillId: the board reads the requirement and the
                window off the task itself when given task_id. */}
            <AssigneePicker
              taskId={assigning.id}
              requiredSkillId={null}
              selectedId={pickedId}
              onSelect={setPickedId}
            />
          </div>
        </Modal>
      )}
    </>
  );
}
