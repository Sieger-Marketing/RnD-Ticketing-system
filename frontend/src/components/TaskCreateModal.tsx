/**
 * Add a task to a design release, beyond the five the standard generates.
 *
 * The standard covers what every release always does. Real work has extra:
 * a site visit, a supplier drawing, a rework of something the customer changed
 * their mind about. Without this, the only way to record that work was to
 * pretend it was one of the five, which is how a timesheet stops matching what
 * anyone actually did.
 *
 * It lands at the end of the sequence, because it is an addition rather than an
 * insertion — putting it in the middle would renumber tasks that people are
 * already referring to by position.
 */

import { useState } from "react";

import { AssigneePicker } from "@/components/AssigneePicker";
import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { useCreateTask, useSkills, useVocabularies } from "@/hooks/queries";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { TaskDetail, UUID } from "@/types/api";

export function TaskCreateModal({
  releaseId,
  releaseName,
  onClose,
  onCreated,
}: {
  releaseId: UUID;
  releaseName: string;
  onClose: () => void;
  onCreated: (task: TaskDetail) => void;
}) {
  const create = useCreateTask();
  const skills = useSkills();
  const vocab = useVocabularies();

  const [name, setName] = useState("");
  const [taskType, setTaskType] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [complexity, setComplexity] = useState(3);
  const [estimate, setEstimate] = useState(0);
  const [plannedStart, setPlannedStart] = useState("");
  const [plannedEnd, setPlannedEnd] = useState("");
  const [assignee, setAssignee] = useState<UUID | null>(null);
  const [skillId, setSkillId] = useState("");
  const [requiresReview, setRequiresReview] = useState(true);
  const [mandatory, setMandatory] = useState(true);

  // The vocabulary lives behind the settings API; falling back keeps the form
  // usable for a team lead who cannot read it.
  const taskTypes = vocab.data?.task_types ?? [];

  const datesBackwards =
    Boolean(plannedStart) && Boolean(plannedEnd) && plannedEnd < plannedStart;
  const ready = name.trim().length > 0 && taskType.trim().length > 0 && !datesBackwards;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    create.mutate(
      {
        release_id: releaseId,
        name: name.trim(),
        task_type: taskType.trim(),
        description: description.trim() || null,
        priority,
        complexity,
        estimated_hours: estimate,
        planned_start: plannedStart || null,
        planned_end: plannedEnd || null,
        assigned_to_id: assignee,
        required_skill_id: skillId || null,
        requires_review: requiresReview,
        is_mandatory: mandatory,
      },
      { onSuccess: (task) => onCreated(task) },
    );
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Add a task"
      description={`It will be added to ${releaseName}, after the tasks already there.`}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="task-form"
            className="btn-primary"
            disabled={!ready || create.isPending}
          >
            {create.isPending && <Spinner className="h-4 w-4" />}
            Add task
          </button>
        </>
      }
    >
      <form id="task-form" onSubmit={submit} className="space-y-3">
        <FormError error={create.error} />

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="What is it">
            <TextInput
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Supplier drawing review"
              required
            />
          </Field>

          <Field label="Type" hint="Groups it for reporting.">
            {taskTypes.length > 0 ? (
              <Select
                value={taskType}
                onChange={(event) => setTaskType(event.target.value)}
                options={toOptions(taskTypes)}
                placeholder="Choose a type"
              />
            ) : (
              <TextInput
                value={taskType}
                onChange={(event) => setTaskType(event.target.value)}
                placeholder="2D Drawing"
                required
              />
            )}
          </Field>
        </div>

        <Field label="Notes">
          <TextArea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            placeholder="Why this is needed, and anything the designer should know."
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Priority">
            <Select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              options={toOptions(PRIORITIES)}
            />
          </Field>

          <Field label="Complexity" hint="1 simple, 5 hard.">
            <TextInput
              type="number"
              min={1}
              max={5}
              value={complexity}
              onChange={(event) => setComplexity(Number(event.target.value))}
            />
          </Field>

          <Field label="Estimate (hours)">
            <TextInput
              type="number"
              min={0}
              step={0.5}
              value={estimate}
              onChange={(event) => setEstimate(Number(event.target.value))}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Planned start">
            <TextInput
              type="date"
              value={plannedStart}
              onChange={(event) => setPlannedStart(event.target.value)}
            />
          </Field>
          <Field
            label="Planned end"
            error={datesBackwards ? "The end cannot be before the start." : undefined}
          >
            <TextInput
              type="date"
              value={plannedEnd}
              min={plannedStart || undefined}
              onChange={(event) => setPlannedEnd(event.target.value)}
            />
          </Field>
        </div>

        <Field label="Skill needed" hint="Used to suggest who should do it.">
          <Select
            value={skillId}
            onChange={(event) => setSkillId(event.target.value)}
            options={[
              { value: "", label: "Any" },
              ...(skills.data ?? []).map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </Field>

        <Field label="Give it to" hint="Anyone who does design work. Can be left for later.">
          <AssigneePicker
            requiredSkillId={skillId || null}
            selectedId={assignee}
            onSelect={setAssignee}
          />
        </Field>

        <div className="space-y-2">
          <label className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={requiresReview}
              onChange={(event) => setRequiresReview(event.target.checked)}
            />
            <span className="text-sm text-ink-900">
              Needs checking before it counts as done
              <span className="mt-0.5 block text-xs text-ink-500">
                It will go through review rather than straight to complete.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={mandatory}
              onChange={(event) => setMandatory(event.target.checked)}
            />
            <span className="text-sm text-ink-900">
              The release cannot complete without it
              <span className="mt-0.5 block text-xs text-ink-500">
                Untick for work that is useful but not a condition of release.
              </span>
            </span>
          </label>
        </div>

        {!mandatory && (
          <InlineAlert tone="info">
            This task will not block the release from being completed, and will
            not appear in its completion blockers.
          </InlineAlert>
        )}
      </form>
    </Modal>
  );
}
