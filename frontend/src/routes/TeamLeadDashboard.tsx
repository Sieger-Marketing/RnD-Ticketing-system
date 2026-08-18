/**
 * The Team Lead's view (spec section 24): my releases, my team, my queue.
 */

import { CalendarClock, ClipboardCheck, Layers, Users } from "lucide-react";

import { TaskTable } from "@/components/TaskTable";
import {
  Card,
  ErrorState,
  HealthPill,
  KpiCard,
  PageHeader,
  ProgressBar,
  SkeletonRows,
  Stat,
  StatusBadge,
  UtilizationBadge,
  toneFor,
} from "@/components/ui/primitives";
import { useDashboard } from "@/hooks/queries";
import { DASH, dateTime, durationHours, hours, percent, shortDate } from "@/lib/format";
import type { CapacitySummary, Health, HealthReason, TaskSummary } from "@/types/api";

interface LeadRelease {
  id: string;
  code: string;
  name: string;
  project_code: string | null;
  status: string;
  health: Health;
  completion_percent: number;
  delay_days: number;
  planned_end: string | null;
  health_reasons: HealthReason[];
}

interface LeadKpis {
  user: { id: string; full_name: string };
  period: { from: string; to: string };
  releases_assigned: number;
  releases_completed: number;
  releases_delayed: number;
  team_size: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  team_efficiency_percent: number | null;
  team_utilization_percent: number | null;
  team_on_time_percent: number | null;
  rework_percent: number | null;
  revision_rate_percent: number | null;
  average_review_turnaround_hours: number | null;
  first_pass_approval_percent: number | null;
  pending_reviews: number;
  blocked_tasks: number;
  overdue_tasks: number;
  team_capacity: CapacitySummary[];
}

interface TeamLeadDashboardData {
  kpis: LeadKpis;
  my_releases: LeadRelease[];
  team: CapacitySummary[];
  tasks_due_today: TaskSummary[];
  overdue_tasks: TaskSummary[];
  blocked_tasks: TaskSummary[];
  review_queue: {
    id: string;
    code: string;
    task_code: string | null;
    task_name: string | null;
    submitted_at: string;
    round_number: number;
    submitted_by: string | null;
  }[];
}

export default function TeamLeadDashboard() {
  const { data, isLoading, isError, error, refetch } =
    useDashboard<TeamLeadDashboardData>("team-lead");

  if (isLoading) {
    return (
      <>
        <PageHeader title="My Team" />
        <div className="card">
          <SkeletonRows rows={7} />
        </div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="My Team" />
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
        title="My Team"
        subtitle={`${k.user.full_name} · ${k.team_size} designer${k.team_size === 1 ? "" : "s"}`}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard
          label="My releases"
          value={k.releases_assigned}
          hint={`${k.releases_completed} completed`}
          icon={<Layers className="h-4 w-4" />}
        />
        <KpiCard
          label="Delayed"
          value={k.releases_delayed}
          tone={k.releases_delayed > 0 ? "bad" : "good"}
          hint="Releases behind schedule"
          icon={<CalendarClock className="h-4 w-4" />}
        />
        <KpiCard
          label="Team utilisation"
          value={percent(k.team_utilization_percent)}
          tone={
            (k.team_utilization_percent ?? 0) > 100
              ? "bad"
              : (k.team_utilization_percent ?? 0) > 90
                ? "warn"
                : "good"
          }
          icon={<Users className="h-4 w-4" />}
        />
        <KpiCard
          label="Team efficiency"
          value={percent(k.team_efficiency_percent)}
          tone={toneFor(k.team_efficiency_percent, { good: 95, warn: 85 })}
        />
        <KpiCard
          label="Pending reviews"
          value={k.pending_reviews}
          hint={durationHours(k.average_review_turnaround_hours) + " avg turnaround"}
          icon={<ClipboardCheck className="h-4 w-4" />}
        />
        <KpiCard
          label="Overdue tasks"
          value={k.overdue_tasks}
          tone={k.overdue_tasks > 0 ? "bad" : "good"}
          hint={`${k.blocked_tasks} blocked`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title={`My releases (${data.my_releases.length})`} bodyClassName="">
            {data.my_releases.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                No releases assigned to you.
              </div>
            ) : (
              <div className="divide-y divide-ink-100">
                {data.my_releases.map((release) => (
                  <div key={release.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink-900">
                          {release.name}
                        </p>
                        <p className="font-mono text-2xs text-ink-400">
                          {release.code} · {release.project_code} · due{" "}
                          {shortDate(release.planned_end)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={release.status} />
                        <HealthPill health={release.health} />
                      </div>
                    </div>
                    <div className="mt-2 max-w-md">
                      <ProgressBar
                        value={release.completion_percent}
                        tone={
                          release.health === "RED"
                            ? "red"
                            : release.health === "AMBER"
                              ? "amber"
                              : "brand"
                        }
                      />
                    </div>
                    {release.health_reasons.length > 0 && (
                      <ul className="mt-2 space-y-0.5">
                        {release.health_reasons.map((reason, i) => (
                          <li
                            key={i}
                            className={
                              reason.level === "RED"
                                ? "text-2xs text-rag-red"
                                : "text-2xs text-rag-amber"
                            }
                          >
                            • {reason.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title={`Overdue (${data.overdue_tasks.length})`} bodyClassName="">
            <TaskTable
              tasks={data.overdue_tasks}
              columns={["code", "name", "assignee", "due", "delay", "status"]}
              emptyTitle="Nothing overdue in your team"
            />
          </Card>

          <Card title={`Due today (${data.tasks_due_today.length})`} bodyClassName="">
            <TaskTable
              tasks={data.tasks_due_today}
              columns={["code", "name", "assignee", "status", "progress"]}
              emptyTitle="Nothing due today"
            />
          </Card>

          {data.blocked_tasks.length > 0 && (
            <Card title={`Blocked (${data.blocked_tasks.length})`} bodyClassName="">
              <div className="divide-y divide-ink-100">
                {data.blocked_tasks.map((task) => (
                  <div key={task.id} className="px-4 py-2.5">
                    <p className="text-sm font-medium text-ink-900">{task.name}</p>
                    <p className="font-mono text-2xs text-ink-400">
                      {task.code} · {task.assigned_to_name ?? "Unassigned"}
                    </p>
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
          <Card title={`Review queue (${data.review_queue.length})`} bodyClassName="">
            {data.review_queue.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                Your queue is clear.
              </div>
            ) : (
              <ul className="divide-y divide-ink-100">
                {data.review_queue.map((review) => (
                  <li key={review.id} className="px-3 py-2">
                    <p className="truncate text-xs font-medium text-ink-900">
                      {review.task_name}
                    </p>
                    <p className="text-2xs text-ink-500">
                      {review.task_code} · round {review.round_number} ·{" "}
                      {review.submitted_by ?? DASH}
                    </p>
                    <p className="text-2xs text-ink-400">
                      submitted {dateTime(review.submitted_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Team workload" bodyClassName="">
            {data.team.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-ink-500">
                No designers report to you yet.
              </div>
            ) : (
              <ul className="divide-y divide-ink-100">
                {data.team.map((member) => (
                  <li
                    key={member.user_id}
                    className="flex items-center justify-between gap-2 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-ink-900">
                        {member.full_name}
                      </p>
                      <p className="text-2xs text-ink-500">
                        {member.open_tasks} open · {hours(member.allocated_hours)} of{" "}
                        {hours(member.available_hours)}
                      </p>
                    </div>
                    <UtilizationBadge
                      band={member.utilization_band}
                      value={member.utilization_percent}
                    />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Quality and delivery">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="On-time" value={percent(k.team_on_time_percent)} />
              <Stat label="First-pass" value={percent(k.first_pass_approval_percent)} />
              <Stat label="Rework" value={percent(k.rework_percent)} />
              <Stat label="Rework hours" value={hours(k.rework_hours)} />
              <Stat label="Revision rate" value={percent(k.revision_rate_percent)} />
              <Stat
                label="Review turnaround"
                value={durationHours(k.average_review_turnaround_hours)}
              />
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
