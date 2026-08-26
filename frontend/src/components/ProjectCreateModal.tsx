import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/primitives";
import {
  useCreateProject,
  useCustomers,
  useProducts,
  useUpdateProject,
  useUsers,
  useVocabularies,
} from "@/hooks/queries";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { ProjectDetail } from "@/types/api";

const EMPTY_UUID = "00000000-0000-0000-0000-000000000000";

const EMPTY = {
  name: "",
  description: "",
  customer_id: "",
  product_id: "",
  project_type: "",
  sales_order: "",
  work_order: "",
  team_lead_id: "",
  priority: "Medium",
  start_date: "",
  required_completion_date: "",
  internal_deadline: "",
  customer_deadline: "",
  external_id: "",
};

/** The form's shape, filled from a project when one is being edited. */
function formFor(project: ProjectDetail | undefined): typeof EMPTY {
  if (!project) return EMPTY;
  return {
    name: project.name ?? "",
    description: project.description ?? "",
    customer_id: project.customer_id ?? "",
    product_id: project.product_id ?? "",
    project_type: project.project_type ?? "",
    sales_order: project.sales_order ?? "",
    work_order: project.work_order ?? "",
    team_lead_id: project.team_lead_id ?? "",
    priority: project.priority ?? "Medium",
    start_date: project.start_date ?? "",
    required_completion_date: project.required_completion_date ?? "",
    internal_deadline: project.internal_deadline ?? "",
    customer_deadline: project.customer_deadline ?? "",
    external_id: project.external_id ?? "",
  };
}

/**
 * Creates a project, or edits one.
 *
 * One form rather than two, because two drift: a field added to the create
 * form and forgotten on the edit form is a field nobody can ever correct.
 */
export function ProjectCreateModal({
  open,
  onClose,
  onCreated,
  project,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (project: ProjectDetail) => void;
  /** Editing this project rather than creating a new one. */
  project?: ProjectDetail;
}) {
  const editing = project !== undefined;
  const [form, setForm] = useState(() => formFor(project));
  const create = useCreateProject();
  const update = useUpdateProject(project?.id ?? EMPTY_UUID);
  const mutation = editing ? update : create;

  // Reopening on a different project, or after it was saved elsewhere, must
  // show that project rather than whatever was last typed.
  useEffect(() => {
    if (open) setForm(formFor(project));
  }, [open, project]);

  const { data: customers } = useCustomers();
  const { data: products } = useProducts();
  const { data: leads } = useUsers({ role: "Team Lead" });
  const { data: vocab } = useVocabularies();

  const typeOptions = vocab?.project_types ?? [];

  const set = (key: keyof typeof EMPTY) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const close = () => {
    mutation.reset();
    setForm(formFor(project));
    onClose();
  };

  const submit = () => {
    const payload: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(form)) {
      if (value !== "") {
        payload[key] = value;
      } else if (editing) {
        // On an edit, a cleared field means "remove this". Dropping it as the
        // create path does would make clearing a date silently impossible.
        // On a create there is nothing to clear, so a blank is still omitted:
        // the API rejects "" where it wants a UUID or a date.
        payload[key] = null;
      }
    }
    mutation.mutate(payload as never, {
      onSuccess: (saved: ProjectDetail) => {
        if (!editing) setForm(EMPTY);
        onCreated(saved);
      },
    });
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={editing ? `Edit ${project.code}` : "New project"}
      description={
        editing
          ? "Changes are recorded against your name in the audit trail."
          : "A project holds the design releases for one customer deliverable."
      }
      size="lg"
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={close}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={
              mutation.isPending ||
              form.name.trim() === "" ||
              form.team_lead_id === ""
            }
          >
            {mutation.isPending && <Spinner />}
            {editing ? "Save changes" : "Create project"}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError error={mutation.error} />

        <Field label="Project name" htmlFor="name" required>
          <TextInput
            id="name"
            value={form.name}
            onChange={(e) => set("name")(e.target.value)}
            placeholder="Harbour Point Basement Extension"
            autoFocus
          />
        </Field>

        <Field label="Description" htmlFor="description">
          <TextArea
            id="description"
            value={form.description}
            onChange={(e) => set("description")(e.target.value)}
            placeholder="Scope, deliverables, anything the team needs before starting."
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Customer"
            htmlFor="customer"
            hint={
              (customers?.items ?? []).length === 0
                ? "None on file yet — add the first one."
                : undefined
            }
          >
            <div className="flex items-center gap-2">
              <Select
                id="customer"
                className="flex-1"
                value={form.customer_id}
                onChange={(e) => set("customer_id")(e.target.value)}
                placeholder="Select a customer"
                options={(customers?.items ?? []).map((c) => ({
                  value: c.id,
                  label: `${c.name} (${c.customer_code})`,
                }))}
              />
              {/* A project needs a customer, so discovering there are none
                  must not mean abandoning the half-filled form. */}
              <Link
                to="/catalogue"
                className="btn-secondary shrink-0 px-2"
                title="Add a customer"
                aria-label="Add a customer"
              >
                <Plus className="h-4 w-4" />
              </Link>
            </div>
          </Field>

          <Field
            label="Product"
            htmlFor="product"
            hint="Determines which design templates are suggested."
          >
            <Select
              id="product"
              value={form.product_id}
              onChange={(e) => set("product_id")(e.target.value)}
              placeholder="Select a product"
              options={(products ?? []).map((p) => ({ value: p.id, label: p.name }))}
            />
          </Field>

          <Field
            label="Project type"
            htmlFor="project_type"
            hint={
              form.project_type && !typeOptions.includes(form.project_type)
                ? "This project predates the current list. Leaving it alone keeps it as it is."
                : undefined
            }
          >
            <Select
              id="project_type"
              value={form.project_type}
              onChange={(e) => set("project_type")(e.target.value)}
              placeholder="Choose a project type"
              options={[
                ...typeOptions.map((v) => ({ value: v, label: v })),
                // A value the vocabulary no longer offers is still the truth
                // about this project. Dropping it from the list would blank the
                // control and quietly rewrite the field on the next save.
                ...(form.project_type && !typeOptions.includes(form.project_type)
                  ? [{ value: form.project_type, label: `${form.project_type} (retired)` }]
                  : []),
              ]}
            />
          </Field>

          <Field label="Priority" htmlFor="priority">
            <Select
              id="priority"
              value={form.priority}
              onChange={(e) => set("priority")(e.target.value)}
              options={toOptions(PRIORITIES)}
            />
          </Field>

          <Field
            label="Team lead"
            htmlFor="team_lead"
            hint="The one person driving this project."
            required
          >
            <Select
              id="team_lead"
              value={form.team_lead_id}
              onChange={(e) => set("team_lead_id")(e.target.value)}
              placeholder="Unassigned"
              options={(leads?.items ?? []).map((u) => ({
                value: u.id,
                label: u.full_name,
              }))}
            />
          </Field>

          <Field label="Sales order" htmlFor="sales_order">
            <TextInput
              id="sales_order"
              value={form.sales_order}
              onChange={(e) => set("sales_order")(e.target.value)}
              placeholder="SO-2026-0142"
            />
          </Field>

          <Field label="Work order" htmlFor="work_order">
            <TextInput
              id="work_order"
              value={form.work_order}
              onChange={(e) => set("work_order")(e.target.value)}
              placeholder="WO-2026-0142"
            />
          </Field>

          <Field
            label="External ID"
            htmlFor="external_id"
            hint="Reserved for a future Salesforce record ID."
          >
            <TextInput
              id="external_id"
              value={form.external_id}
              onChange={(e) => set("external_id")(e.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-4 border-t border-ink-100 pt-4 sm:grid-cols-2">
          <Field label="Start date" htmlFor="start_date">
            <TextInput
              id="start_date"
              type="date"
              value={form.start_date}
              onChange={(e) => set("start_date")(e.target.value)}
            />
          </Field>

          <Field
            label="Required completion"
            htmlFor="required_completion_date"
            hint="Drives delay detection and project health."
          >
            <TextInput
              id="required_completion_date"
              type="date"
              value={form.required_completion_date}
              onChange={(e) => set("required_completion_date")(e.target.value)}
            />
          </Field>

          <Field label="Internal deadline" htmlFor="internal_deadline">
            <TextInput
              id="internal_deadline"
              type="date"
              value={form.internal_deadline}
              onChange={(e) => set("internal_deadline")(e.target.value)}
            />
          </Field>

          <Field label="Customer deadline" htmlFor="customer_deadline">
            <TextInput
              id="customer_deadline"
              type="date"
              value={form.customer_deadline}
              onChange={(e) => set("customer_deadline")(e.target.value)}
            />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
