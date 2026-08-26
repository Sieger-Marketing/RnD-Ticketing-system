/**
 * Apply a product's standard design releases to a project.
 *
 * The design team already knows a Tower project releases five DSQs and an
 * H-Cart six. This turns that knowledge into the releases themselves, with
 * their five tasks, instead of a coordinator retyping the list per project.
 *
 * Conditional releases start unticked with their rule shown, because only the
 * person applying it knows the level count and whether the site has a ceiling.
 */

import { AlertCircle, CircleDashed, Layers } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Field, FormError } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { useApplyStandard, useProductStandard, useReleases } from "@/hooks/queries";
import type { ReleaseSummary, UUID } from "@/types/api";

export function ApplyStandardModal({
  open,
  projectId,
  productId,
  productName,
  onClose,
  onApplied,
}: {
  open: boolean;
  projectId: UUID;
  productId: UUID | null;
  productName: string | null;
  onClose: () => void;
  onApplied: (created: ReleaseSummary[]) => void;
}) {
  const standard = useProductStandard(open ? productId : null);
  const apply = useApplyStandard(projectId);

  // What the project already has. Without this the dialog offers to create
  // releases that exist, pre-ticked, and the only way to find out is to submit
  // and be refused -- which is how "nothing was added" became the normal
  // outcome of applying a standard to an imported project.
  const existing = useReleases(open ? { project_id: projectId, page_size: 200 } : undefined);
  const existingNames = useMemo(
    () =>
      new Set(
        (existing.data?.items ?? []).map((r) => r.name.trim().toLowerCase()),
      ),
    [existing.data],
  );

  const [variant, setVariant] = useState("standard");
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const variants = standard.data?.variants ?? [];
  const active = useMemo(
    () => variants.find((v) => v.variant === variant) ?? variants[0],
    [variants, variant],
  );

  // Every variant is a different list, so the ticks belong to the variant
  // rather than to the dialog: switching resets to that list's defaults.
  //
  // Keyed on the variant NAME, not on `active` itself. `active` is derived from
  // query data, so a refetch -- a window regaining focus is enough -- hands
  // back an equal object with a new identity, this effect re-runs, and every
  // tick the user has made is silently reset to the defaults. Ticking an
  // optional release and then glancing at another window was enough to lose
  // it, and because the defaults all exist already the next Apply came back
  // "Every selected release already exists on this project", which describes
  // a selection the user never made.
  const activeVariant = active?.variant;
  useEffect(() => {
    if (!active) return;
    setChecked(
      Object.fromEntries(
        active.releases.map((r) => [
          r.id,
          // Never pre-tick something that is already there.
          r.is_default && !existingNames.has(r.name.trim().toLowerCase()),
        ]),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVariant, open, existingNames]);

  useEffect(() => {
    if (!open) {
      setVariant("standard");
      apply.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selected = active?.releases.filter((r) => checked[r.id]) ?? [];

  const submit = () => {
    apply.mutate(
      {
        variant: active?.variant ?? "standard",
        release_ids: selected.map((r) => r.id),
      },
      { onSuccess: (created) => onApplied(created) },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Apply the design release standard"
      description={
        productName ? `The releases a ${productName} produces as standard.` : undefined
      }
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={selected.length === 0 || apply.isPending}
            onClick={submit}
          >
            {apply.isPending && <Spinner className="h-4 w-4" />}
            Create {selected.length} release{selected.length === 1 ? "" : "s"}
          </button>
        </>
      }
    >
      {!productId && (
        <InlineAlert tone="warn">
          <p className="font-medium">This project has no product.</p>
          <p>Set the project&rsquo;s product first &mdash; a standard is defined per product.</p>
        </InlineAlert>
      )}

      {standard.isLoading && <Spinner />}

      {standard.data && variants.length === 0 && (
        <InlineAlert tone="warn">
          <p className="font-medium">
            {standard.data.product_name} has no standard release list yet.
          </p>
          <p>Add its releases one at a time, or ask a manager to define the standard.</p>
        </InlineAlert>
      )}

      <FormError error={apply.error} />

      {active && (
        <div className="space-y-4">
          {variants.length > 1 && (
            <Field label="Which standard applies?">
              <div className="space-y-2">
                {variants.map((v) => (
                  <label
                    key={v.variant}
                    className={
                      v.variant === active.variant
                        ? "flex cursor-pointer items-start gap-2 rounded-md border border-signal-600 bg-signal-50 px-3 py-2"
                        : "flex cursor-pointer items-start gap-2 rounded-md border border-ink-200 px-3 py-2"
                    }
                  >
                    <input
                      type="radio"
                      name="standard-variant"
                      className="mt-1"
                      checked={v.variant === active.variant}
                      onChange={() => setVariant(v.variant)}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-ink-900">
                        {v.variant === "standard" ? "Standard" : v.variant}
                        <span className="ml-1.5 font-normal text-ink-500">
                          {v.releases.length} release{v.releases.length === 1 ? "" : "s"}
                        </span>
                      </span>
                      {v.condition && (
                        <span className="block text-xs text-ink-500">{v.condition}</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </Field>
          )}

          <Field label="Releases to create">
            <ul className="space-y-2">
              {active.releases.map((release) => {
                const alreadyThere = existingNames.has(
                  release.name.trim().toLowerCase(),
                );
                return (
                <li key={release.id}>
                  <label className="flex cursor-pointer items-start gap-2.5 rounded-md border border-ink-200 px-3 py-2 hover:bg-cream-50">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(checked[release.id])}
                      onChange={(event) =>
                        setChecked((prev) => ({
                          ...prev,
                          [release.id]: event.target.checked,
                        }))
                      }
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-ink-900">
                        <span className="mr-1.5 font-mono text-xs text-ink-400">
                          {release.sequence}
                        </span>
                        {release.name}
                        {release.alternative_name && (
                          <span className="text-ink-500"> or {release.alternative_name}</span>
                        )}
                        {alreadyThere && (
                          <span className="ml-2 rounded bg-ink-100 px-1.5 py-0.5 text-2xs font-medium text-ink-600">
                            already on this project
                          </span>
                        )}
                      </span>
                      {release.condition && (
                        <span className="mt-0.5 flex items-start gap-1 text-xs text-ink-500">
                          <CircleDashed className="mt-px h-3 w-3 shrink-0" />
                          {release.condition}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              );
              })}
            </ul>
          </Field>

          {standard.data && standard.data.tasks.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 rounded-md bg-cream-100 px-3 py-2 text-xs text-ink-600">
              <Layers className="h-3.5 w-3.5 shrink-0" />
              Each release is created with{" "}
              <span className="font-medium text-ink-800">
                {standard.data.tasks.join(", ")}
              </span>
              .
            </p>
          )}

          <p className="flex items-start gap-1.5 text-xs text-ink-500">
            <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
            Releases already on this project are left alone. You can still add, rename
            or remove releases afterwards.
          </p>
        </div>
      )}
    </Modal>
  );
}
