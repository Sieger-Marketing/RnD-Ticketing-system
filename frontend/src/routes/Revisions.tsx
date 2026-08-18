/**
 * Revision and rework tracking (spec section 16).
 *
 * The column that matters is accountability. Separating rework the team could
 * have avoided from rework caused by a customer change is the whole point of
 * recording revisions, and it is what stops a designer being judged for a
 * scope change they did not cause.
 */

import { RotateCcw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ChipFilter, FilterBar, Pagination } from "@/components/ui/Filters";
import {
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  PageHeader,
  SkeletonRows,
  Spinner,
  StatusBadge,
} from "@/components/ui/primitives";
import { useResolveRevision, useRevisions, useVocabularies } from "@/hooks/queries";
import { DASH, hours, relative, shortDate } from "@/lib/format";
import { P, useAuth } from "@/store/auth";

const ACCOUNTABILITY = ["Controllable", "External"];
const REVISION_STATUSES = ["Open", "In Progress", "Resolved", "Cancelled"];

export default function Revisions() {
  const navigate = useNavigate();
  const can = useAuth((s) => s.can);
  const [params, setParams] = useSearchParams();

  const page = Number(params.get("page") ?? 1);
  const category = params.getAll("category");
  const status = params.getAll("status");
  const accountability = params.get("accountability") ?? "";
  const openOnly = params.get("open_only") === "true";

  const { data: vocab } = useVocabularies();
  const resolve = useResolveRevision();

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    setParams(next, { replace: true });
  };

  const setList = (key: string, values: string[]) =>
    update((next) => {
      next.delete(key);
      values.forEach((v) => next.append(key, v));
      next.delete("page");
    });

  const { data, isLoading, isError, error, refetch } = useRevisions({
    page,
    page_size: 25,
    category,
    status,
    accountability: accountability || undefined,
    open_only: openOnly || undefined,
  });

  // Counted from the page in view, and labelled as such rather than presented
  // as a department total the backend never claimed.
  const shown = data?.items ?? [];
  const controllable = shown.filter((r) => r.accountability === "Controllable").length;
  const external = shown.filter((r) => r.accountability === "External").length;
  const reworkHours = shown.reduce((sum, r) => sum + (r.additional_hours || 0), 0);

  return (
    <>
      <PageHeader
        title="Revisions"
        subtitle="Every piece of rework, and whose cause it was."
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Revisions listed"
          value={data?.total ?? 0}
          hint={`${shown.length} on this page`}
        />
        <KpiCard
          label="Controllable"
          value={controllable}
          tone={controllable > 0 ? "warn" : "good"}
          hint="On this page — avoidable rework"
          icon={<ShieldAlert className="h-4 w-4" />}
        />
        <KpiCard
          label="External"
          value={external}
          hint="On this page — customer or upstream change"
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <KpiCard
          label="Rework hours"
          value={hours(reworkHours)}
          hint="Recorded on resolved revisions"
        />
      </div>

      <FilterBar>
        <ChipFilter
          label="Status"
          options={REVISION_STATUSES}
          selected={status}
          onChange={(v) => setList("status", v)}
        />
        <ChipFilter
          label="Category"
          options={(vocab?.revision_categories ?? []).map((c) => c.value)}
          selected={category}
          onChange={(v) => setList("category", v)}
        />
        <div className="flex items-center gap-1">
          <span className="mr-1 text-2xs font-medium uppercase tracking-wide text-ink-500">
            Accountability
          </span>
          {ACCOUNTABILITY.map((value) => (
            <button
              key={value}
              type="button"
              className={`rounded-full border px-2 py-0.5 text-2xs transition-colors ${
                accountability === value
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-ink-300 bg-white text-ink-600 hover:bg-ink-100"
              }`}
              onClick={() =>
                update((next) => {
                  if (accountability === value) next.delete("accountability");
                  else next.set("accountability", value);
                  next.delete("page");
                })
              }
            >
              {value}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-ink-700">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) =>
              update((next) => {
                if (e.target.checked) next.set("open_only", "true");
                else next.delete("open_only");
                next.delete("page");
              })
            }
          />
          Open only
        </label>
      </FilterBar>

      <Card bodyClassName="">
        {isLoading && <SkeletonRows rows={8} cols={7} />}

        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : undefined}
            onRetry={() => void refetch()}
          />
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            title="No revisions"
            description="Rework raised at review, or by a lead directly, appears here."
            icon={<RotateCcw className="h-7 w-7" />}
          />
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">Task</th>
                    <th className="th">#</th>
                    <th className="th">Category</th>
                    <th className="th">Accountability</th>
                    <th className="th">Reason</th>
                    <th className="th">Assigned to</th>
                    <th className="th">Raised</th>
                    <th className="th text-right">Rework</th>
                    <th className="th">Status</th>
                    {can(P.revisionResolve) && <th className="th" />}
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {data.items.map((revision) => {
                    const isOpen =
                      revision.status === "Open" || revision.status === "In Progress";
                    return (
                      <tr key={revision.id} className="hover:bg-ink-50">
                        <td
                          className="td max-w-[18rem] cursor-pointer"
                          onClick={() => navigate(`/tasks/${revision.task_id}`)}
                        >
                          <div className="truncate font-medium text-ink-900">
                            {revision.task_name}
                          </div>
                          <div className="font-mono text-2xs text-ink-400">
                            {revision.task_code}
                          </div>
                        </td>
                        <td className="td text-xs tabular">{revision.revision_number}</td>
                        <td className="td text-xs text-ink-700">{revision.category}</td>
                        <td className="td">
                          <span
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs font-medium ${
                              revision.accountability === "Controllable"
                                ? "bg-rag-amberBg text-rag-amber"
                                : "bg-blue-50 text-blue-700"
                            }`}
                          >
                            {revision.accountability}
                          </span>
                        </td>
                        <td className="td max-w-[16rem]">
                          <div className="truncate text-xs text-ink-700" title={revision.reason}>
                            {revision.reason}
                          </div>
                          {revision.root_cause && (
                            <div
                              className="truncate text-2xs text-ink-400"
                              title={revision.root_cause}
                            >
                              {revision.root_cause}
                            </div>
                          )}
                        </td>
                        <td className="td text-xs text-ink-600">
                          {revision.assigned_to_name ?? DASH}
                        </td>
                        <td className="td text-xs text-ink-500">
                          {relative(revision.raised_date)}
                        </td>
                        <td className="td text-right text-xs tabular">
                          {/* additional_hours is only computed on resolve, so an
                              open revision reads 0.0 rather than "none logged". */}
                          {isOpen ? (
                            <span className="text-ink-400" title="Measured when resolved">
                              {DASH}
                            </span>
                          ) : (
                            hours(revision.additional_hours)
                          )}
                        </td>
                        <td className="td">
                          <StatusBadge status={revision.status} />
                          {revision.resolved_date && (
                            <div className="mt-0.5 text-2xs text-ink-400">
                              {shortDate(revision.resolved_date)}
                            </div>
                          )}
                        </td>
                        {can(P.revisionResolve) && (
                          <td className="td">
                            {isOpen && (
                              <button
                                type="button"
                                className="btn-secondary px-2 py-1"
                                onClick={() => resolve.mutate(revision.id)}
                                disabled={resolve.isPending}
                                title="Closes the revision and totals its rework hours"
                              >
                                {resolve.isPending ? <Spinner /> : "Resolve"}
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={data.page}
              pages={data.pages}
              total={data.total}
              pageSize={data.page_size}
              onPage={(next) => update((p) => p.set("page", String(next)))}
            />
          </>
        )}
      </Card>

      <p className="mt-3 text-2xs text-ink-500">
        Resolving a revision closes it and totals the rework logged against it. It
        does not move the task on by itself — the designer restarts the task when
        the rework begins.
      </p>
    </>
  );
}
