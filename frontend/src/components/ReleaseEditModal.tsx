/**
 * Edit a design release.
 *
 * The lead is not here: the release page already has Assign lead / Reassign
 * lead beside the header, and that path notifies the person receiving it. Two
 * ways to do the same thing is how one of them ends up being the one that
 * forgets to tell anybody.
 *
 * The dates are the part worth care. Giving a release its first planned dates
 * also stamps its baseline -- the one date in this system nothing is allowed to
 * revise afterwards, because on-time delivery is measured against it. Judged
 * against a target that follows the work, everything is always on time. So the
 * form says which case the reader is in rather than letting them find out from
 * a report months later.
 */

import { useEffect, useState } from "react";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { useUpdateRelease, useVocabularies } from "@/hooks/queries";
import { shortDate } from "@/lib/format";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { Priority, ReleaseDetail } from "@/types/api";

export function ReleaseEditModal({
  release,
  open,
  onClose,
  onSaved,
}: {
  release: ReleaseDetail;
  open: boolean;
  onClose: () => void;
  onSaved: (release: ReleaseDetail) => void;
}) {
  const update = useUpdateRelease(release.id);
  const vocab = useVocabularies();

  const [name, setName] = useState(release.name);
  const [releaseType, setReleaseType] = useState(release.release_type ?? "");
  const [description, setDescription] = useState(release.description ?? "");
  const [priority, setPriority] = useState<Priority>(release.priority);
  const [plannedStart, setPlannedStart] = useState(release.planned_start ?? "");
  const [plannedEnd, setPlannedEnd] = useState(release.planned_end ?? "");

  useEffect(() => {
    if (!open) return;
    setName(release.name);
    setReleaseType(release.release_type ?? "");
    setDescription(release.description ?? "");
    setPriority(release.priority);
    setPlannedStart(release.planned_start ?? "");
    setPlannedEnd(release.planned_end ?? "");
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, release.id, release.updated_at]);

  // A type no longer in the vocabulary is still the truth about this release;
  // dropping it would blank the control and rewrite the field on save.
  const types = vocab.data?.release_types ?? [];
  const typeOptions = [
    ...types.map((v) => ({ value: v, label: v })),
    ...(releaseType && !types.includes(releaseType)
      ? [{ value: releaseType, label: `${releaseType} (retired)` }]
      : []),
  ];

  const hasBaseline = Boolean(release.baseline_planned_end);
  const datesBackwards =
    Boolean(plannedStart) && Boolean(plannedEnd) && plannedEnd < plannedStart;
  const ready = name.trim().length > 0 && !datesBackwards;

  const save = () => {
    if (!ready) return;
    update.mutate(
      {
        name: name.trim(),
        release_type: releaseType.trim() || null,
        description: description.trim() || null,
        priority,
        // Cleared means cleared, so a release can be unscheduled again.
        planned_start: plannedStart || null,
        planned_end: plannedEnd || null,
      },
      { onSuccess: (saved) => onSaved(saved) },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit ${release.code}`}
      description="Changes are recorded against your name in the audit trail."
      size="lg"
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={save}
            disabled={update.isPending || !ready}
          >
            {update.isPending && <Spinner />}
            Save changes
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError error={update.error} />

        <Field label="Name" htmlFor="release_name" required>
          <TextInput
            id="release_name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type" htmlFor="release_type">
            <Select
              id="release_type"
              value={releaseType}
              onChange={(e) => setReleaseType(e.target.value)}
              placeholder="Not set"
              options={typeOptions}
            />
          </Field>

          <Field label="Priority" htmlFor="release_priority">
            <Select
              id="release_priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as Priority)}
              options={toOptions(PRIORITIES)}
            />
          </Field>
        </div>

        <Field label="Notes" htmlFor="release_description">
          <TextArea
            id="release_description"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Target start" htmlFor="release_start">
            <TextInput
              id="release_start"
              type="date"
              value={plannedStart}
              onChange={(e) => setPlannedStart(e.target.value)}
            />
          </Field>

          <Field
            label="Handover target"
            htmlFor="release_end"
            hint={
              datesBackwards
                ? "The handover date cannot be before the start."
                : "When design hands this over. Not the dispatch date."
            }
          >
            <TextInput
              id="release_end"
              type="date"
              value={plannedEnd}
              onChange={(e) => setPlannedEnd(e.target.value)}
            />
          </Field>
        </div>

        {hasBaseline ? (
          <InlineAlert tone="info">
            Committed to {shortDate(release.baseline_planned_end)}. Moving the
            target above does not move that — delivery is still measured against
            the original commitment, and the move is recorded.
          </InlineAlert>
        ) : (
          plannedEnd && (
            <InlineAlert tone="warn">
              This release has no commitment yet, so saving a handover target
              sets one. It is the date on-time delivery will be judged against
              from now on, and it does not change afterwards.
            </InlineAlert>
          )
        )}

        <p className="text-2xs text-ink-500">
          The team lead is set with Assign lead on the release page, which tells
          them they have it.
        </p>
      </div>
    </Modal>
  );
}
