/**
 * The product-based template library (spec section 9).
 *
 * Versioning is the point of this screen: a published version is immutable
 * because releases were generated from it, so editing means opening a new
 * draft. The UI makes that the only available path rather than letting someone
 * discover it through a 400.
 */

import { Check, FileStack, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Card,
  EmptyState,
  ErrorState,
  InlineAlert,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import {
  useCreateDraft,
  useCreateTemplate,
  usePublishVersion,
  useSaveVersionTasks,
  useProducts,
  useProductFamilies,
  useSkills,
  useTemplates,
  useVocabularies,
} from "@/hooks/queries";
import { DASH } from "@/lib/format";
import { PRIORITIES } from "@/lib/vocab";
import { P, useAuth } from "@/store/auth";
import type { TemplateTask } from "@/types/api";

/** A task row while it is being edited; ids are absent for new rows. */
interface DraftRow {
  key: string;
  sequence: number;
  name: string;
  task_type: string;
  description: string;
  default_estimated_hours: number;
  default_priority: string;
  complexity: number;
  required_skill_id: string;
  is_mandatory: boolean;
  requires_review: boolean;
  depends_on_sequence: number | null;
}

const toRow = (task: TemplateTask, index: number): DraftRow => ({
  key: task.id ?? `row-${index}`,
  sequence: task.sequence,
  name: task.name,
  task_type: task.task_type,
  description: task.description ?? "",
  default_estimated_hours: task.default_estimated_hours,
  default_priority: task.default_priority,
  complexity: task.complexity,
  required_skill_id: task.required_skill_id ?? "",
  is_mandatory: task.is_mandatory,
  requires_review: task.requires_review,
  depends_on_sequence: task.depends_on_sequence,
});

export default function Templates() {
  const can = useAuth((s) => s.can);
  // The list endpoint omits task lists by default to stay cheap; this screen
  // is the one place that needs them.
  const {
    data: templates,
    isLoading,
    isError,
    error,
    refetch,
  } = useTemplates({ include_tasks: true });
  const { data: skills } = useSkills();
  const { data: products } = useProducts();
  const { data: families } = useProductFamilies();
  const { data: vocab } = useVocabularies();

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [rows, setRows] = useState<DraftRow[] | null>(null);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [draftingFrom, setDraftingFrom] = useState(false);
  const [changeNote, setChangeNote] = useState("");

  const template =
    templates?.find((t) => t.id === selectedTemplateId) ?? templates?.[0] ?? null;
  const version =
    template?.versions.find((v) => v.id === selectedVersionId) ??
    template?.versions.find((v) => v.is_published) ??
    template?.versions[0] ??
    null;

  const createTemplate = useCreateTemplate();
  const createDraft = useCreateDraft(template?.id ?? "");
  const saveTasks = useSaveVersionTasks(version?.id ?? "");
  const publish = usePublishVersion();

  const editing = rows !== null;
  const canManage = can(P.templateManage);

  const skillOptions = useMemo(
    () => (skills ?? []).map((s) => ({ value: s.id, label: s.name })),
    [skills],
  );

  const startEditing = () => {
    if (!version) return;
    setRows(version.tasks.map(toRow));
  };

  const updateRow = (key: string, patch: Partial<DraftRow>) =>
    setRows((current) =>
      current?.map((row) => (row.key === key ? { ...row, ...patch } : row)) ?? null,
    );

  const addRow = () =>
    setRows((current) => {
      const next = current ?? [];
      const sequence = next.length
        ? Math.max(...next.map((r) => r.sequence)) + 1
        : 1;
      return [
        ...next,
        {
          key: `new-${Date.now()}`,
          sequence,
          name: "",
          task_type: vocab?.task_types?.[0] ?? "",
          description: "",
          default_estimated_hours: 4,
          default_priority: "Medium",
          complexity: 3,
          required_skill_id: "",
          is_mandatory: true,
          requires_review: true,
          depends_on_sequence: next.length ? sequence - 1 : null,
        },
      ];
    });

  const save = () => {
    if (!rows) return;
    const payload = rows.map((row) => ({
      sequence: row.sequence,
      name: row.name,
      task_type: row.task_type,
      description: row.description || null,
      default_estimated_hours: row.default_estimated_hours,
      default_priority: row.default_priority,
      complexity: row.complexity,
      required_skill_id: row.required_skill_id || null,
      is_mandatory: row.is_mandatory,
      requires_review: row.requires_review,
      depends_on_sequence: row.depends_on_sequence,
    }));
    saveTasks.mutate(payload, { onSuccess: () => setRows(null) });
  };

  if (isLoading) {
    return (
      <>
        <PageHeader title="Design Templates" />
        <div className="card">
          <SkeletonRows rows={6} />
        </div>
      </>
    );
  }

  if (isError) {
    return (
      <div className="card">
        <ErrorState
          message={error instanceof Error ? error.message : undefined}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Design Templates"
        subtitle="Standard task lists per product and release type. Releases pin the version they were generated from."
        actions={
          canManage && (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setCreatingTemplate(true)}
            >
              <Plus className="h-4 w-4" />
              New template
            </button>
          )
        }
      />

      {(templates?.length ?? 0) === 0 ? (
        <div className="card">
          <EmptyState
            title="No templates yet"
            description="A template turns a release type into a standard task list, so every Mechanical Design release starts the same way."
            icon={<FileStack className="h-7 w-7" />}
            action={
              canManage && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setCreatingTemplate(true)}
                >
                  Create the first template
                </button>
              )
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-4">
          <Card title="Templates" bodyClassName="" className="lg:col-span-1">
            <ul className="divide-y divide-ink-100">
              {templates?.map((t) => {
                const active = t.id === template?.id;
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      className={`w-full px-3 py-2.5 text-left transition-colors ${
                        active ? "bg-brand-50" : "hover:bg-ink-50"
                      }`}
                      onClick={() => {
                        setSelectedTemplateId(t.id);
                        setSelectedVersionId(null);
                        setRows(null);
                      }}
                    >
                      <p
                        className={`text-xs font-medium ${
                          active ? "text-brand-700" : "text-ink-900"
                        }`}
                      >
                        {t.name}
                      </p>
                      <p className="mt-0.5 text-2xs text-ink-500">
                        {t.release_type}
                        {t.product_name ? ` · ${t.product_name}` : ""}
                        {!t.product_name && t.product_family_name
                          ? ` · ${t.product_family_name} family`
                          : ""}
                      </p>
                      <p className="text-2xs text-ink-400">
                        {t.versions.length} version
                        {t.versions.length === 1 ? "" : "s"}
                        {t.current_version_number
                          ? ` · v${t.current_version_number} live`
                          : " · none published"}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <div className="space-y-4 lg:col-span-3">
            {template && (
              <Card
                title={
                  <span className="flex items-center gap-2">
                    {template.name}
                    <span className="font-normal text-ink-500">
                      {template.release_type}
                    </span>
                  </span>
                }
                action={
                  canManage &&
                  !editing && (
                    <div className="flex items-center gap-2">
                      {version && !version.is_published && (
                        <>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={startEditing}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                            Edit tasks
                          </button>
                          <button
                            type="button"
                            className="btn-primary"
                            onClick={() => publish.mutate(version.id)}
                            disabled={publish.isPending || version.tasks.length === 0}
                            title={
                              version.tasks.length === 0
                                ? "Add at least one task before publishing"
                                : undefined
                            }
                          >
                            {publish.isPending && <Spinner />}
                            Publish v{version.version_number}
                          </button>
                        </>
                      )}
                      {version?.is_published && (
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => {
                            setChangeNote("");
                            setDraftingFrom(true);
                          }}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          New draft version
                        </button>
                      )}
                    </div>
                  )
                }
                bodyClassName=""
              >
                <div className="flex flex-wrap items-center gap-1.5 border-b border-ink-100 px-4 py-2">
                  <span className="mr-1 text-2xs font-medium uppercase tracking-wide text-ink-500">
                    Versions
                  </span>
                  {template.versions.map((v) => {
                    const active = v.id === version?.id;
                    return (
                      <button
                        key={v.id}
                        type="button"
                        onClick={() => {
                          setSelectedVersionId(v.id);
                          setRows(null);
                        }}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs transition-colors ${
                          active
                            ? "border-brand-600 bg-brand-600 text-white"
                            : "border-ink-300 bg-white text-ink-600 hover:bg-ink-100"
                        }`}
                      >
                        {v.is_published ? (
                          <Lock className="h-2.5 w-2.5" />
                        ) : (
                          <Pencil className="h-2.5 w-2.5" />
                        )}
                        {v.label}
                        {!v.is_published && " (draft)"}
                      </button>
                    );
                  })}
                </div>

                {publish.isError && (
                  <div className="p-4">
                    <FormError error={publish.error} />
                  </div>
                )}
                {saveTasks.isError && (
                  <div className="p-4">
                    <FormError error={saveTasks.error} />
                  </div>
                )}

                {version?.is_published && (
                  <div className="px-4 pt-3">
                    <InlineAlert tone="info">
                      This version is published and cannot be changed — releases
                      have already been generated from it. Open a new draft to
                      revise the task list.
                    </InlineAlert>
                  </div>
                )}

                {!version ? (
                  <EmptyState title="No versions" />
                ) : editing ? (
                  <TaskEditor
                    rows={rows!}
                    skillOptions={skillOptions}
                    taskTypes={vocab?.task_types ?? []}
                    onChange={updateRow}
                    onAdd={addRow}
                    onRemove={(key) =>
                      setRows((current) => current?.filter((r) => r.key !== key) ?? null)
                    }
                    onSave={save}
                    onCancel={() => setRows(null)}
                    saving={saveTasks.isPending}
                  />
                ) : (
                  <ReadOnlyTasks tasks={version.tasks} />
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {/* New template */}
      <NewTemplateModal
        open={creatingTemplate}
        onClose={() => setCreatingTemplate(false)}
        products={products ?? []}
        families={families ?? []}
        releaseTypes={vocab?.release_types ?? []}
        mutation={createTemplate}
      />

      {/* New draft from the published version */}
      <Modal
        open={draftingFrom}
        onClose={() => setDraftingFrom(false)}
        title="New draft version"
        description="Copies the current published task list into an editable draft. Existing releases keep the version they were generated from."
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setDraftingFrom(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                createDraft.mutate(changeNote, {
                  onSuccess: (draft: any) => {
                    setDraftingFrom(false);
                    setSelectedVersionId(draft.id);
                  },
                })
              }
              disabled={createDraft.isPending}
            >
              {createDraft.isPending && <Spinner />}
              Create draft
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={createDraft.error} />
          <Field
            label="What is changing?"
            htmlFor="change_note"
            hint="Recorded against the version so the history explains itself."
          >
            <TextArea
              id="change_note"
              value={changeNote}
              onChange={(e) => setChangeNote(e.target.value)}
              placeholder="Added a separate interlock logic check after the 2026 site incident."
            />
          </Field>
        </div>
      </Modal>
    </>
  );
}

function ReadOnlyTasks({ tasks }: { tasks: TemplateTask[] }) {
  if (tasks.length === 0) {
    return (
      <EmptyState
        title="This version has no tasks"
        description="Edit the draft to add the standard tasks for this release type."
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px]">
        <thead className="border-b border-ink-200 bg-ink-50">
          <tr>
            <th className="th w-10">#</th>
            <th className="th">Task</th>
            <th className="th">Type</th>
            <th className="th">Skill</th>
            <th className="th text-right">Est</th>
            <th className="th text-right">Complexity</th>
            <th className="th">Priority</th>
            <th className="th">Depends on</th>
            <th className="th">Flags</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {[...tasks]
            .sort((a, b) => a.sequence - b.sequence)
            .map((task) => (
              <tr key={task.id} className="hover:bg-ink-50">
                <td className="td text-2xs text-ink-400">{task.sequence}</td>
                <td className="td max-w-[20rem]">
                  <div className="font-medium text-ink-900">{task.name}</div>
                  {task.description && (
                    <div className="truncate text-2xs text-ink-500" title={task.description}>
                      {task.description}
                    </div>
                  )}
                </td>
                <td className="td text-xs text-ink-600">{task.task_type}</td>
                <td className="td text-xs text-ink-600">
                  {(task as TemplateTask & { required_skill_name?: string })
                    .required_skill_name ?? DASH}
                </td>
                <td className="td text-right text-xs tabular">
                  {task.default_estimated_hours.toFixed(1)}h
                </td>
                <td className="td text-right text-xs tabular">{task.complexity}</td>
                <td className="td text-xs">{task.default_priority}</td>
                <td className="td text-xs text-ink-500">
                  {task.depends_on_sequence ? `#${task.depends_on_sequence}` : DASH}
                </td>
                <td className="td">
                  <div className="flex gap-1">
                    {task.is_mandatory && (
                      <span className="rounded bg-ink-100 px-1 py-0.5 text-2xs text-ink-600">
                        mandatory
                      </span>
                    )}
                    {task.requires_review && (
                      <span className="rounded bg-purple-50 px-1 py-0.5 text-2xs text-purple-700">
                        review
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

function TaskEditor({
  rows,
  skillOptions,
  taskTypes,
  onChange,
  onAdd,
  onRemove,
  onSave,
  onCancel,
  saving,
}: {
  rows: DraftRow[];
  skillOptions: { value: string; label: string }[];
  taskTypes: string[];
  onChange: (key: string, patch: Partial<DraftRow>) => void;
  onAdd: () => void;
  onRemove: (key: string) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const incomplete = rows.some((r) => r.name.trim() === "" || r.task_type.trim() === "");

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px]">
          <thead className="border-b border-ink-200 bg-ink-50">
            <tr>
              <th className="th w-12">Seq</th>
              <th className="th">Name</th>
              <th className="th w-32">Type</th>
              <th className="th w-40">Skill</th>
              <th className="th w-20">Est h</th>
              <th className="th w-24">Priority</th>
              <th className="th w-20">Cplx</th>
              <th className="th w-24">Depends</th>
              <th className="th w-28">Flags</th>
              <th className="th w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="px-2 py-1">
                  <input
                    className="input px-1.5 py-1 text-xs"
                    type="number"
                    min={1}
                    value={row.sequence}
                    onChange={(e) =>
                      onChange(row.key, { sequence: Number(e.target.value) })
                    }
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    className="input px-2 py-1 text-xs"
                    value={row.name}
                    onChange={(e) => onChange(row.key, { name: e.target.value })}
                    placeholder="GA Drawing"
                  />
                </td>
                <td className="px-2 py-1">
                  <select
                    className="input px-1.5 py-1 text-xs"
                    value={row.task_type}
                    onChange={(e) => onChange(row.key, { task_type: e.target.value })}
                  >
                    <option value="">Choose...</option>
                    {taskTypes.map((tt) => (
                      <option key={tt} value={tt}>
                        {tt}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <select
                    className="input px-1.5 py-1 text-xs"
                    value={row.required_skill_id}
                    onChange={(e) =>
                      onChange(row.key, { required_skill_id: e.target.value })
                    }
                  >
                    <option value="">Any</option>
                    {skillOptions.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <input
                    className="input px-1.5 py-1 text-xs"
                    type="number"
                    min={0}
                    step={0.5}
                    value={row.default_estimated_hours}
                    onChange={(e) =>
                      onChange(row.key, {
                        default_estimated_hours: Number(e.target.value),
                      })
                    }
                  />
                </td>
                <td className="px-2 py-1">
                  <select
                    className="input px-1.5 py-1 text-xs"
                    value={row.default_priority}
                    onChange={(e) =>
                      onChange(row.key, { default_priority: e.target.value })
                    }
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <input
                    className="input px-1.5 py-1 text-xs"
                    type="number"
                    min={1}
                    max={5}
                    value={row.complexity}
                    onChange={(e) =>
                      onChange(row.key, { complexity: Number(e.target.value) })
                    }
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    className="input px-1.5 py-1 text-xs"
                    type="number"
                    min={1}
                    value={row.depends_on_sequence ?? ""}
                    onChange={(e) =>
                      onChange(row.key, {
                        depends_on_sequence: e.target.value
                          ? Number(e.target.value)
                          : null,
                      })
                    }
                    placeholder="—"
                  />
                </td>
                <td className="px-2 py-1">
                  <div className="flex flex-col gap-0.5">
                    <label className="flex items-center gap-1 text-2xs text-ink-600">
                      <input
                        type="checkbox"
                        checked={row.is_mandatory}
                        onChange={(e) =>
                          onChange(row.key, { is_mandatory: e.target.checked })
                        }
                      />
                      mandatory
                    </label>
                    <label className="flex items-center gap-1 text-2xs text-ink-600">
                      <input
                        type="checkbox"
                        checked={row.requires_review}
                        onChange={(e) =>
                          onChange(row.key, { requires_review: e.target.checked })
                        }
                      />
                      review
                    </label>
                  </div>
                </td>
                <td className="px-2 py-1">
                  <button
                    type="button"
                    className="btn-ghost px-1"
                    onClick={() => onRemove(row.key)}
                    aria-label={`Remove ${row.name || "task"}`}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-rag-red" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-200 px-4 py-3">
        <button type="button" className="btn-secondary" onClick={onAdd}>
          <Plus className="h-3.5 w-3.5" />
          Add task
        </button>
        <div className="flex items-center gap-2">
          {incomplete && (
            <span className="text-2xs text-rag-amber">
              Every task needs a name and a type.
            </span>
          )}
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onSave}
            disabled={saving || incomplete || rows.length === 0}
          >
            {saving ? <Spinner /> : <Check className="h-3.5 w-3.5" />}
            Save draft
          </button>
        </div>
      </div>
    </div>
  );
}

function NewTemplateModal({
  open,
  onClose,
  products,
  families,
  releaseTypes,
  mutation,
}: {
  open: boolean;
  onClose: () => void;
  products: { id: string; name: string }[];
  families: { id: string; name: string }[];
  releaseTypes: string[];
  mutation: ReturnType<typeof useCreateTemplate>;
}) {
  const [form, setForm] = useState({
    name: "",
    release_type: "",
    description: "",
    product_id: "",
    product_family_id: "",
  });

  // The API requires one of the two; the form says so rather than letting the
  // request 422 after the Create button looked enabled.
  const hasTarget = Boolean(form.product_id || form.product_family_id);

  const close = () => {
    mutation.reset();
    setForm({
      name: "",
      release_type: "",
      description: "",
      product_id: "",
      product_family_id: "",
    });
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="New design template"
      description="Creates the template and an empty draft version 1 for you to fill in."
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={close}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              const payload: Record<string, unknown> = {
                name: form.name,
                release_type: form.release_type,
              };
              if (form.description) payload.description = form.description;
              if (form.product_id) payload.product_id = form.product_id;
              if (form.product_family_id)
                payload.product_family_id = form.product_family_id;
              mutation.mutate(payload, { onSuccess: close });
            }}
            disabled={
              mutation.isPending ||
              form.name.trim() === "" ||
              form.release_type.trim() === "" ||
              !hasTarget
            }
          >
            {mutation.isPending && <Spinner />}
            Create template
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError error={mutation.error} />
        <Field label="Template name" htmlFor="tname" required>
          <TextInput
            id="tname"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Mechanical Design — Automated Parking System"
            autoFocus
          />
        </Field>
        <Field
          label="Release type"
          htmlFor="ttype"
          required
          hint="Releases of this type will match this template."
        >
          <Select
            id="ttype"
            value={form.release_type}
            onChange={(e) => setForm((f) => ({ ...f, release_type: e.target.value }))}
            placeholder="Choose a release type"
            options={releaseTypes.map((v) => ({ value: v, label: v }))}
          />
        </Field>
        <Field
          label="Product"
          htmlFor="tproduct"
          hint="Pick a product for a template that applies to just that product."
        >
          <Select
            id="tproduct"
            value={form.product_id}
            onChange={(e) =>
              setForm((f) => ({ ...f, product_id: e.target.value, product_family_id: "" }))
            }
            placeholder="No specific product"
            options={products.map((p) => ({ value: p.id, label: p.name }))}
          />
        </Field>

        <Field
          label="or Product family"
          htmlFor="tfamily"
          hint="Pick a family for a template shared across every product in it."
          error={hasTarget ? undefined : "Choose a product or a product family."}
        >
          <Select
            id="tfamily"
            value={form.product_family_id}
            onChange={(e) =>
              setForm((f) => ({ ...f, product_family_id: e.target.value, product_id: "" }))
            }
            placeholder="No family"
            options={families.map((f) => ({ value: f.id, label: f.name }))}
          />
        </Field>
        <Field label="Description" htmlFor="tdesc">
          <TextArea
            id="tdesc"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            rows={2}
          />
        </Field>
      </div>
    </Modal>
  );
}
