/**
 * Confirming a permanent deletion.
 *
 * Everything else destructive in this application is reversible -- a cancelled
 * task can be re-opened, a deleted time entry re-logged. This is the one that
 * is not, and it cascades: deleting a project takes its releases, its tasks and
 * every hour anybody logged against them.
 *
 * Two things follow, and they are the whole reason this is a component rather
 * than a `window.confirm`:
 *
 * The dialog states what will actually be destroyed, fetched from the server
 * while it is open, because "8 releases, 40 tasks and 312 logged hours" is a
 * decision somebody can make and "are you sure?" is not.
 *
 * And it asks for the entity's code to be typed. A confirm button next to a
 * cancel button is one mis-click; typing PRJ-0007 is not something anybody does
 * by accident. The check is deliberately generous about case and surrounding
 * space, because the point is to force a deliberate act, not to test typing.
 */

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { Field, FormError, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/primitives";
import type { DeletionImpact } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  /** "project" | "release" | "task" -- used in the prose. */
  entityLabel: string;
  /** The code the user must type, e.g. PRJ-0007. */
  code: string;
  name: string;
  impact: DeletionImpact | undefined;
  impactLoading: boolean;
  onConfirm: () => void;
  isPending: boolean;
  error: unknown;
}

/** The counts worth showing, in the order they cascade. */
function impactRows(impact: DeletionImpact): { label: string; value: number }[] {
  const rows: { label: string; value: number }[] = [];
  if (impact.releases !== undefined) {
    rows.push({ label: "Design releases", value: impact.releases });
  }
  if (impact.tasks !== undefined) rows.push({ label: "Tasks", value: impact.tasks });
  rows.push({ label: "Time entries", value: impact.time_entries });
  rows.push({ label: "Logged hours", value: impact.logged_hours });
  if (impact.reviews !== undefined) {
    rows.push({ label: "Reviews", value: impact.reviews });
  }
  if (impact.revisions !== undefined) {
    rows.push({ label: "Revisions", value: impact.revisions });
  }
  return rows;
}

export function DeleteEntityDialog({
  open,
  onClose,
  entityLabel,
  code,
  name,
  impact,
  impactLoading,
  onConfirm,
  isPending,
  error,
}: Props) {
  const [typed, setTyped] = useState("");

  const matches = typed.trim().toUpperCase() === code.trim().toUpperCase();

  const close = () => {
    setTyped("");
    onClose();
  };

  // Hours are the number people care about, because they are somebody's
  // recorded work rather than a structural count.
  const hoursAtRisk = impact?.logged_hours ?? 0;

  return (
    <Modal
      open={open}
      onClose={close}
      title={`Delete this ${entityLabel} permanently?`}
      description="This cannot be undone. Nothing here is recoverable except from a database backup."
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={close}>
            Keep it
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={onConfirm}
            disabled={!matches || isPending || impactLoading}
            title={
              matches ? undefined : `Type ${code} to enable this button`
            }
          >
            {isPending && <Spinner />}
            Delete permanently
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <FormError error={error} />

        <div className="flex items-start gap-2 rounded-lg border border-rag-redBg bg-rag-redBg/40 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rag-red" />
          <div className="min-w-0 text-xs text-ink-700">
            <p className="font-medium text-ink-900">
              {code} — {name}
            </p>
            <p className="mt-0.5">
              {hoursAtRisk > 0
                ? `Deleting this removes ${hoursAtRisk} hours of recorded work from every
                   report and dashboard that includes them.`
                : `Deleting this removes it from every report and dashboard.`}{" "}
              To take it out of the working view without losing the history,
              cancel it instead.
            </p>
          </div>
        </div>

        {impactLoading && (
          <p className="text-xs text-ink-500">Counting what this would remove…</p>
        )}

        {impact && (
          <div className="rounded-lg border border-ink-200">
            <p className="border-b border-ink-200 px-3 py-2 text-2xs uppercase tracking-wide text-ink-500">
              What goes with it
            </p>
            <dl className="divide-y divide-ink-100">
              {impactRows(impact).map((row) => (
                <div key={row.label} className="flex justify-between px-3 py-1.5">
                  <dt className="text-xs text-ink-600">{row.label}</dt>
                  <dd className="text-xs tabular font-medium text-ink-900">
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <Field
          label={`Type ${code} to confirm`}
          htmlFor="delete_confirm"
          required
          hint="Deliberately awkward: this is the one action with no undo."
        >
          <TextInput
            id="delete_confirm"
            value={typed}
            autoComplete="off"
            placeholder={code}
            onChange={(e) => setTyped(e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}
