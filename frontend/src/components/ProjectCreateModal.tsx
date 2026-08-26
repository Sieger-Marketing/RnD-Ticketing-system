import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/primitives";
import {
  useCreateProject,
  useCustomers,
  useProducts,
  useUsers,
  useVocabularies,
} from "@/hooks/queries";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { ProjectDetail } from "@/types/api";

const EMPTY = {
  name: "",
  description: "",
  customer_id: "",
  product_id: "",
  project_type: "",
  sales_order: "",
  work_order: "",
  design_manager_id: "",
  team_lead_id: "",
  priority: "Medium",
  start_date: "",
  required_completion_date: "",
  internal_deadline: "",
  customer_deadline: "",
  external_id: "",
};

export function ProjectCreateModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (project: ProjectDetail) => void;
}) {
  const [form, setForm] = useState(EMPTY);
  const create = useCreateProject();

  const { data: customers } = useCustomers();
  const { data: products } = useProducts();
  const { data: managers } = useUsers({ role: "Design Manager" });
  const { data: leads } = useUsers({ role: "Team Lead" });
  const { data: vocab } = useVocabularies();

  const set = (key: keyof typeof EMPTY) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const close = () => {
    create.reset();
    setForm(EMPTY);
    onClose();
  };

  const submit = () => {
    // Blank strings would fail the API's UUID and date parsing, so they are
    // dropped rather than sent as "".
    const payload: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(form)) {
      if (value !== "") payload[key] = value;
    }
    create.mutate(payload, {
      onSuccess: (project) => {
        setForm(EMPTY);
        onCreated(project);
      },
    });
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="New project"
      description="A project holds the design releases for one customer deliverable."
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
            disabled={create.isPending || form.name.trim() === ""}
          >
            {create.isPending && <Spinner />}
            Create project
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError error={create.error} />

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

          <Field label="Project type" htmlFor="project_type">
            <Select
              id="project_type"
              value={form.project_type}
              onChange={(e) => set("project_type")(e.target.value)}
              placeholder="Choose a project type"
              options={(vocab?.project_types ?? []).map((v) => ({
                value: v,
                label: v,
              }))}
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

          <Field label="Design manager" htmlFor="design_manager">
            <Select
              id="design_manager"
              value={form.design_manager_id}
              onChange={(e) => set("design_manager_id")(e.target.value)}
              placeholder="Unassigned"
              options={(managers?.items ?? []).map((u) => ({
                value: u.id,
                label: u.full_name,
              }))}
            />
          </Field>

          <Field
            label="Team lead"
            htmlFor="team_lead"
            hint="Who runs the design work. Can be set later."
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
