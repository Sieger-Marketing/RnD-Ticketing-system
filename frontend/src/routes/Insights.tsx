/**
 * The same performance question, asked along different lines.
 *
 * A design manager asks it per product, because a Tower behaves nothing like a
 * Stacker. A director asks it per customer, because that is how the commercial
 * conversation is framed. A team lead asks it per team. The arithmetic is the
 * same in all three cases, so this is one table with a switch above it rather
 * than three screens that drift apart.
 *
 * Clicking a row drills into it, and the table keeps its shape: the projects
 * behind a product are described in exactly the columns the products were, so
 * the reader is not re-learning a layout at the moment they are trying to
 * follow a thread.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowLeft, ChevronRight, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ResponsiveTable } from "@/components/ui/ResponsiveTable";
import {
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  PageHeader,
  SkeletonRows,
  toneFor,
} from "@/components/ui/primitives";
import { useIsNarrow } from "@/hooks/useIsNarrow";
import { useBreakdown } from "@/hooks/queries";
import { download } from "@/lib/api";
import { DASH, hours, localDaysAgo, localToday, num, percent } from "@/lib/format";
import type { BreakdownRow, UUID } from "@/types/api";

const CHART = {
  brand: "#9b2423",
  green: "#3f6d44",
  amber: "#8a6212",
  grid: "#e2ddd4",
  axis: "#948b7c",
};

type Dimension = "product" | "customer" | "team";

const DIMENSIONS: { key: Dimension; label: string; blurb: string }[] = [
  { key: "product", label: "Product", blurb: "How each system behaves" },
  { key: "customer", label: "Customer", blurb: "Who the work is for" },
  { key: "team", label: "Team", blurb: "Who is carrying it" },
];

/** A drill-down step, so the reader can walk back out the way they came. */
interface Crumb {
  dimension: Dimension | "project";
  key: UUID;
  label: string;
}

/**
 * Efficiency is planned over actual, so 100 is on estimate and lower is slower.
 * Colouring it needs a band rather than "more is better": 250% is not a triumph,
 * it means the estimate was wrong.
 */
function efficiencyTone(value: number | null): "good" | "warn" | "bad" | "neutral" {
  if (value === null) return "neutral";
  if (value >= 90 && value <= 130) return "good";
  if (value >= 70) return "warn";
  return "bad";
}

export default function Insights() {
  const navigate = useNavigate();
  const narrow = useIsNarrow();

  const [dimension, setDimension] = useState<Dimension>("product");
  const [trail, setTrail] = useState<Crumb[]>([]);
  const [from, setFrom] = useState(localDaysAgo(90));
  const [to, setTo] = useState(localToday());
  const [exporting, setExporting] = useState(false);

  // Inside a drill-down the rows are the projects underneath, unless the
  // reader has switched to another lens -- "which teams worked on Tower" is a
  // question worth being able to ask.
  const parent = trail.at(-1) ?? null;
  const effectiveDimension: Dimension | "project" = parent ? "project" : dimension;

  const query = useBreakdown({
    dimension: effectiveDimension,
    date_from: from,
    date_to: to,
    within_dimension: parent?.dimension,
    within_key: parent?.key,
  });

  const rows = query.data?.rows ?? [];
  const totals = query.data?.totals;

  const chartData = useMemo(
    () =>
      rows
        .filter((r) => r.efficiency_percent !== null)
        .slice(0, 10)
        .map((r) => ({
          label: r.label.length > 18 ? `${r.label.slice(0, 17)}…` : r.label,
          efficiency: r.efficiency_percent,
          onTime: r.on_time_percent,
        })),
    [rows],
  );

  const exportReport = async () => {
    setExporting(true);
    try {
      await download("/api/reports/breakdown", {
        dimension: effectiveDimension,
        date_from: from,
        date_to: to,
        format: "xlsx",
      });
    } finally {
      setExporting(false);
    }
  };

  const openRow = (row: BreakdownRow) => {
    if (!row.key) return; // "Unassigned" has nothing to drill into
    if (effectiveDimension === "project") {
      navigate(`/projects/${row.key}`);
      return;
    }
    setTrail((t) => [
      ...t,
      { dimension: effectiveDimension, key: row.key as UUID, label: row.label },
    ]);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Insights"
        subtitle="Efficiency, delivery and rework, cut the way you need to look at it."
        actions={
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void exportReport()}
            disabled={exporting || rows.length === 0}
          >
            <Download className="h-4 w-4" />
            {exporting ? "Preparing" : "Export"}
          </button>
        }
      />

      {/* Lens and period */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div
          className="inline-flex rounded-lg border border-ink-200 bg-white p-0.5"
          role="tablist"
          aria-label="Cut the numbers by"
        >
          {DIMENSIONS.map((d) => (
            <button
              key={d.key}
              type="button"
              role="tab"
              aria-selected={dimension === d.key && !parent}
              title={d.blurb}
              className={
                dimension === d.key
                  ? "rounded-md bg-signal-600 px-3 py-1.5 text-sm font-medium text-white"
                  : "rounded-md px-3 py-1.5 text-sm text-ink-600 hover:bg-cream-100"
              }
              onClick={() => {
                setDimension(d.key);
                setTrail([]);
              }}
            >
              {d.label}
            </button>
          ))}
        </div>

        <div className="flex items-end gap-2">
          <label className="text-2xs font-medium uppercase tracking-wide text-ink-500">
            From
            <input
              type="date"
              className="input mt-0.5 py-1.5 text-sm"
              value={from}
              max={to}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="text-2xs font-medium uppercase tracking-wide text-ink-500">
            To
            <input
              type="date"
              className="input mt-0.5 py-1.5 text-sm"
              value={to}
              min={from}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
        </div>
      </div>

      {/* Where the reader is */}
      {trail.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-sm">
          <button
            type="button"
            className="btn-ghost px-2 py-1 text-xs"
            onClick={() => setTrail([])}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            All {dimension}s
          </button>
          {trail.map((crumb, index) => (
            <span key={crumb.key} className="flex items-center gap-1">
              <ChevronRight className="h-3.5 w-3.5 text-ink-400" />
              <button
                type="button"
                className="rounded px-1.5 py-0.5 text-xs font-medium text-ink-900 hover:bg-cream-100"
                onClick={() => setTrail((t) => t.slice(0, index + 1))}
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </div>
      )}

      {query.isError && <ErrorState onRetry={() => void query.refetch()} />}
      {query.isLoading && <SkeletonRows rows={6} cols={5} />}

      {query.data && (
        <>
          {/* The higher-level view: one honest set of department figures,
              recomputed from the underlying totals rather than averaged from
              the rows -- an average of percentages weights a product with four
              hours the same as one with four hundred. */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard
              label="Efficiency"
              value={percent(totals?.efficiency_percent, 1)}
              tone={efficiencyTone(totals?.efficiency_percent ?? null)}
              hint="Planned ÷ actual hours"
            />
            <KpiCard
              label="On time"
              value={percent(totals?.on_time_percent, 1)}
              tone={toneFor(totals?.on_time_percent ?? null, { good: 85, warn: 70 })}
              hint="Finished by the planned date"
            />
            <KpiCard
              label="Rework"
              value={percent(totals?.rework_percent, 1)}
              tone={toneFor(totals?.rework_percent ?? null, {
                good: 5,
                warn: 12,
                higherIsBetter: false,
              })}
              hint="Share of hours spent redoing"
            />
            <KpiCard
              label="First pass"
              value={percent(totals?.first_pass_approval_percent, 1)}
              tone={toneFor(totals?.first_pass_approval_percent ?? null, {
                good: 80,
                warn: 60,
              })}
              hint="Approved without a revision"
            />
            <KpiCard
              label="Tasks done"
              value={num(totals?.tasks_completed)}
              hint={`${hours(totals?.actual_hours)} logged`}
            />
          </div>

          {chartData.length > 1 && (
            <Card title={`Efficiency by ${query.data.row_label.toLowerCase()}`}>
              <ResponsiveContainer width="100%" height={narrow ? 220 : 260}>
                <BarChart data={chartData} margin={{ left: -18, right: 8 }}>
                  <CartesianGrid stroke={CHART.grid} vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke={CHART.axis}
                    fontSize={11}
                    interval={0}
                    angle={narrow ? -35 : 0}
                    textAnchor={narrow ? "end" : "middle"}
                    height={narrow ? 70 : 30}
                  />
                  <YAxis stroke={CHART.axis} fontSize={11} />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, "Efficiency"]}
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Bar dataKey="efficiency" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry) => (
                      <Cell
                        key={entry.label}
                        fill={
                          entry.efficiency !== null &&
                          entry.efficiency >= 90 &&
                          entry.efficiency <= 130
                            ? CHART.green
                            : entry.efficiency !== null && entry.efficiency >= 70
                              ? CHART.amber
                              : CHART.brand
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-1 text-2xs text-ink-500">
                100% means the work took exactly what was estimated. Well above
                it is not a triumph — it means the estimate was wrong.
              </p>
            </Card>
          )}

          {rows.length === 0 ? (
            <Card>
              <EmptyState
                title="Nothing in this period"
                description="No work was completed between these dates. Widen the range."
              />
            </Card>
          ) : (
            <Card bodyClassName="">
              <ResponsiveTable
                rows={rows}
                rowKey={(row) => row.key ?? "unassigned"}
                minWidth="64rem"
                onRowClick={(row) => openRow(row)}
                columns={[
                  {
                    key: "label",
                    mobile: "primary",
                    header: query.data.row_label,
                    cell: (row) => (
                      <span className="flex items-center gap-1.5">
                        <span className="font-medium text-ink-900">{row.label}</span>
                        {row.key && (
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-400" />
                        )}
                      </span>
                    ),
                  },
                  {
                    key: "projects",
                    mobile: "meta",
                    align: "right",
                    header: "Projects",
                    cell: (row) => <span className="tabular-nums">{row.projects}</span>,
                  },
                  {
                    key: "done",
                    align: "right",
                    header: "Tasks done",
                    cell: (row) => (
                      <span className="tabular-nums">{row.tasks_completed}</span>
                    ),
                  },
                  {
                    key: "hours",
                    align: "right",
                    header: "Planned / actual",
                    cell: (row) => (
                      <span className="tabular-nums text-ink-600">
                        {hours(row.planned_hours)} / {hours(row.actual_hours)}
                      </span>
                    ),
                  },
                  {
                    key: "efficiency",
                    align: "right",
                    header: "Efficiency",
                    cell: (row) => {
                      const tone = efficiencyTone(row.efficiency_percent);
                      return (
                        <span
                          className={
                            tone === "good"
                              ? "font-medium tabular-nums text-rag-green"
                              : tone === "warn"
                                ? "font-medium tabular-nums text-rag-amber"
                                : tone === "bad"
                                  ? "font-medium tabular-nums text-rag-red"
                                  : "tabular-nums text-ink-400"
                          }
                        >
                          {percent(row.efficiency_percent, 1)}
                        </span>
                      );
                    },
                  },
                  {
                    key: "on_time",
                    align: "right",
                    header: "On time",
                    cell: (row) => (
                      <span className="tabular-nums">
                        {percent(row.on_time_percent, 1)}
                      </span>
                    ),
                  },
                  {
                    key: "rework",
                    align: "right",
                    header: "Rework",
                    cell: (row) => (
                      <span className="tabular-nums">
                        {percent(row.rework_percent, 1)}
                      </span>
                    ),
                  },
                  {
                    key: "first_pass",
                    align: "right",
                    header: "First pass",
                    cell: (row) => (
                      <span className="tabular-nums">
                        {percent(row.first_pass_approval_percent, 1)}
                      </span>
                    ),
                  },
                  {
                    key: "attention",
                    align: "right",
                    header: "Needs attention",
                    cell: (row) => {
                      const red = row.health.RED;
                      const overdue = row.tasks_overdue;
                      if (!red && !overdue) {
                        return <span className="text-ink-400">{DASH}</span>;
                      }
                      return (
                        <span className="flex items-center justify-end gap-2 text-xs">
                          {red > 0 && (
                            <span className="rounded-full bg-rag-redBg px-2 py-0.5 font-medium text-rag-red">
                              {red} red
                            </span>
                          )}
                          {overdue > 0 && (
                            <span className="rounded-full bg-rag-amberBg px-2 py-0.5 font-medium text-rag-amber">
                              {overdue} overdue
                            </span>
                          )}
                        </span>
                      );
                    },
                  },
                ]}
              />
            </Card>
          )}

          <p className="text-2xs text-ink-500">
            Hours and percentages cover work completed between the selected
            dates. “Needs attention” is a snapshot of right now. A dash means
            there was not enough data to compute the figure — it is not a zero.
            {effectiveDimension !== "project" &&
              " Select a row to see the projects behind it."}
          </p>
        </>
      )}
    </div>
  );
}
