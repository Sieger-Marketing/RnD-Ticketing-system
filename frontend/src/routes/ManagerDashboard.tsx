/**
 * The Design Manager's operational command centre (spec section 23).
 */

import clsx from "clsx";
import { AlertTriangle, Ban, ClipboardCheck, FolderKanban, Layers } from "lucide-react";

import { CapacityHeatmap } from "@/components/CapacityHeatmap";
import { InsightList } from "@/components/InsightList";
import { TaskTable } from "@/components/TaskTable";
import {
  Card,
  ErrorState,
  HealthPill,
  KpiCard,
  PageHeader,
  ProgressBar,
  SkeletonRows,
  StatusBadge,
  toneFor,
} from "@/components/ui/primitives";
import { useDashboard } from "@/hooks/queries";
import { DASH, dateTime, hours, percent, variance } from "@/lib/format";
import type {
  CapacitySummary,
  DepartmentMetrics,
  Health,
  Insight,
  TaskSummary,
} from "@/types/api";

interface ReleaseProgressRow {
  id: string;
  code: string;
  name: string;
  project_code: string | null;
  status: string;
  health: Health;
  completion_percent: number;
  estimated_hours: number;
  actual_hours: number;
  effort_variance: number | null;
  efficiency_percent: number | null;
  delay_days: number;
  team_lead: string | null;
}

interface PendingReview {
  id: string;
  code: string;
  task_code: string | null;
  task_name: string | null;
  reviewer: string | null;
  submitted_at: string;
  round_number: number;
}

interface ManagerDashboardData {
  kpis: DepartmentMetrics;
  todays_workload: TaskSummary[];
  due_this_week: TaskSummary[];
  overdue_tasks: (TaskSummary & { delay_reason: string | null; team_lead: string | null })[];
  blocked_tasks: TaskSummary[];
  pending_reviews: PendingReview[];
  capacity_heatmap: CapacitySummary[];
  release_progress: ReleaseProgressRow[];
  insights: Insight[];
}

export default function ManagerDashboard() {
  const { data, isLoading, isError, error, refetch } =
    useDashboard<ManagerDashboardData>("manager");

  if (isLoading) {
    return (
      <>
        <PageHeader title="Design Manager" />
        <div className="card">
          <SkeletonRows rows={8} />
        </div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="Design Manager" />
        <div className="card">
          <ErrorState
            message={error instanceof Error ? error.message : undefined}
            onRetry={() => void refetch()}
          />
        </div>
      </>
    );
  }

  const k = data.kpis;

  return (
    <>
      <PageHeader
        title="Design Manager"
        subtitle="Operational view of the department, computed from live transactional data"
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          label="Active projects"
          value={k.active_projects}
          hint={`${k.completed_projects} completed`}
          icon={<FolderKanban className="h-4 w-4" />}
        />
        <KpiCard
          label="Active releases"
          value={k.active_releases}
          hint={`${k.overdue_releases} overdue`}
          tone={k.overdue_releases > 0 ? "warn" : "good"}
          icon={<Layers className="h-4 w-4" />}
        />
        <KpiCard
          label="Overdue tasks"
          value={k.overdue_tasks}
          tone={k.overdue_tasks > 0 ? "bad" : "good"}
          hint={`${k.active_tasks} open`}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <KpiCard
          label="Blocked"
          value={k.blocked_tasks}
          tone={k.blocked_tasks > 0 ? "warn" : "good"}
          hint="Waiting on something"
          icon={<Ban className="h-4 w-4" />}
        />
        <KpiCard
          label="Pending reviews"
          value={k.pending_reviews}
          hint={`${k.open_revisions} open revisions`}
          icon={<ClipboardCheck className="h-4 w-4" />}
        />
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          label="Efficiency"
          value={percent(k.efficiency_percent)}
          tone={toneFor(k.efficiency_percent, { good: 95, warn: 85 })}
          hint={`${hours(k.planned_hours)} planned vs ${hours(k.actual_hours)} actual`}
        />
        <KpiCard
          label="Utilisation"
          value={percent(k.utilization_percent)}
          hint={`${hours(k.available_hours)} available`}
        />
        <KpiCard
          label="On-time delivery"
          value={percent(k.on_time_percent)}
          tone={toneFor(k.on_time_percent, { good: 85, warn: 70 })}
          hint={`${k.completed_tasks} tasks completed`}
        />
        <KpiCard
          label="Rework"
          value={percent(k.rework_percent)}
          tone={toneFor(k.rework_percent, { good: 5, warn: 10, higherIsBetter: false })}
          hint={`${hours(k.rework_hours)} of rework`}
        />
        <KpiCard
          label="First-pass approval"
          value={percent(k.first_pass_approval_percent)}
          tone={toneFor(k.first_pass_approval_percent, { good: 85, warn: 70 })}
          hint="Approved without revision"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card
            title={`Overdue tasks (${data.overdue_tasks.length})`}
            bodyClassName=""
          >
            {data.overdue_tasks.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                Nothing is overdue.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px]">
                  <thead className="border-b border-ink-200 bg-ink-50">
                    <tr>
                      <th className="th">Task</th>
                      <th className="th">Assignee</th>
                      <th className="th">Team lead</th>
                      <th className="th">Project</th>
                      <th className="th text-right">Delay</th>
                      <th className="th">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-100">
                    {data.overdue_tasks.slice(0, 15).map((task) => (
                      <tr key={task.id} className="hover:bg-ink-50">
                        <td className="td max-w-[18rem]">
                          <div className="truncate font-medium text-ink-900">
                            {task.name}
                          </div>
                          <div className="font-mono text-2xs text-ink-400">
                            {task.code}
                          </div>
                        </td>
                        <td className="td text-xs">
                          {task.assigned_to_name ?? (
                            <span className="text-ink-400">Unassigned</span>
                          )}
                        </td>
                        <td className="td text-xs text-ink-600">
                          {task.team_lead ?? DASH}
                        </td>
                        <td className="td text-xs text-ink-600">
                          {task.project_code ?? DASH}
                        </td>
                        <td className="td text-right text-xs font-semibold text-rag-red">
                          {task.delay_days}d
                        </td>
                        <td className="td text-xs">
                          {task.delay_reason ?? (
                            <span className="text-rag-amber">Not stated</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.overdue_tasks.length > 15 && (
                  <p className="border-t border-ink-100 px-3 py-2 text-2xs text-ink-500">
                    Showing 15 of {data.overdue_tasks.length}
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card title="Release progress" bodyClassName="">
            {data.release_progress.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                No active releases.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px]">
                  <thead className="border-b border-ink-200 bg-ink-50">
                    <tr>
                      <th className="th">Release</th>
                      <th className="th">Lead</th>
                      <th className="th">Status</th>
                      <th className="th w-36">Completion</th>
                      <th className="th text-right">Est / Act</th>
                      <th className="th text-right">Variance</th>
                      <th className="th">Health</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-100">
                    {data.release_progress.map((r) => (
                      <tr key={r.id} className="hover:bg-ink-50">
                        <td className="td max-w-[18rem]">
                          <div className="truncate font-medium text-ink-900">
                            {r.name}
                          </div>
                          <div className="font-mono text-2xs text-ink-400">
                            {r.code} · {r.project_code}
                          </div>
                        </td>
                        <td className="td text-xs text-ink-600">{r.team_lead ?? DASH}</td>
                        <td className="td">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="td">
                          <ProgressBar
                            value={r.completion_percent}
                            tone={r.health === "RED" ? "red" : r.health === "AMBER" ? "amber" : "brand"}
                          />
                        </td>
                        <td className="td text-right text-xs tabular text-ink-600">
                          {hours(r.estimated_hours)} / {hours(r.actual_hours)}
                        </td>
                        <td
                          className={clsx(
                            "td text-right text-xs tabular",
                            (r.effort_variance ?? 0) > 0
                              ? "font-medium text-rag-amber"
                              : "text-ink-600",
                          )}
                        >
                          {variance(r.effort_variance)}
                        </td>
                        <td className="td">
                          <HealthPill health={r.health} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card
            title={`Today's workload (${data.todays_workload.length})`}
            bodyClassName=""
          >
            <TaskTable
              tasks={data.todays_workload}
              columns={["code", "name", "assignee", "project", "priority", "status"]}
              emptyTitle="Nothing due today"
            />
          </Card>

          {data.blocked_tasks.length > 0 && (
            <Card
              title={`Blocked (${data.blocked_tasks.length})`}
              bodyClassName=""
            >
              <div className="divide-y divide-ink-100">
                {data.blocked_tasks.map((task) => (
                  <div key={task.id} className="px-4 py-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink-900">
                          {task.name}
                        </p>
                        <p className="font-mono text-2xs text-ink-400">
                          {task.code} · {task.assigned_to_name ?? "Unassigned"}
                        </p>
                      </div>
                      <StatusBadge status={task.status} />
                    </div>
                    {task.blocker_reason && (
                      <p className="mt-1 text-xs text-rag-red">{task.blocker_reason}</p>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="What needs attention" bodyClassName="">
            <InsightList insights={data.insights} />
          </Card>

          <Card
            title={`Review queue (${data.pending_reviews.length})`}
            bodyClassName=""
          >
            {data.pending_reviews.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                No reviews waiting.
              </div>
            ) : (
              <ul className="divide-y divide-ink-100">
                {data.pending_reviews.slice(0, 10).map((review) => (
                  <li key={review.id} className="px-3 py-2">
                    <p className="truncate text-xs font-medium text-ink-900">
                      {review.task_name}
                    </p>
                    <p className="text-2xs text-ink-500">
                      {review.task_code} · round {review.round_number} ·{" "}
                      {review.reviewer ?? "Unrouted"}
                    </p>
                    <p className="text-2xs text-ink-400">
                      submitted {dateTime(review.submitted_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Card className="mt-4" title="Capacity heatmap — next 14 days" bodyClassName="p-4">
        <CapacityHeatmap rows={data.capacity_heatmap} />
      </Card>
    </>
  );
}
