/**
 * The design release standard, per product.
 *
 * This is the design team's own reference: how many design releases a product
 * produces, what each one is, and the five tasks that run inside every one of
 * them. It is read-only here on purpose -- the list is applied to a project
 * from the project's own screen, where the manager has the level count and the
 * site conditions in front of them.
 */

import { CircleDashed, Layers, ListChecks } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { useReleaseStandards } from "@/hooks/queries";
import type { ProductStandard, StandardVariant } from "@/types/api";

function VariantBlock({ variant, tasks }: { variant: StandardVariant; tasks: string[] }) {
  const named = variant.variant !== "standard";

  return (
    <div className="space-y-3">
      {named && (
        <div className="flex flex-wrap items-baseline gap-2 border-l-2 border-signal-600 pl-3">
          <span className="text-sm font-semibold text-ink-900">{variant.variant}</span>
          {variant.condition && (
            <span className="text-xs text-ink-500">{variant.condition}</span>
          )}
        </div>
      )}

      <ol className="space-y-2">
        {variant.releases.map((release) => (
          <li
            key={release.id}
            className={`rounded-md border px-3 py-2 ${
              release.is_default
                ? "border-ink-200 bg-white"
                : "border-dashed border-ink-300 bg-cream-50"
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-900 text-xs font-semibold text-white tabular-nums">
                {release.sequence}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-snug text-ink-900">
                  {release.name}
                  {release.alternative_name && (
                    <span className="text-ink-500"> or {release.alternative_name}</span>
                  )}
                </p>
                {release.condition && (
                  <p className="mt-0.5 flex items-start gap-1 text-xs text-ink-500">
                    <CircleDashed className="mt-px h-3 w-3 shrink-0" />
                    {release.condition}
                  </p>
                )}
              </div>
              {!release.is_default && (
                <span className="shrink-0 rounded-full bg-ink-100 px-2 py-0.5 text-[11px] font-medium text-ink-600">
                  Conditional
                </span>
              )}
            </div>

            {/* Every release runs the same five tasks; showing them once per
                release is noise, so they are named at the foot of the card. */}
          </li>
        ))}
      </ol>

      {tasks.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-ink-500">
          <ListChecks className="h-3.5 w-3.5" />
          <span>Each release runs:</span>
          {tasks.map((task, index) => (
            <span key={task}>
              <span className="font-medium text-ink-700">{task}</span>
              {index < tasks.length - 1 && <span className="text-ink-300"> {"->"} </span>}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function ProductCard({ standard }: { standard: ProductStandard }) {
  const counts = standard.variants.map((v) => v.releases.length);
  const label = Array.from(new Set(counts)).sort((a, b) => a - b).join(" or ");

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold text-ink-900">
          {standard.product_name}
        </h2>
        <span className="flex items-center gap-1.5 rounded-full bg-signal-50 px-2.5 py-1 text-xs font-medium text-signal-700">
          <Layers className="h-3.5 w-3.5" />
          {label} design release{counts.some((c) => c > 1) ? "s" : ""}
        </span>
      </div>

      <div className="space-y-5">
        {standard.variants.map((variant) => (
          <VariantBlock key={variant.variant} variant={variant} tasks={standard.tasks} />
        ))}
      </div>
    </Card>
  );
}

export default function Standards() {
  const { data, isLoading, isError, refetch } = useReleaseStandards();
  const [query, setQuery] = useState("");

  const shown = useMemo(() => {
    if (!data) return [];
    const term = query.trim().toLowerCase();
    if (!term) return data;
    return data.filter(
      (s) =>
        s.product_name.toLowerCase().includes(term) ||
        s.variants.some((v) =>
          v.releases.some((r) => r.name.toLowerCase().includes(term)),
        ),
    );
  }, [data, query]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Design release standards"
        subtitle="What each product releases as standard, and what runs inside every release."
      />

      {isError && <ErrorState onRetry={() => void refetch()} />}
      {isLoading && <SkeletonRows rows={4} cols={2} />}

      {data && (
        <>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a product or a release"
            className="input w-full sm:max-w-sm"
            aria-label="Find a product or a release"
          />

          {shown.length === 0 ? (
            <EmptyState
              title="Nothing matches that"
              description="Try a product name, or part of a release name."
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {shown.map((standard) => (
                <ProductCard key={standard.product_id} standard={standard} />
              ))}
            </div>
          )}

          <p className="text-xs text-ink-500">
            A conditional release is offered, never assumed -- the manager decides
            when applying the standard to a project. Anything a project needs beyond
            the standard is still added as an ordinary design release.
          </p>
        </>
      )}
    </div>
  );
}
