/**
 * "My Work" — the designer's personal workspace (spec section 25).
 */

import { CalendarClock, CheckCircle2, Clock, RefreshCcw } from "lucide-react";

import { TaskTable } from "@/components/TaskTable";
import {
  Card,
  ErrorState,
  KpiCard,
  PageHeader,
  SkeletonRows,
  Stat,
  UtilizationBadge,
  toneFor,
} from "@/components/ui/primitives";
import { useDashboard } from "@/hooks/queries";
import { DASH, durationHours, hours, percent } from "@/lib/format";
import { useAuth } from "@/store/auth";
import type { DesignerMetrics, TaskSummary } from "@/types/api";

interface DesignerDashboardData {
  kpis: DesignerMetrics;
  todays_tasks: TaskSummary[];
  upcoming_tasks: TaskSummary[];
  overdue_tasks: TaskSummary[];
  in_review: TaskSummary[];
  revision_required: TaskSummary[];
  recently_completed: TaskSummary[];
}

export default function DesignerDashboard() {
  const user = useAuth((s) => s.user);
  const { data, isLoading, isError, error, refetch } =
    useDashboard<DesignerDashboardData>("designer");

  if (isLoading) {
    return (
      <>
        <PageHeader title="My Work" />
        <div className="card">
          <SkeletonRows rows={6} />
        </div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="My Work" />
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
  const score = k.performance_score.score;

  return (
    <>
      <PageHeader
        title="My Work"
        subtitle={`${user?.full_name ?? ""} · ${k.period.from} to ${k.period.to}`}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard
          label="Open tasks"
          value={k.tasks_pending}
          hint={`${k.tasks_assigned} assigned overall`}
          icon={<Clock className="h-4 w-4" />}
        />
        <KpiCard
          label="Overdue"
          value={k.tasks_overdue}
          tone={k.tasks_overdue > 0 ? "bad" : "good"}
          hint={k.tasks_overdue > 0 ? "Needs attention" : "Nothing late"}
          icon={<CalendarClock className="h-4 w-4" />}
        />
        <KpiCard
          label="Completed"
          value={k.tasks_completed}
          hint="This period"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <KpiCard
          label="Efficiency"
          value={percent(k.efficiency_percent)}
          tone={toneFor(k.efficiency_percent, { good: 95, warn: 80 })}
          hint={`${hours(k.planned_hours)} planned vs ${hours(k.actual_hours)} actual`}
        />
        <KpiCard
          label="Utilisation"
          value={percent(k.utilization_percent)}
          tone={
            k.utilization_band === "Overloaded"
              ? "bad"
              : k.utilization_band === "High Load"
                ? "warn"
                : "good"
          }
          hint={k.utilization_band}
        />
        <KpiCard
          label="Performance"
          value={score === null ? DASH : Math.round(score)}
          tone={toneFor(score, { good: 80, warn: 60 })}
          hint="Weighted score"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {data.revision_required.length > 0 && (
            <Card
              title={
                <span className="flex items-center gap-1.5 text-rag-amber">
                  <RefreshCcw className="h-3.5 w-3.5" />
                  Rework required ({data.revision_required.length})
                </span>
              }
              bodyClassName=""
            >
              <TaskTable
                tasks={data.revision_required}
                columns={["code", "name", "project", "due", "hours"]}
                emptyTitle="Nothing to rework"
              />
            </Card>
          )}

          {data.overdue_tasks.length > 0 && (
            <Card
              title={
                <span className="text-rag-red">
                  Overdue ({data.overdue_tasks.length})
                </span>
              }
              bodyClassName=""
            >
              <TaskTable
                tasks={data.overdue_tasks}
                columns={["code", "name", "status", "due", "delay", "progress"]}
              />
            </Card>
          )}

          <Card title={`Due today (${data.todays_tasks.length})`} bodyClassName="">
            <TaskTable
              tasks={data.todays_tasks}
              columns={["code", "name", "status", "priority", "progress"]}
              emptyTitle="Nothing due today"
              emptyDescription="Your next deadlines are in the upcoming list."
            />
          </Card>

          <Card title={`Upcoming this week (${data.upcoming_tasks.length})`} bodyClassName="">
            <TaskTable
              tasks={data.upcoming_tasks}
              columns={["code", "name", "status", "due", "priority"]}
              emptyTitle="Nothing scheduled this week"
            />
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Awaiting review" bodyClassName="">
            <TaskTable
              tasks={data.in_review}
              columns={["code", "name", "status"]}
              emptyTitle="Nothing with a reviewer"
              emptyDescription="Work you submit will appear here until it is reviewed."
            />
          </Card>

          <Card title="My performance">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="On-time" value={percent(k.on_time_percent)} />
              <Stat label="First-pass approval" value={percent(k.first_pass_approval_percent)} />
              <Stat label="Rework" value={percent(k.rework_percent)} />
              <Stat label="Rework hours" value={hours(k.rework_hours)} />
              <Stat label="Avg cycle time" value={durationHours(k.average_cycle_time_hours)} />
              <Stat label="Avg queue time" value={durationHours(k.average_queue_time_hours)} />
              <Stat label="Logged hours" value={hours(k.logged_hours)} />
              <Stat label="Blocked hours" value={hours(k.blocked_hours)} />
            </dl>

            <div className="mt-4 border-t border-ink-100 pt-3">
              <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-500">
                Score breakdown
              </p>
              <div className="space-y-1.5">
                {Object.entries(k.performance_score.components).map(([name, value]) => (
                  <div key={name} className="flex items-center justify-between gap-2">
                    <span className="text-xs capitalize text-ink-600">
                      {name.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs tabular text-ink-800">
                      {value === null ? (
                        <span className="text-ink-400" title="Not enough data yet">
                          {DASH}
                        </span>
                      ) : (
                        Math.round(value)
                      )}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-2xs text-ink-400">
                Components with no data are excluded and the remaining weights are
                rebalanced, so new work is never scored as zero.
              </p>
            </div>
          </Card>

          <Card title="Capacity">
            <div className="flex items-center justify-between">
              <span className="text-xs text-ink-600">Next two weeks</span>
              <UtilizationBadge band={k.utilization_band} value={k.utilization_percent} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3">
              <Stat label="Available" value={hours(k.available_hours)} />
              <Stat label="Allocated" value={hours(k.allocated_hours)} />
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
