/**
 * The task table used across dashboards and lists.
 *
 * Columns are opt-in so the same component serves a designer's personal queue
 * (who cares about due date and status) and a manager's overdue list (who also
 * needs the assignee, the project and the delay reason).
 */

import clsx from "clsx";
import { AlertTriangle } from "lucide-react";

import {
  Avatar,
  EmptyState,
  PriorityLabel,
  ProgressBar,
  StatusBadge,
} from "@/components/ui/primitives";
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
  | "delay";

const DEFAULT_COLUMNS: TaskColumn[] = [
  "code",
  "name",
  "status",
  "priority",
  "due",
  "progress",
];

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
  if (tasks.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  const rows = maxRows ? tasks.slice(0, maxRows) : tasks;
  const has = (c: TaskColumn) => columns.includes(c);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <thead className="border-b border-ink-200 bg-ink-50">
          <tr>
            {has("code") && <th className="th">Task</th>}
            {has("name") && <th className="th">Description</th>}
            {has("project") && <th className="th">Project</th>}
            {has("assignee") && <th className="th">Assignee</th>}
            {has("status") && <th className="th">Status</th>}
            {has("priority") && <th className="th">Priority</th>}
            {has("due") && <th className="th">Due</th>}
            {has("progress") && <th className="th w-32">Progress</th>}
            {has("hours") && <th className="th text-right">Est / Act</th>}
            {has("delay") && <th className="th">Delay</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {rows.map((task) => (
            <tr
              key={task.id}
              className={clsx(
                "hover:bg-ink-50",
                onSelect && "cursor-pointer",
                task.is_overdue && "bg-rag-redBg/30",
              )}
              onClick={onSelect ? () => onSelect(task) : undefined}
            >
              {has("code") && (
                <td className="td font-mono text-2xs text-ink-500">{task.code}</td>
              )}
              {has("name") && (
                <td className="td max-w-[22rem]">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate font-medium text-ink-900" title={task.name}>
                      {task.name}
                    </span>
                    {task.blocker_reason && (
                      <AlertTriangle
                        className="h-3.5 w-3.5 shrink-0 text-rag-red"
                        aria-label="Blocked"
                      />
                    )}
                  </div>
                  <span className="text-2xs text-ink-400">{task.task_type}</span>
                </td>
              )}
              {has("project") && (
                <td className="td text-xs text-ink-600">{task.project_code ?? DASH}</td>
              )}
              {has("assignee") && (
                <td className="td">
                  {task.assigned_to_name ? (
                    <span className="flex items-center gap-1.5">
                      <Avatar name={task.assigned_to_name} />
                      <span className="text-xs">{task.assigned_to_name}</span>
                    </span>
                  ) : (
                    <span className="text-xs text-ink-400">Unassigned</span>
                  )}
                </td>
              )}
              {has("status") && (
                <td className="td">
                  <StatusBadge status={task.status} />
                </td>
              )}
              {has("priority") && (
                <td className="td">
                  <PriorityLabel priority={task.priority} />
                </td>
              )}
              {has("due") && (
                <td
                  className={clsx(
                    "td text-xs",
                    task.is_overdue ? "font-medium text-rag-red" : "text-ink-600",
                  )}
                >
                  {shortDate(task.planned_end)}
                </td>
              )}
              {has("progress") && (
                <td className="td">
                  <ProgressBar
                    value={task.completion_percent}
                    tone={task.is_overdue ? "amber" : "brand"}
                  />
                </td>
              )}
              {has("hours") && (
                <td className="td text-right text-xs tabular">
                  <span className="text-ink-500">{hours(task.estimated_hours)}</span>
                  <span className="mx-1 text-ink-300">/</span>
                  <span
                    className={clsx(
                      task.actual_hours > task.estimated_hours && task.estimated_hours > 0
                        ? "font-medium text-rag-amber"
                        : "text-ink-800",
                    )}
                  >
                    {hours(task.actual_hours)}
                  </span>
                </td>
              )}
              {has("delay") && (
                <td className="td text-xs">
                  {task.delay_days > 0 ? (
                    <span className="font-medium text-rag-red">
                      {task.delay_days}d
                    </span>
                  ) : (
                    <span className="text-ink-400">{DASH}</span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {maxRows && tasks.length > maxRows && (
        <p className="border-t border-ink-100 px-3 py-2 text-2xs text-ink-500">
          Showing {maxRows} of {tasks.length}
        </p>
      )}
    </div>
  );
}
