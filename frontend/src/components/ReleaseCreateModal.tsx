/**
 * Create a design release, choosing the product template that generates its
 * standard tasks (spec sections 8, 9 and 47 steps 3-5).
 */

import { useQuery } from "@tanstack/react-query";
import { Check, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import {
  useCreateRelease,
  useProducts,
  useUsers,
  useVocabularies,
} from "@/hooks/queries";
import { get } from "@/lib/api";
import { PRIORITIES, toOptions } from "@/lib/vocab";
import type { ReleaseDetail } from "@/types/api";

interface MatchResponse {
  suggested_version_id: string | null;
  suggested_template: string | null;
  matches: {
    id: string;
    name: string;
    release_type: string;
    current_version_number: number | null;
    versions: {
      id: string;
      version_number: number;
      label: string;
      is_published: boolean;
      task_count: number;
      total_estimated_hours: number;
    }[];
  }[];
}

const EMPTY = {
  name: "",
  release_type: "",
  description: "",
  product_id: "",
  team_lead_id: "",
  priority: "Medium",
  planned_start: "",
  planned_end: "",
};

export function ReleaseCreateModal({
  open,
  projectId,
  productId,
  onClose,
  onCreated,
}: {
  open: boolean;
  projectId: string;
  productId: string | null;
  onClose: () => void;
  onCreated: (release: ReleaseDetail) => void;
}) {
  const [form, setForm] = useState({ ...EMPTY, product_id: productId ?? "" });
  const [versionId, setVersionId] = useState<string>("");
  const [touchedTemplate, setTouchedTemplate] = useState(false);

  const create = useCreateRelease();
  const { data: products } = useProducts();
  const { data: leads } = useUsers({ role: "Team Lead" });
  const { data: vocab } = useVocabularies();

  const set = (key: keyof typeof EMPTY) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Ask the server which template it would suggest. Matching lives in the
  // backend so the same rule applies however a release is created.
  const releaseType = form.release_type.trim();
  const match = useQuery({
    queryKey: ["template-match", releaseType, form.product_id],
    queryFn: () =>
      get<MatchResponse>("/api/templates/match", {
        release_type: releaseType,
        product_id: form.product_id || undefined,
      }),
    enabled: open && releaseType.length > 0,
  });

  // Preselect the suggestion, but stop overriding once the user has chosen.
  useEffect(() => {
    if (!touchedTemplate && match.data?.suggested_version_id) {
      setVersionId(match.data.suggested_version_id);
    }
  }, [match.data?.suggested_version_id, touchedTemplate]);

  const close = () => {
    create.reset();
    setForm({ ...EMPTY, product_id: productId ?? "" });
    setVersionId("");
    setTouchedTemplate(false);
    onClose();
  };

  const submit = () => {
    const payload: Record<string, unknown> = { project_id: projectId };
    for (const [key, value] of Object.entries(form)) {
      if (value !== "") payload[key] = value;
    }
    if (versionId) payload.template_version_id = versionId;

    create.mutate(payload, {
      onSuccess: (release) => {
        close();
        onCreated(release);
      },
    });
  };

  const publishedVersions = (match.data?.matches ?? []).flatMap((template) =>
    template.versions
      .filter((v) => v.is_published)
      .map((v) => ({ template: template.name, ...v })),
  );

  const chosen = publishedVersions.find((v) => v.id === versionId);

  return (
    <Modal
      open={open}
      onClose={close}
      title="New design release"
      description="Selecting a template generates its standard tasks immediately. The Team Lead can then add, remove or re-estimate them."
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
              create.isPending || form.name.trim() === "" || releaseType === ""
            }
          >
            {create.isPending && <Spinner />}
            Create release
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError error={create.error} />

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Release name" htmlFor="rname" required className="sm:col-span-2">
            <TextInput
              id="rname"
              value={form.name}
              onChange={(e) => set("name")(e.target.value)}
              placeholder="DR-002 Mechanical Design"
              autoFocus
            />
          </Field>

          <Field
            label="Release type"
            htmlFor="rtype"
            required
            hint="Matched against the template library."
          >
            <Select
              id="rtype"
              value={form.release_type}
              onChange={(e) => {
                set("release_type")(e.target.value);
                setTouchedTemplate(false);
              }}
              placeholder="Choose a release type"
              options={(vocab?.release_types ?? []).map((v) => ({
                value: v,
                label: v,
              }))}
            />
          </Field>

          <Field label="Product" htmlFor="rproduct">
            <Select
              id="rproduct"
              value={form.product_id}
              onChange={(e) => {
                set("product_id")(e.target.value);
                setTouchedTemplate(false);
              }}
              placeholder="Inherit from project"
              options={(products ?? []).map((p) => ({ value: p.id, label: p.name }))}
            />
          </Field>

          <Field label="Team lead" htmlFor="rlead">
            <Select
              id="rlead"
              value={form.team_lead_id}
              onChange={(e) => set("team_lead_id")(e.target.value)}
              placeholder="Assign later"
              options={(leads?.items ?? []).map((u) => ({
                value: u.id,
                label: u.full_name,
              }))}
            />
          </Field>

          <Field label="Priority" htmlFor="rpriority">
            <Select
              id="rpriority"
              value={form.priority}
              onChange={(e) => set("priority")(e.target.value)}
              options={toOptions(PRIORITIES)}
            />
          </Field>

          <Field label="Planned start" htmlFor="rstart">
            <TextInput
              id="rstart"
              type="date"
              value={form.planned_start}
              onChange={(e) => set("planned_start")(e.target.value)}
            />
          </Field>

          <Field label="Planned end" htmlFor="rend">
            <TextInput
              id="rend"
              type="date"
              value={form.planned_end}
              onChange={(e) => set("planned_end")(e.target.value)}
            />
          </Field>

          <Field label="Description" htmlFor="rdesc" className="sm:col-span-2">
            <TextArea
              id="rdesc"
              value={form.description}
              onChange={(e) => set("description")(e.target.value)}
              rows={2}
            />
          </Field>
        </div>

        <div className="border-t border-ink-100 pt-4">
          <p className="label">Design template</p>

          {releaseType === "" && (
            <p className="text-xs text-ink-500">
              Enter a release type to see matching templates.
            </p>
          )}

          {releaseType !== "" && match.isLoading && (
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <Spinner />
              Looking for a matching template…
            </div>
          )}

          {releaseType !== "" && match.data && publishedVersions.length === 0 && (
            <InlineAlert tone="info">
              No published template matches “{releaseType}”
              {form.product_id ? " for this product" : ""}. The release will be
              created with no tasks, and the Team Lead can add them by hand.
            </InlineAlert>
          )}

          {publishedVersions.length > 0 && (
            <div className="space-y-1.5">
              {publishedVersions.map((version) => {
                const isSuggested = version.id === match.data?.suggested_version_id;
                const isSelected = version.id === versionId;
                return (
                  <button
                    key={version.id}
                    type="button"
                    onClick={() => {
                      setTouchedTemplate(true);
                      setVersionId(isSelected ? "" : version.id);
                    }}
                    className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors ${
                      isSelected
                        ? "border-signal-500 bg-signal-50"
                        : "border-ink-200 hover:bg-ink-50"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-xs font-medium text-ink-900">
                        {version.template}
                        <span className="font-normal text-ink-500">{version.label}</span>
                        {isSuggested && (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-signal-100 px-1.5 py-0.5 text-2xs font-medium text-signal-700">
                            <Sparkles className="h-2.5 w-2.5" />
                            suggested
                          </span>
                        )}
                      </p>
                      <p className="text-2xs text-ink-500">
                        {version.task_count} standard task
                        {version.task_count === 1 ? "" : "s"} ·{" "}
                        {version.total_estimated_hours.toFixed(1)}h estimated
                      </p>
                    </div>
                    {isSelected && (
                      <Check className="h-4 w-4 shrink-0 text-signal-700" />
                    )}
                  </button>
                );
              })}

              <p className="pt-1 text-2xs text-ink-500">
                {chosen
                  ? `${chosen.task_count} tasks will be generated from ${chosen.template} ${chosen.label}. The release keeps this version even after the template is revised.`
                  : "No template selected — the release will start with no tasks."}
              </p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
