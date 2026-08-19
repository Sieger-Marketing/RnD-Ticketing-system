/**
 * Designer × date planned workload (spec section 23).
 *
 * Cell colour comes from the configured capacity bands, not from hard-coded
 * cut-offs, so retuning the thresholds in Settings changes what the heatmap
 * calls "overloaded".
 */

import clsx from "clsx";
import { format, parseISO } from "date-fns";

import { EmptyState, UtilizationBadge } from "@/components/ui/primitives";
import type { CapacitySummary, UtilizationBand } from "@/types/api";

function bandFor(
  utilization: number | null,
  thresholds: { underutilized: number; healthy: number; high_load: number },
): UtilizationBand {
  if (utilization === null) return "No Data";
  if (utilization < thresholds.underutilized) return "Underutilized";
  if (utilization < thresholds.healthy) return "Healthy";
  if (utilization <= thresholds.high_load) return "High Load";
  return "Overloaded";
}

const CELL_STYLE: Record<UtilizationBand, string> = {
  "No Data": "bg-ink-50 text-ink-300",
  Underutilized: "bg-cream-300 text-ink-700",
  Healthy: "bg-rag-greenBg text-rag-green",
  "High Load": "bg-rag-amberBg text-rag-amber",
  Overloaded: "bg-rag-redBg text-rag-red font-semibold",
};

export function CapacityHeatmap({
  rows,
  thresholds = { underutilized: 70, healthy: 90, high_load: 100 },
}: {
  rows: CapacitySummary[];
  thresholds?: { underutilized: number; healthy: number; high_load: number };
}) {
  if (rows.length === 0) {
    return <EmptyState title="No capacity data" />;
  }

  const days = rows[0]?.daily ?? [];

  return (
    <div className="table-scroll">
      <table className="w-full min-w-[720px] border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="th sticky left-0 z-10 bg-white">Designer</th>
            <th className="th text-right">Load</th>
            {days.map((day) => {
              const parsed = parseISO(day.date);
              const isWeekend = parsed.getDay() === 0 || parsed.getDay() === 6;
              return (
                <th
                  key={day.date}
                  className={clsx("th px-1 text-center", isWeekend && "text-ink-300")}
                  title={format(parsed, "EEEE d MMMM")}
                >
                  <div>{format(parsed, "EEEEE")}</div>
                  <div className="font-normal">{format(parsed, "d")}</div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.user_id}>
              <td className="sticky left-0 z-10 whitespace-nowrap border-t border-ink-100 bg-white px-3 py-1.5 text-xs font-medium text-ink-800">
                {row.full_name}
              </td>
              <td className="border-t border-ink-100 px-2 py-1.5 text-right">
                <UtilizationBadge
                  band={row.utilization_band}
                  value={row.utilization_percent}
                />
              </td>
              {row.daily.map((cell) => {
                const util =
                  cell.available > 0 ? (cell.allocated / cell.available) * 100 : null;
                const band = cell.available === 0 ? "No Data" : bandFor(util, thresholds);
                return (
                  <td
                    key={cell.date}
                    className="border-t border-ink-100 px-0.5 py-1.5"
                    title={`${format(parseISO(cell.date), "d MMM")}: ${cell.allocated.toFixed(
                      1,
                    )}h allocated of ${cell.available.toFixed(1)}h available`}
                  >
                    <div
                      className={clsx(
                        "mx-auto flex h-6 w-8 items-center justify-center rounded text-2xs",
                        CELL_STYLE[band],
                      )}
                    >
                      {cell.available === 0 ? "—" : cell.allocated.toFixed(0)}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap items-center gap-3 px-1 text-2xs text-ink-500">
        <span>Hours allocated per day.</span>
        {(
          ["Underutilized", "Healthy", "High Load", "Overloaded"] as UtilizationBand[]
        ).map((band) => (
          <span key={band} className="flex items-center gap-1">
            <span className={clsx("h-3 w-3 rounded", CELL_STYLE[band])} />
            {band}
          </span>
        ))}
      </div>
    </div>
  );
}
