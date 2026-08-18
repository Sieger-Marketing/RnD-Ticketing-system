/**
 * The task assignment screen from spec section 13.
 *
 * The point is that a Team Lead should not have to guess who is free. Each
 * candidate carries their current load, remaining headroom, skill match and
 * next deadline, so "who can take this" is answerable without leaving the
 * dialog. Sorting defaults to skill match then headroom, which is the order a
 * lead actually reasons in.
 */

import clsx from "clsx";
import { AlertTriangle, Check, Search } from "lucide-react";
import { useMemo, useState } from "react";

import {
  EmptyState,
  LoadingBlock,
  UtilizationBadge,
} from "@/components/ui/primitives";
import { useAssignmentBoard } from "@/hooks/queries";
import { DASH, hours, shortDate } from "@/lib/format";
import type { CapacitySummary } from "@/types/api";

type SortKey = "recommended" | "headroom" | "utilization" | "name";

export function AssigneePicker({
  taskId,
  requiredSkillId,
  selectedId,
  onSelect,
}: {
  /** Scores candidates against this task's skill and dates when given. */
  taskId?: string;
  requiredSkillId?: string | null;
  selectedId: string | null;
  onSelect: (userId: string | null) => void;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("recommended");

  const { data, isLoading, isError } = useAssignmentBoard({
    task_id: taskId,
    required_skill_id: requiredSkillId ?? undefined,
  });

  const candidates = useMemo(() => {
    const rows = [...(data ?? [])];
    const term = search.trim().toLowerCase();
    const filtered = term
      ? rows.filter((r) => r.full_name.toLowerCase().includes(term))
      : rows;

    const byName = (a: CapacitySummary, b: CapacitySummary) =>
      a.full_name.localeCompare(b.full_name);

    switch (sort) {
      case "headroom":
        return filtered.sort(
          (a, b) => (b.headroom_hours ?? 0) - (a.headroom_hours ?? 0) || byName(a, b),
        );
      case "utilization":
        return filtered.sort(
          (a, b) =>
            (a.utilization_percent ?? 0) - (b.utilization_percent ?? 0) || byName(a, b),
        );
      case "name":
        return filtered.sort(byName);
      default:
        // Skill first, then the deepest skill level, then who has room.
        return filtered.sort(
          (a, b) =>
            Number(b.has_required_skill ?? false) - Number(a.has_required_skill ?? false) ||
            (b.skill_rank ?? 0) - (a.skill_rank ?? 0) ||
            (b.headroom_hours ?? 0) - (a.headroom_hours ?? 0) ||
            byName(a, b),
        );
    }
  }, [data, search, sort]);

  if (isLoading) return <LoadingBlock label="Loading team capacity" />;
  if (isError)
    return (
      <EmptyState
        title="Could not load capacity"
        description="Assignment is still possible, but without workload guidance."
      />
    );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[10rem]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" />
          <input
            className="input py-1.5 pl-8 text-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Find a designer"
          />
        </div>
        <select
          className="input w-auto py-1.5 text-xs"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          aria-label="Sort candidates"
        >
          <option value="recommended">Best match</option>
          <option value="headroom">Most free hours</option>
          <option value="utilization">Lowest utilisation</option>
          <option value="name">Name</option>
        </select>
      </div>

      {selectedId && (
        <button
          type="button"
          className="mb-2 text-2xs text-brand-600 hover:underline"
          onClick={() => onSelect(null)}
        >
          Clear selection (leave unassigned)
        </button>
      )}

      <div className="max-h-80 divide-y divide-ink-100 overflow-y-auto rounded-md border border-ink-200">
        {candidates.length === 0 && (
          <EmptyState title="Nobody matches" description="Try clearing the search." />
        )}

        {candidates.map((person) => {
          const selected = person.user_id === selectedId;
          const overloaded = person.utilization_band === "Overloaded";
          return (
            <button
              key={person.user_id}
              type="button"
              onClick={() => onSelect(person.user_id)}
              className={clsx(
                "flex w-full items-start gap-3 px-3 py-2 text-left transition-colors",
                selected ? "bg-brand-50" : "hover:bg-ink-50",
              )}
            >
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 text-xs font-medium text-ink-900">
                  {person.full_name}
                  {person.has_required_skill === true && (
                    <span className="rounded bg-rag-greenBg px-1 py-0.5 text-2xs font-medium text-rag-green">
                      has skill
                    </span>
                  )}
                  {person.has_required_skill === false && (
                    <span className="rounded bg-ink-100 px-1 py-0.5 text-2xs text-ink-500">
                      no skill match
                    </span>
                  )}
                  {overloaded && (
                    <AlertTriangle
                      className="h-3 w-3 text-rag-red"
                      aria-label="Overloaded"
                    />
                  )}
                </p>
                <p className="mt-0.5 text-2xs text-ink-500">
                  {person.open_tasks} open ·{" "}
                  {hours(person.allocated_hours)} of {hours(person.available_hours)}{" "}
                  allocated
                  {person.headroom_hours !== null &&
                    person.headroom_hours !== undefined && (
                      <>
                        {" · "}
                        <span
                          className={
                            person.headroom_hours <= 0
                              ? "font-medium text-rag-red"
                              : "text-rag-green"
                          }
                        >
                          {person.headroom_hours > 0
                            ? `${person.headroom_hours.toFixed(1)}h free`
                            : `${Math.abs(person.headroom_hours).toFixed(1)}h over`}
                        </span>
                      </>
                    )}
                </p>
                <p className="text-2xs text-ink-400">
                  Next deadline: {shortDate(person.next_deadline) ?? DASH}
                  {person.skills.length > 0 && (
                    <>
                      {" · "}
                      {person.skills
                        .slice(0, 3)
                        .map((s) => `${s.name} (${s.level})`)
                        .join(", ")}
                    </>
                  )}
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                <UtilizationBadge
                  band={person.utilization_band}
                  value={person.utilization_percent}
                />
                {selected && <Check className="h-4 w-4 text-brand-600" />}
              </div>
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-2xs text-ink-400">
        Utilisation bands come from the configured capacity thresholds, so
        changing them in Settings changes what counts as overloaded here.
      </p>
    </div>
  );
}
