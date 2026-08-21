/**
 * Task list (spec section 10).
 */

import { LayoutGrid, List, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { TaskCreateModal } from "@/components/TaskCreateModal";
import { TaskTable } from "@/components/TaskTable";
import { ChipFilter, FilterBar, Pagination, SearchInput } from "@/components/ui/Filters";
import {
  ErrorState,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { useTasks } from "@/hooks/queries";
import { P, useAuth } from "@/store/auth";
import { PRIORITIES, TASK_STATUSES } from "@/lib/vocab";

export default function Tasks() {
  const navigate = useNavigate();
  const can = useAuth((state) => state.can);
  const [adding, setAdding] = useState(false);
  const [params, setParams] = useSearchParams();

  const page = Number(params.get("page") ?? 1);
  const search = params.get("search") ?? "";
  const status = params.getAll("status");
  const priority = params.getAll("priority");
  const overdueOnly = params.get("overdue_only") === "true";
  const openOnly = params.get("open_only") === "true";

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

  const toggle = (key: string, on: boolean) =>
    update((next) => {
      if (on) next.set(key, "true");
      else next.delete(key);
      next.delete("page");
    });

  const { data, isLoading, isError, error, refetch } = useTasks({
    page,
    page_size: 50,
    search,
    status,
    priority,
    overdue_only: overdueOnly || undefined,
    open_only: openOnly || undefined,
    sort: "planned_end",
  });

  return (
    <>
      <PageHeader
        title="Tasks"
        subtitle={
          data ? `${data.total.toLocaleString()} task${data.total === 1 ? "" : "s"}` : undefined
        }
        actions={
          <>
            {can(P.taskCreate) && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => setAdding(true)}
              >
                <Plus className="h-4 w-4" />
                New task
              </button>
            )}
          <div className="flex items-center gap-1 rounded-md border border-ink-300 p-0.5">
            <span className="btn px-2 py-1 bg-ink-900 text-white">
              <List className="h-3.5 w-3.5" />
              List
            </span>
            <Link to="/kanban" className="btn-ghost px-2 py-1">
              <LayoutGrid className="h-3.5 w-3.5" />
              Board
            </Link>
            </div>
          </>
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
          placeholder="Task name or code"
          className="w-full sm:w-60"
        />
        <ChipFilter
          label="Status"
          options={TASK_STATUSES}
          selected={status}
          onChange={(v) => setList("status", v)}
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
            checked={openOnly}
            onChange={(e) => toggle("open_only", e.target.checked)}
          />
          Open only
        </label>
        <label className="flex items-center gap-1.5 text-xs text-ink-700">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => toggle("overdue_only", e.target.checked)}
          />
          Overdue only
        </label>
      </FilterBar>

      <div className="card">
        {isLoading && <SkeletonRows rows={10} cols={8} />}

        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : undefined}
            onRetry={() => void refetch()}
          />
        )}

        {data && (
          <>
            <TaskTable
              tasks={data.items}
              columns={[
                "code",
                "name",
                "project",
                "assignee",
                "status",
                "priority",
                "due",
                "hours",
                "progress",
              ]}
              onSelect={(task) => navigate(`/tasks/${task.id}`)}
              emptyTitle="No tasks match these filters"
              emptyDescription="Try clearing a filter."
            />
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

      {adding && (
        <TaskCreateModal
          onClose={() => setAdding(false)}
          onCreated={(task) => {
            setAdding(false);
            navigate(`/tasks/${task.id}`);
          }}
        />
      )}
    </>
  );
}
