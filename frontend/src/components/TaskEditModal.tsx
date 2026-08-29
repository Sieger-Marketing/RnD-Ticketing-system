/**
 * Edit the things about a task that are decisions rather than events.
 *
 * Deliberately not the whole task. Estimate, assignee and status each have
 * their own control on the task page because each carries a rule the others do
 * not -- a re-estimate wants a reason, assignment notifies the new owner, a
 * status move enforces the workflow. Folding them into one form would either
 * lose those rules or make this dialog the place every rule has to be
 * re-implemented.
 *
 * What is left is the description of the work: what it is, how it is
 * classified, how hard it is, and when it is meant to happen. Those are a team
 * lead's to set, and until now nothing in the app could set them -- the API
 * has accepted PATCH /api/tasks/{id} all along, and no screen ever called it.
 */

import { useEffect, useState } from "react";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/primitives";
import { useUpdateTask, useVocabularies } from "@/hooks/queries";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { Priority, TaskDetail } from "@/types/api";

export function TaskEditModal({
  task,
  open,
  onClose,
  onSaved,
}: {
  task: TaskDetail;
  open: boolean;
  onClose: () => void;
  onSaved: (task: TaskDetail) => void;
}) {
  const update = useUpdateTask(task.id);
  const vocab = useVocabularies();

  const [name, setName] = useState(task.name);
  const [taskType, setTaskType] = useState(task.task_type ?? "");
  const [description, setDescription] = useState(task.description ?? "");
  const [priority, setPriority] = useState<Priority>(task.priority);
  const [complexity, setComplexity] = useState(task.complexity ?? 3);
  const [plannedStart, setPlannedStart] = useState(task.planned_start ?? "");
  const [plannedEnd, setPlannedEnd] = useState(task.planned_end ?? "");
  const [requiresReview, setRequiresReview] = useState(Boolean(task.requires_review));
  const [mandatory, setMandatory] = useState(Boolean(task.is_mandatory));

  // Reopening on a task that changed elsewhere must show the task, not the
  // last thing typed into the dialog.
  useEffect(() => {
    if (!open) return;
    setName(task.name);
    setTaskType(task.task_type ?? "");
    setDescription(task.description ?? "");
    setPriority(task.priority);
    setComplexity(task.complexity ?? 3);
    setPlannedStart(task.planned_start ?? "");
    setPlannedEnd(task.planned_end ?? "");
    setRequiresReview(Boolean(task.requires_review));
    setMandatory(Boolean(task.is_mandatory));
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task.id, task.updated_at]);

  // A type already on the task but no longer in the vocabulary is still the
  // truth about it; dropping it would blank the control and rewrite the field
  // on the next save.
  const taskTypes = vocab.data?.task_types ?? [];
  const typeOptions = [
    ...taskTypes.map((v) => ({ value: v, label: v })),
    ...(taskType && !taskTypes.includes(taskType)
      ? [{ value: taskType, label: `${taskType} (retired)` }]
      : []),
  ];

  const datesBackwards =
    Boolean(plannedStart) && Boolean(plannedEnd) && plannedEnd < plannedStart;
  const ready = name.trim().length > 0 && !datesBackwards;

  const save = () => {
    if (!ready) return;
    update.mutate(
      {
        name: name.trim(),
        task_type: taskType.trim() || null,
        description: description.trim() || null,
        priority,
        complexity,
        // A cleared date means "remove it", so it is sent as null rather than
        // dropped -- otherwise unscheduling a task would be impossible.
        planned_start: plannedStart || null,
        planned_end: plannedEnd || null,
        requires_review: requiresReview,
        is_mandatory: mandatory,
      },
      { onSuccess: (saved) => onSaved(saved) },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit ${task.code}`}
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

        <Field label="What is it" htmlFor="task_name" required>
          <TextInput
            id="task_name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type" htmlFor="task_type" hint="Groups it for reporting.">
            <Select
              id="task_type"
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              placeholder="Not set"
              options={typeOptions}
            />
          </Field>

          <Field label="Priority" htmlFor="task_priority">
            <Select
              id="task_priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as Priority)}
              options={toOptions(PRIORITIES)}
            />
          </Field>
        </div>

        <Field label="Notes" htmlFor="task_description">
          <TextArea
            id="task_description"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Anything the person doing it needs to know."
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Complexity" htmlFor="task_complexity" hint="1 simple, 5 hard.">
            <Select
              id="task_complexity"
              value={String(complexity)}
              onChange={(e) => setComplexity(Number(e.target.value))}
              options={[1, 2, 3, 4, 5].map((n) => ({
                value: String(n),
                label: String(n),
              }))}
            />
          </Field>

          <Field label="Planned start" htmlFor="task_start">
            <TextInput
              id="task_start"
              type="date"
              value={plannedStart}
              onChange={(e) => setPlannedStart(e.target.value)}
            />
          </Field>

          <Field
            label="Due"
            htmlFor="task_end"
            hint={
              datesBackwards ? "Due cannot be before the start." : "Blank means unscheduled."
            }
          >
            <TextInput
              id="task_end"
              type="date"
              value={plannedEnd}
              onChange={(e) => setPlannedEnd(e.target.value)}
            />
          </Field>
        </div>

        <div className="space-y-2">
          <label className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={requiresReview}
              onChange={(e) => setRequiresReview(e.target.checked)}
            />
            <span className="min-w-0 text-sm text-ink-900">
              Needs a review before it can be completed
              <span className="mt-0.5 block text-xs text-ink-500">
                Off means the person doing it closes it themselves. On means it
                goes to a reviewer first — so somebody has to be there to review it.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={mandatory}
              onChange={(e) => setMandatory(e.target.checked)}
            />
            <span className="min-w-0 text-sm text-ink-900">
              Required for the release to be complete
              <span className="mt-0.5 block text-xs text-ink-500">
                Optional tasks do not hold the release open.
              </span>
            </span>
          </label>
        </div>

        <p className="text-2xs text-ink-500">
          Estimate, who it is assigned to, and its status each have their own
          control on the task page — they carry rules this form does not.
        </p>
      </div>
    </Modal>
  );
}
