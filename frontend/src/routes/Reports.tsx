/**
 * Generate a report and take it away.
 *
 * The list is built from the server's own catalogue rather than hard-coded
 * here, so adding a report on the backend makes it appear on this screen
 * instead of quietly existing where nobody can reach it — which is exactly
 * what had happened to all of them.
 *
 * Each report is previewed on screen before it is exported. Downloading a
 * spreadsheet to find out whether it contains what you wanted is a slow way to
 * ask a question.
 */

import { Download, FileSpreadsheet, FileText, Table2 } from "lucide-react";
import { useState } from "react";

import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import { useReportCatalogue } from "@/hooks/queries";
import { download, get } from "@/lib/api";
import { DASH, localToday } from "@/lib/format";
import type { ReportDefinition } from "@/types/api";

interface RenderedReport {
  key: string;
  title: string;
  period_label: string;
  generated_at: string;
  generated_by: string | null;
  summary: { label: string; value: unknown }[];
  sections: {
    title: string;
    columns: string[];
    rows: unknown[][];
    note: string | null;
  }[];
}

const FORMAT_ICONS: Record<string, typeof FileText> = {
  csv: Table2,
  xlsx: FileSpreadsheet,
  pdf: FileText,
};

/** A value the server could not compute comes back as null; show the dash. */
function cell(value: unknown): string {
  if (value === null || value === undefined || value === "") return DASH;
  return String(value);
}

export default function Reports() {
  const catalogue = useReportCatalogue();

  const [active, setActive] = useState<ReportDefinition | null>(null);
  const [parameter, setParameter] = useState<string>(localToday());
  const [preview, setPreview] = useState<RenderedReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = (report: ReportDefinition) => {
    setActive(report);
    setPreview(null);
    setError(null);
    setParameter(report.parameter_options?.[0] ?? localToday());
  };

  const generate = async (report: ReportDefinition, value: string) => {
    setBusy(true);
    setError(null);
    try {
      const data = await get<RenderedReport>(`/api/reports/${report.key}`, {
        [report.parameter]: value,
        format: "json",
      });
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate it.");
    } finally {
      setBusy(false);
    }
  };

  const exportAs = async (format: string) => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await download(`/api/reports/${active.key}`, {
        [active.parameter]: parameter,
        format,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export it.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reports"
        subtitle="Generate a report, look at it, then take it with you."
      />

      {catalogue.isError && <ErrorState onRetry={() => void catalogue.refetch()} />}
      {catalogue.isLoading && <SkeletonRows rows={3} cols={2} />}

      {catalogue.data && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {catalogue.data.reports.map((report) => (
            <button
              key={report.key}
              type="button"
              onClick={() => open(report)}
              className={
                active?.key === report.key
                  ? "card p-4 text-left ring-2 ring-signal-600"
                  : "card p-4 text-left hover:border-signal-300"
              }
            >
              <p className="font-display text-sm font-semibold text-ink-900">
                {report.title}
              </p>
              <p className="mt-1 text-xs text-ink-500">{report.description}</p>
            </button>
          ))}
        </div>
      )}

      {active && (
        <Card
          title={active.title}
          action={
            <div className="flex flex-wrap items-center gap-2">
              {(catalogue.data?.formats ?? [])
                .filter((f) => f !== "json")
                .map((format) => {
                  const Icon = FORMAT_ICONS[format] ?? Download;
                  return (
                    <button
                      key={format}
                      type="button"
                      className="btn-secondary"
                      disabled={busy}
                      onClick={() => void exportAs(format)}
                    >
                      <Icon className="h-4 w-4" />
                      {format.toUpperCase()}
                    </button>
                  );
                })}
            </div>
          }
        >
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-2xs font-medium uppercase tracking-wide text-ink-500">
              {active.parameter_label}
              {active.parameter_options ? (
                <select
                  className="input mt-0.5 py-1.5 text-sm"
                  value={parameter}
                  onChange={(event) => setParameter(event.target.value)}
                >
                  {active.parameter_options.map((option) => (
                    <option key={option} value={option}>
                      {option.charAt(0).toUpperCase() + option.slice(1)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="date"
                  className="input mt-0.5 py-1.5 text-sm"
                  value={parameter}
                  onChange={(event) => setParameter(event.target.value)}
                />
              )}
            </label>

            <button
              type="button"
              className="btn-primary"
              disabled={busy}
              onClick={() => void generate(active, parameter)}
            >
              {busy && <Spinner className="h-4 w-4" />}
              Generate
            </button>
          </div>

          {error && (
            <p className="mt-3 rounded-md bg-rag-redBg px-3 py-2 text-xs text-rag-red">
              {error}
            </p>
          )}

          {preview && (
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-xs text-ink-500">
                  {preview.period_label}
                  {preview.generated_by ? ` · ${preview.generated_by}` : ""}
                </p>
                {preview.summary.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
                    {preview.summary.map((item) => (
                      <div key={item.label}>
                        <p className="text-2xs uppercase tracking-wide text-ink-500">
                          {item.label}
                        </p>
                        <p className="font-display text-base font-semibold tabular-nums text-ink-900">
                          {cell(item.value)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {preview.sections.map((section) => (
                <div key={section.title}>
                  <p className="mb-1.5 font-display text-sm font-semibold text-ink-900">
                    {section.title}
                  </p>
                  {section.rows.length === 0 ? (
                    <p className="text-xs text-ink-500">Nothing to report here.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[40rem] text-sm">
                        <thead>
                          <tr>
                            {section.columns.map((column) => (
                              <th
                                key={column}
                                className="border-b border-ink-200 px-2 py-1.5 text-left text-2xs font-medium uppercase tracking-wide text-ink-500"
                              >
                                {column}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {section.rows.map((row, index) => (
                            <tr key={index} className="hover:bg-cream-50">
                              {row.map((value, column) => (
                                <td
                                  key={column}
                                  className="border-b border-ink-100 px-2 py-1.5 tabular-nums text-ink-700"
                                >
                                  {cell(value)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {section.note && (
                    <p className="mt-1.5 text-2xs text-ink-500">{section.note}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {!preview && !busy && (
            <EmptyState
              title="Nothing generated yet"
              description="Choose the period and press Generate to see it before exporting."
            />
          )}
        </Card>
      )}
    </div>
  );
}
