/**
 * Design release list (spec section 8).
 */

import { Plus } from "lucide-react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";

import { ChipFilter, FilterBar, Pagination, SearchInput } from "@/components/ui/Filters";
import { Select } from "@/components/ui/form";
import {
  EmptyState,
  ErrorState,
  HealthPill,
  PageHeader,
  PriorityLabel,
  ProgressBar,
  SkeletonRows,
  Spinner,
  StatusBadge,
} from "@/components/ui/primitives";
import { P, useAuth } from "@/store/auth";
import { useAssignLead, useReleases, useUsers } from "@/hooks/queries";
import { DASH, hours, shortDate, variance } from "@/lib/format";
import { HEALTH_LEVELS, RELEASE_STATUSES } from "@/lib/vocab";
import type { ReleaseSummary } from "@/types/api";

export default function Releases() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const page = Number(params.get("page") ?? 1);
  const search = params.get("search") ?? "";
  const status = params.getAll("status");
  const health = params.getAll("health");
  const overdueOnly = params.get("overdue_only") === "true";

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

  const { data, isLoading, isError, error, refetch } = useReleases({
    page,
    page_size: 25,
    search,
    status,
    health,
    overdue_only: overdueOnly || undefined,
    sort: "-planned_end",
  });

  const can = useAuth((state) => state.can);

  const hasFilters =
    Boolean(search) || status.length > 0 || health.length > 0 || overdueOnly;

  return (
    <>
      <PageHeader
        title="Design Releases"
        subtitle={
          data
            ? `${data.total.toLocaleString()} release${data.total === 1 ? "" : "s"} visible to you`
            : undefined
        }
        actions={
          can(P.releaseCreate) && (
            <Link to="/projects" className="btn-primary">
              <Plus className="h-4 w-4" />
              Add a release
            </Link>
          )
        }
      />

      <FilterBar>
        <SearchInput
          value={search}
          onChange={(value) =>
            update((next) => {
              if (value) next.set("search", value);
              else next.delete("search");
              next.delete("page");
            })
          }
          placeholder="Release name or code"
          className="w-full sm:w-64"
        />
        <ChipFilter
          label="Status"
          options={RELEASE_STATUSES}
          selected={status}
          onChange={(v) => setList("status", v)}
        />
        <ChipFilter
          label="Health"
          options={HEALTH_LEVELS}
          selected={health}
          onChange={(v) => setList("health", v)}
        />
        <label className="flex items-center gap-1.5 text-xs text-ink-700">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) =>
              update((next) => {
                if (e.target.checked) next.set("overdue_only", "true");
                else next.delete("overdue_only");
                next.delete("page");
              })
            }
          />
          Overdue only
        </label>
      </FilterBar>

      <div className="card">
        {isLoading && <SkeletonRows rows={8} cols={7} />}

        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : undefined}
            onRetry={() => void refetch()}
          />
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            title={hasFilters ? "No releases match these filters" : "No releases yet"}
            description={
              hasFilters
                ? "Try clearing a filter."
                : "Releases are created from inside a project."
            }
          />
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[940px]">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">Release</th>
                    <th className="th">Project</th>
                    <th className="th">Team lead</th>
                    <th className="th">Status</th>
                    <th className="th">Priority</th>
                    <th className="th w-32">Progress</th>
                    <th className="th text-right">Est / Act</th>
                    <th className="th text-right">Variance</th>
                    <th className="th">Due</th>
                    <th className="th">Health</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {data.items.map((release) => (
                    <tr
                      key={release.id}
                      className="cursor-pointer hover:bg-ink-50"
                      onClick={() => navigate(`/releases/${release.id}`)}
                    >
                      <td className="td max-w-[18rem]">
                        <div className="truncate font-medium text-ink-900">
                          {release.name}
                        </div>
                        <div className="font-mono text-2xs text-ink-400">
                          {release.code} · {release.release_type}
                        </div>
                      </td>
                      <td className="td text-xs text-ink-600">
                        <div className="max-w-[12rem] truncate">
                          {release.project_name ?? DASH}
                        </div>
                        <div className="font-mono text-2xs text-ink-400">
                          {release.project_code}
                        </div>
                      </td>
                      <td className="td text-xs text-ink-600">
                        <LeadCell release={release} />
                      </td>
                      <td className="td">
                        <StatusBadge status={release.status} />
                      </td>
                      <td className="td">
                        <PriorityLabel priority={release.priority} />
                      </td>
                      <td className="td">
                        <ProgressBar
                          value={release.completion_percent}
                          tone={
                            release.health === "RED"
                              ? "red"
                              : release.health === "AMBER"
                                ? "amber"
                                : "neutral"
                          }
                        />
                      </td>
                      <td className="td text-right text-xs tabular text-ink-600">
                        {hours(release.estimated_hours)} / {hours(release.actual_hours)}
                      </td>
                      <td className="td text-right text-xs tabular">
                        {release.estimated_hours > 0 ? (
                          <span
                            className={
                              release.actual_hours > release.estimated_hours
                                ? "font-medium text-rag-amber"
                                : "text-ink-600"
                            }
                          >
                            {variance(release.actual_hours - release.estimated_hours)}
                          </span>
                        ) : (
                          <span className="text-ink-300">{DASH}</span>
                        )}
                      </td>
                      <td className="td text-xs">
                        <span
                          className={
                            release.delay_days > 0
                              ? "font-medium text-rag-red"
                              : "text-ink-600"
                          }
                        >
                          {shortDate(release.planned_end)}
                        </span>
                        {release.delay_days > 0 && (
                          <span className="ml-1 text-2xs text-rag-red">
                            +{release.delay_days}d
                          </span>
                        )}
                      </td>
                      <td className="td">
                        <HealthPill health={release.health} />
                      </td>
                    </tr>
                  ))}
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
      </div>
    </>
  );
}

/**
 * Assign a release's lead without leaving the list.
 *
 * The detail page has always been able to do this, one release at a time. With
 * 28 of 29 releases unled that is 28 page visits, and the work that unblocks --
 * a release lead is what gives its tasks a lead, and a task lead is who a
 * review is routed to -- is exactly the work nobody does when it costs that
 * much. The list already showed "Unassigned" in amber; it just could not act
 * on it.
 *
 * Falls back to plain text for anyone without the permission, rather than
 * offering a control the API would refuse.
 */
function LeadCell({ release }: { release: ReleaseSummary }) {
  const can = useAuth((state) => state.can);
  const { data: leads } = useUsers({ role: "Team Lead" });
  const assign = useAssignLead(release.id);

  const finished = release.status === "Completed" || release.status === "Cancelled";

  if (!can(P.releaseAssignLead) || finished) {
    return (
      <>
        {release.team_lead_name ?? <span className="text-rag-amber">Unassigned</span>}
      </>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <Select
        aria-label={`Team lead for ${release.code}`}
        className="py-1 text-xs font-normal"
        value={release.team_lead_id ?? ""}
        disabled={assign.isPending}
        placeholder="Unassigned"
        onChange={(event) => {
          // The row is a link to the release; choosing a lead is not navigation.
          event.stopPropagation();
          if (event.target.value) assign.mutate(event.target.value);
        }}
        options={(leads?.items ?? []).map((u) => ({ value: u.id, label: u.full_name }))}
      />
      {assign.isPending && <Spinner className="h-3 w-3 shrink-0" />}
      {assign.isError && <span className="text-2xs text-rag-red">not saved</span>}
    </div>
  );
}
