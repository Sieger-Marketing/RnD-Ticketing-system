/**
 * Kanban board (spec section 10).
 *
 * Dragging a card asks the backend for the status change; it does not decide
 * locally whether the move is legal. An illegal move comes back as the state
 * machine's own message ("a task cannot go from Not Started to Approved"),
 * which is more useful than a disabled drop target that never explains itself.
 */

import clsx from "clsx";
import { AlertTriangle, LayoutGrid, List } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Field, FormError, Select, TextArea } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Avatar,
  CountBadge,
  ErrorState,
  InlineAlert,
  PageHeader,
  PriorityLabel,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import {
  useDelayReasons,
  useKanban,
  useMoveTask,
  useProjects,
} from "@/hooks/queries";
import { hours, shortDate } from "@/lib/format";
import type { TaskStatus, TaskSummary } from "@/types/api";

/**
 * Where a column drop lands. Not simply the column's first status: the
 * "Completed" column covers Approved and Completed, and dragging a card there
 * means finished, not awaiting sign-off.
 */
const COLUMN_TARGET: Record<string, TaskStatus> = {
  not_started: "Not Started",
  assigned: "Assigned",
  in_progress: "In Progress",
  blocked: "Blocked",
  review: "Submitted for Review",
  revision: "Revision Required",
  completed: "Completed",
};

const COLUMN_ACCENT: Record<string, string> = {
  not_started: "border-t-ink-300",
  assigned: "border-t-ink-400",
  in_progress: "border-t-ink-700",
  blocked: "border-t-rag-red",
  review: "border-t-rag-amber",
  revision: "border-t-rag-amber",
  completed: "border-t-rag-green",
};

/**
 * States the API refuses for an overdue task unless a delay reason comes with
 * the move. Mirrors the rule in task_service.
 */
const NEEDS_DELAY_REASON: TaskStatus[] = ["Completed", "Submitted for Review"];

interface PendingMove {
  task: TaskSummary;
  status: TaskStatus;
  /** Which question the move has to answer before it can go through. */
  ask: "blocker" | "delay";
}

export default function Kanban() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const projectId = params.get("project_id") ?? "";

  const [dragging, setDragging] = useState<TaskSummary | null>(null);
  const [hoverColumn, setHoverColumn] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingMove | null>(null);
  const [note, setNote] = useState("");
  const [delayReason, setDelayReason] = useState("");
  const [moveError, setMoveError] = useState<unknown>(null);

  const board = useKanban({ project_id: projectId || undefined });
  const { data: projects } = useProjects({ page_size: 100 });
  const { data: delayReasonRows } = useDelayReasons();

  const move = useMoveTask();

  // Each row carries whether the reason is controllable or external; the
  // label shows it so the choice is made knowingly.
  const delayReasons = delayReasonRows ?? [];

  const applyMove = (
    task: TaskSummary,
    status: TaskStatus,
    body: { note?: string; delay_reason?: string } = {},
  ) => {
    setMoveError(null);
    move.mutate(
      { taskId: task.id, status, ...body },
      {
        onSuccess: () => {
          setPending(null);
          setNote("");
          setDelayReason("");
        },
        onError: (error) => setMoveError(error),
      },
    );
  };

  const handleDrop = (columnKey: string, event: React.DragEvent) => {
    // The dragged task travels in the DataTransfer, not in React state: state
    // set on dragstart has not necessarily committed by the time drop fires,
    // and a drop that silently does nothing is the worst kind of bug.
    const taskId = event.dataTransfer.getData("text/plain") || dragging?.id;
    setDragging(null);
    setHoverColumn(null);
    if (!taskId) return;

    const task =
      board.data?.columns.flatMap((c) => c.tasks).find((t) => t.id === taskId) ?? null;
    if (!task) return;

    const status = COLUMN_TARGET[columnKey];
    if (!status || status === task.status) return;

    // Blocking without a stated reason is refused by the API, so ask for one
    // here rather than letting the drop fail and explaining afterwards.
    if (status === "Blocked") {
      setMoveError(null);
      setNote("");
      setDelayReason("");
      setPending({ task, status, ask: "blocker" });
      return;
    }

    // Dropping an overdue card onto Completed or Review used to fail with "a
    // delay reason is required" and offer nowhere to give one.
    if (task.is_overdue && NEEDS_DELAY_REASON.includes(status)) {
      setMoveError(null);
      setNote("");
      setDelayReason("");
      setPending({ task, status, ask: "delay" });
      return;
    }

    applyMove(task, status);
  };

  return (
    <>
      <PageHeader
        title="Task Board"
        subtitle={board.data ? `${board.data.total} tasks` : undefined}
        actions={
          <div className="flex items-center gap-2">
            <select
              className="input w-auto py-1.5 text-xs"
              value={projectId}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                if (e.target.value) next.set("project_id", e.target.value);
                else next.delete("project_id");
                setParams(next, { replace: true });
              }}
              aria-label="Filter by project"
            >
              <option value="">All projects</option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-1 rounded-md border border-ink-300 p-0.5">
              <Link to="/tasks" className="btn-ghost px-2 py-1">
                <List className="h-3.5 w-3.5" />
                List
              </Link>
              <span className="btn bg-ink-900 px-2 py-1 text-white">
                <LayoutGrid className="h-3.5 w-3.5" />
                Board
              </span>
            </div>
          </div>
        }
      />

      {moveError && !pending && (
        <div className="mb-3">
          <FormError error={moveError} />
        </div>
      )}

      {board.isLoading && (
        <div className="card">
          <SkeletonRows rows={8} cols={7} />
        </div>
      )}

      {board.isError && (
        <div className="card">
          <ErrorState
            message={board.error instanceof Error ? board.error.message : undefined}
            onRetry={() => void board.refetch()}
          />
        </div>
      )}

      {board.data && (
        <div className="snap-columns -mx-3 flex gap-3 overflow-x-auto px-3 pb-4 sm:mx-0 sm:px-0">
          {board.data.columns.map((column) => (
            <div
              key={column.key}
              className={clsx(
                "snap-column flex w-[78vw] max-w-[17rem] shrink-0 flex-col rounded-lg border border-t-2 bg-cream-100 transition-colors sm:w-64",
                COLUMN_ACCENT[column.key] ?? "border-t-ink-300",
                hoverColumn === column.key
                  ? "border-signal-400 bg-signal-50"
                  : "border-ink-200",
              )}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                setHoverColumn(column.key);
              }}
              onDragLeave={() => setHoverColumn((c) => (c === column.key ? null : c))}
              onDrop={(e) => {
                e.preventDefault();
                handleDrop(column.key, e);
              }}
            >
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <h2 className="text-xs font-semibold text-ink-800">{column.title}</h2>
                <CountBadge count={column.count} />
              </div>

              <div className="flex-1 space-y-2 px-2 pb-2">
                {column.tasks.length === 0 && (
                  <p className="px-1 py-6 text-center text-2xs text-ink-400">
                    Nothing here
                  </p>
                )}

                {column.tasks.map((task) => (
                  <article
                    key={task.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/plain", task.id);
                      e.dataTransfer.effectAllowed = "move";
                      setDragging(task);
                    }}
                    onDragEnd={() => {
                      setDragging(null);
                      setHoverColumn(null);
                    }}
                    onClick={() => navigate(`/tasks/${task.id}`)}
                    className={clsx(
                      "cursor-pointer rounded-md border bg-white p-2 shadow-sm transition-opacity hover:border-signal-300",
                      dragging?.id === task.id ? "opacity-40" : "opacity-100",
                      task.is_overdue ? "border-rag-red/40" : "border-ink-200",
                    )}
                  >
                    <p className="text-xs font-medium leading-snug text-ink-900">
                      {task.name}
                    </p>
                    <p className="mt-0.5 font-mono text-2xs text-ink-400">
                      {task.code} · {task.project_code}
                    </p>

                    {task.blocker_reason && (
                      <p className="mt-1 flex items-start gap-1 text-2xs text-rag-red">
                        <AlertTriangle className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                        {task.blocker_reason}
                      </p>
                    )}

                    <div className="mt-2 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {task.assigned_to_name ? (
                          <Avatar name={task.assigned_to_name} />
                        ) : (
                          <span className="text-2xs text-ink-400">Unassigned</span>
                        )}
                        <PriorityLabel priority={task.priority} />
                      </div>
                      <span
                        className={clsx(
                          "text-2xs tabular",
                          task.is_overdue ? "font-medium text-rag-red" : "text-ink-500",
                        )}
                      >
                        {shortDate(task.planned_end)}
                      </span>
                    </div>

                    <p className="mt-1 text-2xs text-ink-400">
                      {hours(task.estimated_hours)} est · {hours(task.actual_hours)} actual
                      {task.revision_count > 0 && ` · ${task.revision_count} rev`}
                    </p>
                  </article>
                ))}

                {column.count > column.tasks.length && (
                  <p className="px-1 py-1 text-center text-2xs text-ink-500">
                    +{column.count - column.tasks.length} more
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={pending?.ask === "delay"}
        onClose={() => {
          setPending(null);
          setMoveError(null);
        }}
        title={`Move to ${pending?.status ?? ""}`}
        description={pending ? `${pending.task.code} — ${pending.task.name}` : undefined}
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setPending(null);
                setMoveError(null);
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                pending &&
                applyMove(pending.task, pending.status, { delay_reason: delayReason })
              }
              disabled={move.isPending || !delayReason}
            >
              {move.isPending && <Spinner />}
              Confirm
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={moveError} />
          <InlineAlert tone="warn">
            This task is {pending?.task.delay_days} day
            {pending?.task.delay_days === 1 ? "" : "s"} past its planned end date.
            The reason separates delays the team could control from those it
            could not.
          </InlineAlert>
          <Field label="Delay reason" htmlFor="board_delay" required>
            <Select
              id="board_delay"
              value={delayReason}
              onChange={(e) => setDelayReason(e.target.value)}
              placeholder="Choose a reason"
              options={delayReasons.map((r) => ({
                value: r.value,
                label: `${r.value} (${r.accountability.toLowerCase()})`,
              }))}
            />
          </Field>
        </div>
      </Modal>

      <Modal
        open={pending?.ask === "blocker"}
        onClose={() => {
          setPending(null);
          setMoveError(null);
        }}
        title="Why is this blocked?"
        description={pending ? `${pending.task.code} — ${pending.task.name}` : undefined}
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setPending(null);
                setMoveError(null);
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                pending &&
                applyMove(pending.task, pending.status, {
                  note,
                  ...(delayReason ? { delay_reason: delayReason } : {}),
                })
              }
              disabled={move.isPending || note.trim().length < 5}
            >
              {move.isPending && <Spinner />}
              Block task
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={moveError} />
          <InlineAlert tone="info">
            Blocked time is measured against this task, and the reason appears on
            the manager's dashboard. It is worth being specific.
          </InlineAlert>

          <Field label="What is it waiting on?" htmlFor="blocker" required>
            <TextArea
              id="blocker"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Vendor has not confirmed the drive unit envelope."
            />
          </Field>

          {delayReasons.length > 0 && (
            <Field
              label="Category"
              htmlFor="delay_reason"
              hint="Used to separate controllable delays from external ones."
            >
              <Select
                id="delay_reason"
                value={delayReason}
                onChange={(e) => setDelayReason(e.target.value)}
                placeholder="Not categorised"
                options={delayReasons.map((r) => ({
                  value: r.value,
                  label: `${r.value} (${r.accountability.toLowerCase()})`,
                }))}
              />
            </Field>
          )}
        </div>
      </Modal>
    </>
  );
}
