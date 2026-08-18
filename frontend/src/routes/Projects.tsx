/**
 * Project list (spec section 7).
 *
 * Filters, search, sort and paging are all server-side, so the browser never
 * holds the whole project table.
 */

import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ProjectCreateModal } from "@/components/ProjectCreateModal";
import { ChipFilter, FilterBar, Pagination, SearchInput } from "@/components/ui/Filters";
import {
  EmptyState,
  ErrorState,
  HealthPill,
  PageHeader,
  PriorityLabel,
  ProgressBar,
  SkeletonRows,
  StatusBadge,
} from "@/components/ui/primitives";
import { useProjects } from "@/hooks/queries";
import { DASH, hours, shortDate, variance } from "@/lib/format";
import { HEALTH_LEVELS, PRIORITIES, PROJECT_STATUSES } from "@/lib/vocab";
import { P, useAuth } from "@/store/auth";

export default function Projects() {
  const navigate = useNavigate();
  const can = useAuth((s) => s.can);
  const [creating, setCreating] = useState(false);

  // Filters live in the URL so a filtered list can be shared or bookmarked.
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1);
  const search = params.get("search") ?? "";
  const status = params.getAll("status");
  const health = params.getAll("health");
  const priority = params.getAll("priority");
  const overdueOnly = params.get("overdue_only") === "true";
  const sort = params.get("sort") ?? "-created_at";

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    // Any filter change invalidates the current page number.
    if (!next.get("page")) next.delete("page");
    setParams(next, { replace: true });
  };

  const setList = (key: string, values: string[]) =>
    update((next) => {
      next.delete(key);
      values.forEach((v) => next.append(key, v));
      next.delete("page");
    });

  const { data, isLoading, isError, error, refetch } = useProjects({
    page,
    page_size: 25,
    search,
    status,
    health,
    priority,
    overdue_only: overdueOnly || undefined,
    sort,
  });

  const hasFilters =
    Boolean(search) ||
    status.length > 0 ||
    health.length > 0 ||
    priority.length > 0 ||
    overdueOnly;

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={
          data ? `${data.total.toLocaleString()} project${data.total === 1 ? "" : "s"}` : undefined
        }
        actions={
          can(P.projectCreate) && (
            <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              New project
            </button>
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
          placeholder="Name, code, sales or work order"
          className="w-full sm:w-72"
        />
        <ChipFilter
          label="Status"
          options={PROJECT_STATUSES}
          selected={status}
          onChange={(v) => setList("status", v)}
        />
        <ChipFilter
          label="Health"
          options={HEALTH_LEVELS}
          selected={health}
          onChange={(v) => setList("health", v)}
        />
        <ChipFilter
          label="Priority"
          options={PRIORITIES}
          selected={priority}
          onChange={(v) => setList("priority", v)}
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
            title={hasFilters ? "No projects match these filters" : "No projects yet"}
            description={
              hasFilters
                ? "Try clearing a filter."
                : "Create the first project to start planning design releases."
            }
            action={
              hasFilters ? (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setParams(new URLSearchParams(), { replace: true })}
                >
                  Clear filters
                </button>
              ) : can(P.projectCreate) ? (
                <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
                  New project
                </button>
              ) : undefined
            }
          />
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">Project</th>
                    <th className="th">Customer</th>
                    <th className="th">Product</th>
                    <th className="th">Status</th>
                    <th className="th">Priority</th>
                    <th className="th w-36">Completion</th>
                    <th className="th text-right">Planned / Actual</th>
                    <th className="th text-right">Variance</th>
                    <th className="th">Due</th>
                    <th className="th">Health</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {data.items.map((project) => (
                    <tr
                      key={project.id}
                      className="cursor-pointer hover:bg-ink-50"
                      onClick={() => navigate(`/projects/${project.id}`)}
                    >
                      <td className="td max-w-[20rem]">
                        <div className="truncate font-medium text-ink-900" title={project.name}>
                          {project.name}
                        </div>
                        <div className="font-mono text-2xs text-ink-400">
                          {project.code}
                          {project.release_count > 0 && (
                            <span className="ml-2 font-sans">
                              {project.release_count} release
                              {project.release_count === 1 ? "" : "s"} ·{" "}
                              {project.task_count} task{project.task_count === 1 ? "" : "s"}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="td text-xs text-ink-600">
                        {project.customer_name ?? DASH}
                      </td>
                      <td className="td text-xs text-ink-600">
                        {project.product_name ?? DASH}
                      </td>
                      <td className="td">
                        <StatusBadge status={project.status} />
                      </td>
                      <td className="td">
                        <PriorityLabel priority={project.priority} />
                      </td>
                      <td className="td">
                        <ProgressBar
                          value={project.completion_percent}
                          tone={
                            project.health === "RED"
                              ? "red"
                              : project.health === "AMBER"
                                ? "amber"
                                : "brand"
                          }
                        />
                      </td>
                      <td className="td text-right text-xs tabular text-ink-600">
                        {hours(project.planned_hours)} / {hours(project.actual_hours)}
                      </td>
                      <td className="td text-right text-xs tabular">
                        {project.planned_hours > 0 ? (
                          <span
                            className={
                              project.actual_hours > project.planned_hours
                                ? "font-medium text-rag-amber"
                                : "text-ink-600"
                            }
                          >
                            {variance(project.actual_hours - project.planned_hours)}
                          </span>
                        ) : (
                          <span className="text-ink-300">{DASH}</span>
                        )}
                      </td>
                      <td className="td text-xs">
                        <span
                          className={
                            project.delay_days > 0 ? "font-medium text-rag-red" : "text-ink-600"
                          }
                        >
                          {shortDate(project.required_completion_date)}
                        </span>
                        {project.delay_days > 0 && (
                          <span className="ml-1 text-2xs text-rag-red">
                            +{project.delay_days}d
                          </span>
                        )}
                      </td>
                      <td className="td">
                        <HealthPill health={project.health} />
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
              onPage={(next) =>
                update((params) => params.set("page", String(next)))
              }
            />
          </>
        )}
      </div>

      {/* Mounted only while open. Left mounted, its lookups (customers,
          products, design managers) fire on every visit to this list, and the
          users lookup 403s for anyone without user.view -- a request that can
          never succeed, for a dialog they cannot open. */}
      {creating && (
        <ProjectCreateModal
          open
          onClose={() => setCreating(false)}
          onCreated={(project) => {
            setCreating(false);
            navigate(`/projects/${project.id}`);
          }}
        />
      )}
    </>
  );
}
