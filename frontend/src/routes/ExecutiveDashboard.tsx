/**
 * The Director's dashboard (spec section 22).
 *
 * Weighted towards exceptions and trends rather than task-level detail: a
 * Director needs to know which projects are in trouble and where the
 * department is heading, not what any individual is doing today.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { InsightList } from "@/components/InsightList";
import {
  Card,
  ErrorState,
  HealthPill,
  KpiCard,
  PageHeader,
  ProgressBar,
  SkeletonRows,
  UtilizationBadge,
  toneFor,
} from "@/components/ui/primitives";
import { useDashboard } from "@/hooks/queries";
import { DASH, durationHours, hours, percent } from "@/lib/format";
import type {
  DepartmentMetrics,
  Health,
  HealthReason,
  Insight,
  MonthlyTrend,
  PerformanceScore,
  UtilizationBand,
} from "@/types/api";

interface LeadPerformance {
  id: string;
  full_name: string;
  releases_assigned: number;
  releases_completed: number;
  releases_delayed: number;
  team_efficiency_percent: number | null;
  team_utilization_percent: number | null;
  team_on_time_percent: number | null;
  rework_percent: number | null;
  first_pass_approval_percent: number | null;
  average_review_turnaround_hours: number | null;
}

interface DesignerPerformance {
  id: string;
  full_name: string;
  tasks_completed: number;
  efficiency_percent: number | null;
  utilization_percent: number | null;
  utilization_band: UtilizationBand;
  on_time_percent: number | null;
  rework_percent: number | null;
  first_pass_approval_percent: number | null;
  performance_score: PerformanceScore;
}

interface ExecutiveDashboardData {
  kpis: DepartmentMetrics;
  project_pipeline: { status: string; count: number }[];
  capacity_vs_demand: {
    available_hours: number;
    allocated_hours: number;
    utilization_percent: number | null;
    people: number;
  };
  monthly_output: MonthlyTrend[];
  team_lead_performance: LeadPerformance[];
  designer_performance: DesignerPerformance[];
  delayed_projects: {
    id: string;
    code: string;
    name: string;
    customer: string | null;
    health: Health;
    delay_days: number;
    completion_percent: number;
    reasons: HealthReason[];
  }[];
  bottlenecks: {
    slowest_reviews: { code: string; task_code: string | null; reviewer: string | null; turnaround_hours: number }[];
    blocked_tasks: { code: string; name: string; assigned_to: string | null; blocker_reason: string | null }[];
  };
  insights: Insight[];
}

const CHART_COLORS = {
  brand: "#3363f5",
  green: "#16a34a",
  amber: "#d97706",
  red: "#dc2626",
  grid: "#e5e7eb",
  axis: "#8494ab",
};

const HEALTH_FILL: Record<Health, string> = {
  GREEN: CHART_COLORS.green,
  AMBER: CHART_COLORS.amber,
  RED: CHART_COLORS.red,
};

export default function ExecutiveDashboard() {
  const { data, isLoading, isError, error, refetch } =
    useDashboard<ExecutiveDashboardData>("executive");

  if (isLoading) {
    return (
      <>
        <PageHeader title="Executive Overview" />
        <div className="card">
          <SkeletonRows rows={8} />
        </div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="Executive Overview" />
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
  const healthData = (Object.keys(k.health_breakdown) as Health[]).map((health) => ({
    health,
    count: k.health_breakdown[health],
  }));

  return (
    <>
      <PageHeader
        title="Executive Overview"
        subtitle={`Department performance, ${k.period.from} to ${k.period.to}`}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
        <KpiCard label="Active projects" value={k.active_projects} />
        <KpiCard label="Active releases" value={k.active_releases} />
        <KpiCard
          label="Completed projects"
          value={k.completed_projects}
          tone="good"
        />
        <KpiCard
          label="Efficiency"
          value={percent(k.efficiency_percent)}
          tone={toneFor(k.efficiency_percent, { good: 95, warn: 85 })}
        />
        <KpiCard
          label="Utilisation"
          value={percent(k.utilization_percent)}
          hint={`${data.capacity_vs_demand.people} people`}
        />
        <KpiCard
          label="On-time delivery"
          value={percent(k.on_time_percent)}
          tone={toneFor(k.on_time_percent, { good: 85, warn: 70 })}
        />
        <KpiCard
          label="Rework"
          value={percent(k.rework_percent)}
          tone={toneFor(k.rework_percent, { good: 5, warn: 10, higherIsBetter: false })}
        />
        <KpiCard
          label="Overdue releases"
          value={k.overdue_releases}
          tone={k.overdue_releases > 0 ? "bad" : "good"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Exceptions and wins" bodyClassName="" className="lg:col-span-1">
          <InsightList insights={data.insights} />
        </Card>

        <Card title="Monthly design output" className="lg:col-span-2">
          {data.monthly_output.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-500">
              Not enough completed work yet to plot a trend.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.monthly_output}>
                <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
                <XAxis dataKey="month" stroke={CHART_COLORS.axis} fontSize={11} />
                <YAxis stroke={CHART_COLORS.axis} fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 6 }}
                  formatter={(value: number, name: string) => [value, name]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar
                  dataKey="tasks_completed"
                  name="Tasks completed"
                  fill={CHART_COLORS.brand}
                  radius={[3, 3, 0, 0]}
                />
                <Bar
                  dataKey="releases_completed"
                  name="Releases completed"
                  fill={CHART_COLORS.green}
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Efficiency and on-time trend" className="lg:col-span-2">
          {data.monthly_output.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-500">No trend data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data.monthly_output}>
                <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
                <XAxis dataKey="month" stroke={CHART_COLORS.axis} fontSize={11} />
                <YAxis
                  stroke={CHART_COLORS.axis}
                  fontSize={11}
                  unit="%"
                  domain={[0, "auto"]}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 6 }}
                  formatter={(value: number) => `${value?.toFixed?.(1) ?? value}%`}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="efficiency_percent"
                  name="Efficiency"
                  stroke={CHART_COLORS.brand}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="on_time_percent"
                  name="On-time"
                  stroke={CHART_COLORS.green}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="rework_percent"
                  name="Rework"
                  stroke={CHART_COLORS.red}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Portfolio health">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={healthData} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} horizontal={false} />
              <XAxis type="number" stroke={CHART_COLORS.axis} fontSize={11} allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="health"
                stroke={CHART_COLORS.axis}
                fontSize={11}
                width={60}
              />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
              <Bar dataKey="count" name="Active projects" radius={[0, 3, 3, 0]}>
                {healthData.map((entry) => (
                  <Cell key={entry.health} fill={HEALTH_FILL[entry.health]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <dl className="mt-3 space-y-1.5 border-t border-ink-100 pt-3">
            <div className="flex justify-between text-xs">
              <dt className="text-ink-600">Capacity available</dt>
              <dd className="tabular text-ink-900">
                {hours(data.capacity_vs_demand.available_hours)}
              </dd>
            </div>
            <div className="flex justify-between text-xs">
              <dt className="text-ink-600">Demand allocated</dt>
              <dd className="tabular text-ink-900">
                {hours(data.capacity_vs_demand.allocated_hours)}
              </dd>
            </div>
            <div className="flex justify-between text-xs">
              <dt className="text-ink-600">Average cycle time</dt>
              <dd className="tabular text-ink-900">
                {durationHours(k.average_cycle_time_hours)}
              </dd>
            </div>
            <div className="flex justify-between text-xs">
              <dt className="text-ink-600">Review turnaround</dt>
              <dd className="tabular text-ink-900">
                {durationHours(k.average_review_turnaround_hours)}
              </dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card className="mt-4" title="Delayed projects" bodyClassName="">
        {data.delayed_projects.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-ink-500">
            No project is past its required completion date.
          </div>
        ) : (
          <div className="divide-y divide-ink-100">
            {data.delayed_projects.map((project) => (
              <div key={project.id} className="px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink-900">{project.name}</p>
                    <p className="font-mono text-2xs text-ink-400">
                      {project.code} · {project.customer ?? DASH}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-rag-red">
                      {project.delay_days} day{project.delay_days === 1 ? "" : "s"} late
                    </span>
                    <HealthPill health={project.health} />
                  </div>
                </div>
                <div className="mt-2 max-w-md">
                  <ProgressBar value={project.completion_percent} tone="red" />
                </div>
                <ul className="mt-1.5 space-y-0.5">
                  {project.reasons.slice(0, 3).map((reason, i) => (
                    <li key={i} className="text-2xs text-ink-600">
                      • {reason.message}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Team lead performance" bodyClassName="">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead className="border-b border-ink-200 bg-ink-50">
                <tr>
                  <th className="th">Lead</th>
                  <th className="th text-right">Releases</th>
                  <th className="th text-right">Late</th>
                  <th className="th text-right">Efficiency</th>
                  <th className="th text-right">On-time</th>
                  <th className="th text-right">First-pass</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {data.team_lead_performance.map((lead) => (
                  <tr key={lead.id} className="hover:bg-ink-50">
                    <td className="td font-medium">{lead.full_name}</td>
                    <td className="td text-right tabular">
                      {lead.releases_completed}/{lead.releases_assigned}
                    </td>
                    <td className="td text-right tabular">
                      {lead.releases_delayed > 0 ? (
                        <span className="font-medium text-rag-red">
                          {lead.releases_delayed}
                        </span>
                      ) : (
                        <span className="text-ink-400">0</span>
                      )}
                    </td>
                    <td className="td text-right tabular">
                      {percent(lead.team_efficiency_percent)}
                    </td>
                    <td className="td text-right tabular">
                      {percent(lead.team_on_time_percent)}
                    </td>
                    <td className="td text-right tabular">
                      {percent(lead.first_pass_approval_percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Designer performance" bodyClassName="">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead className="border-b border-ink-200 bg-ink-50">
                <tr>
                  <th className="th">Designer</th>
                  <th className="th text-right">Done</th>
                  <th className="th text-right">Efficiency</th>
                  <th className="th">Utilisation</th>
                  <th className="th text-right">Rework</th>
                  <th className="th text-right">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {[...data.designer_performance]
                  .sort(
                    (a, b) =>
                      (b.performance_score.score ?? -1) - (a.performance_score.score ?? -1),
                  )
                  .map((designer) => (
                    <tr key={designer.id} className="hover:bg-ink-50">
                      <td className="td font-medium">{designer.full_name}</td>
                      <td className="td text-right tabular">{designer.tasks_completed}</td>
                      <td className="td text-right tabular">
                        {percent(designer.efficiency_percent)}
                      </td>
                      <td className="td">
                        <UtilizationBadge
                          band={designer.utilization_band}
                          value={designer.utilization_percent}
                        />
                      </td>
                      <td className="td text-right tabular">
                        {percent(designer.rework_percent)}
                      </td>
                      <td className="td text-right font-semibold tabular">
                        {designer.performance_score.score === null
                          ? DASH
                          : Math.round(designer.performance_score.score)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Slowest reviews" bodyClassName="">
          {data.bottlenecks.slowest_reviews.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-ink-500">
              No completed reviews yet.
            </div>
          ) : (
            <ul className="divide-y divide-ink-100">
              {data.bottlenecks.slowest_reviews.map((review) => (
                <li
                  key={review.code}
                  className="flex items-center justify-between gap-2 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs text-ink-800">{review.task_code}</p>
                    <p className="text-2xs text-ink-500">{review.reviewer ?? DASH}</p>
                  </div>
                  <span className="shrink-0 text-xs tabular text-rag-amber">
                    {durationHours(review.turnaround_hours)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Blocked work" bodyClassName="">
          {data.bottlenecks.blocked_tasks.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-ink-500">
              Nothing is blocked.
            </div>
          ) : (
            <ul className="divide-y divide-ink-100">
              {data.bottlenecks.blocked_tasks.map((task) => (
                <li key={task.code} className="px-3 py-2">
                  <p className="truncate text-xs font-medium text-ink-900">{task.name}</p>
                  <p className="text-2xs text-ink-500">
                    {task.code} · {task.assigned_to ?? DASH}
                  </p>
                  {task.blocker_reason && (
                    <p className="mt-0.5 text-2xs text-rag-red">{task.blocker_reason}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
