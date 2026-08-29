/**
 * The per-project dashboard (spec section 26).
 */

import { ArrowLeft, Check, GitBranch, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { type ChangeEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { RecordLink } from "@/components/RecordLink";
import { DeleteEntityDialog } from "@/components/DeleteEntityDialog";
import { ProjectCreateModal } from "@/components/ProjectCreateModal";
import { ApplyStandardModal } from "@/components/ApplyStandardModal";
import { ReleaseCreateModal } from "@/components/ReleaseCreateModal";
import { ReleaseTimeline, type TimelineRelease } from "@/components/ReleaseTimeline";
import { Select } from "@/components/ui/form";
import {
  Card,
  ErrorState,
  HealthPill,
  KpiCard,
  PageHeader,
  PriorityLabel,
  ProgressBar,
  SkeletonRows,
  Spinner,
  Stat,
  StatusBadge,
  toneFor,
} from "@/components/ui/primitives";
import {
  useDeleteProject,
  useProject,
  useProjectDashboard,
  useProjectDeletionImpact,
  useReleases,
  useUpdateProject,
  useUsers,
} from "@/hooks/queries";
import { DASH, hours, percent, shortDate, variance } from "@/lib/format";
import { P, useAuth } from "@/store/auth";
import type {
  Health,
  HealthReason,
  ProjectDetail as ProjectDetailData,
} from "@/types/api";

interface ProjectDashboard {
  project: {
    id: string;
    code: string;
    name: string;
    status: string;
    health: Health;
    health_reasons: HealthReason[];
    completion_percent: number;
    planned_hours: number;
    actual_hours: number;
    rework_hours: number;
    revision_count: number;
    delay_days: number;
    efficiency_percent: number | null;
    rework_percent: number | null;
    on_time_percent: number | null;
  };
  release_counts: {
    total: number;
    completed: number;
    in_progress: number;
    pending: number;
    overdue: number;
  };
  task_counts: {
    total: number;
    completed: number;
    open: number;
    overdue: number;
    blocked: number;
  };
  timeline: TimelineRelease[];
  resource_allocation: {
    user_id: string;
    full_name: string | null;
    tasks: number;
    estimated_hours: number;
    actual_hours: number;
  }[];
}

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const can = useAuth((s) => s.can);
  const [creatingRelease, setCreatingRelease] = useState(false);
  const [applyingStandard, setApplyingStandard] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const deletionImpact = useProjectDeletionImpact(projectId, deleting);
  const deleteProject = useDeleteProject();

  const project = useProject(projectId);
  const dashboard = useProjectDashboard(projectId);
  const releases = useReleases({ project_id: projectId, page_size: 100 });

  if (project.isLoading || dashboard.isLoading) {
    return (
      <>
        <PageHeader title="Project" />
        <div className="card">
          <SkeletonRows rows={8} />
        </div>
      </>
    );
  }

  if (project.isError || !project.data) {
    return (
      <div className="card">
        <ErrorState
          title="Could not load this project"
          message={project.error instanceof Error ? project.error.message : undefined}
          onRetry={() => void project.refetch()}
        />
      </div>
    );
  }

  const p = project.data;
  const d = dashboard.data as ProjectDashboard | undefined;

  return (
    <>
      <Link
        to="/projects"
        className="mb-3 inline-flex items-center gap-1 text-xs text-ink-500 hover:text-ink-800"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All projects
      </Link>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {p.name}
            <StatusBadge status={p.status} />
            <HealthPill health={p.health} />
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono">{p.code}</span>
            <span>{p.customer_name ?? "No customer"}</span>
            <span>{p.product_name ?? "No product"}</span>
            <PriorityLabel priority={p.priority} />
            {p.delay_days > 0 && (
              <span className="font-medium text-rag-red">
                {p.delay_days} day{p.delay_days === 1 ? "" : "s"} late
              </span>
            )}
          </span>
        }
        actions={
          <>
            {can(P.projectUpdate) && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setEditing(true)}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </button>
            )}
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                void project.refetch();
                void dashboard.refetch();
              }}
              title="Recompute rollups from the underlying tasks"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
            {can(P.releaseCreate) && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setApplyingStandard(true)}
                title="Create this product's standard design releases"
              >
                <GitBranch className="h-4 w-4" />
                Apply standard
              </button>
            )}
            {can(P.releaseCreate) && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => setCreatingRelease(true)}
              >
                <Plus className="h-4 w-4" />
                New release
              </button>
            )}
            {/* Administrator and Design Manager only. A Team Lead cancels a
                project instead, which keeps its history. */}
            {can(P.projectDelete) && (
              <button
                type="button"
                className="btn-ghost text-rag-red"
                onClick={() => {
                  deleteProject.reset();
                  setDeleting(true);
                }}
                title="Permanently delete this project and everything under it"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            )}
          </>
        }
      />

      {p.health_reasons.length > 0 && (
        <div
          className={`mb-4 rounded-lg border-l-4 bg-white p-4 shadow-card ${
            p.health === "RED" ? "border-l-rag-red" : "border-l-rag-amber"
          }`}
        >
          <p className="mb-1.5 text-xs font-semibold text-ink-900">
            Why this project is {p.health}
          </p>
          <ul className="space-y-1">
            {p.health_reasons.map((reason, i) => (
              <li
                key={i}
                className={`text-xs ${
                  reason.level === "RED" ? "text-rag-red" : "text-rag-amber"
                }`}
              >
                • {reason.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard
          label="Completion"
          value={percent(p.completion_percent)}
          hint={`${d?.task_counts.completed ?? 0} of ${d?.task_counts.total ?? 0} tasks`}
        />
        <KpiCard
          label="Releases"
          value={`${d?.release_counts.completed ?? 0}/${d?.release_counts.total ?? 0}`}
          hint={`${d?.release_counts.overdue ?? 0} overdue`}
          tone={(d?.release_counts.overdue ?? 0) > 0 ? "warn" : "neutral"}
        />
        <KpiCard
          label="Efficiency"
          value={percent(d?.project.efficiency_percent)}
          tone={toneFor(d?.project.efficiency_percent, { good: 95, warn: 85 })}
          hint={`${hours(p.planned_hours)} vs ${hours(p.actual_hours)}`}
        />
        <KpiCard
          label="Effort variance"
          value={variance(p.actual_hours - p.planned_hours)}
          tone={p.actual_hours > p.planned_hours ? "warn" : "good"}
        />
        <KpiCard
          label="Rework"
          value={percent(d?.project.rework_percent)}
          tone={toneFor(d?.project.rework_percent, {
            good: 5,
            warn: 10,
            higherIsBetter: false,
          })}
          hint={`${hours(p.rework_hours)} · ${p.revision_count} revision${
            p.revision_count === 1 ? "" : "s"
          }`}
        />
        <KpiCard
          label="Overdue tasks"
          value={d?.task_counts.overdue ?? 0}
          tone={(d?.task_counts.overdue ?? 0) > 0 ? "bad" : "good"}
          hint={`${d?.task_counts.blocked ?? 0} blocked`}
        />
      </div>

      <Card className="mb-4" title="Release timeline">
        <ReleaseTimeline
          releases={d?.timeline ?? []}
          onSelect={(releaseId) => navigate(`/releases/${releaseId}`)}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Design releases" bodyClassName="">
          {releases.isLoading && <SkeletonRows rows={4} />}
          {releases.data && releases.data.items.length === 0 && (
            <div className="px-4 py-10 text-center">
              <p className="text-sm text-ink-600">No releases yet.</p>
              <p className="mt-1 text-xs text-ink-500">
                A release is one design stage — concept, mechanical, drawings, BOM.
              </p>
              {can(P.releaseCreate) && (
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setApplyingStandard(true)}
                  >
                    <GitBranch className="h-4 w-4" />
                    Apply the {p.product_name ?? "product"} standard
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setCreatingRelease(true)}
                  >
                    Create one release
                  </button>
                </div>
              )}
            </div>
          )}
          {releases.data && releases.data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px]">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">#</th>
                    <th className="th">Release</th>
                    <th className="th">Team lead</th>
                    <th className="th">Status</th>
                    <th className="th w-32">Progress</th>
                    <th className="th text-right">Est / Act</th>
                    <th className="th">Due</th>
                    <th className="th">Health</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {releases.data.items.map((release) => (
                    <tr
                      key={release.id}
                      className="cursor-pointer hover:bg-ink-50"
                      onClick={() => navigate(`/releases/${release.id}`)}
                    >
                      <td className="td text-2xs text-ink-400">
                        {release.sequence_number}
                      </td>
                      <td className="td max-w-[16rem]">
                        <RecordLink
                          kind="release"
                          id={release.id}
                          className="block truncate font-medium text-ink-900"
                        >
                          {release.name}
                        </RecordLink>
                        <div className="font-mono text-2xs text-ink-400">
                          {release.code} · {release.task_count} task
                          {release.task_count === 1 ? "" : "s"}
                        </div>
                      </td>
                      <td className="td text-xs text-ink-600">
                        {release.team_lead_name ?? (
                          <span className="text-rag-amber">Unassigned</span>
                        )}
                      </td>
                      <td className="td">
                        <StatusBadge status={release.status} />
                      </td>
                      <td className="td">
                        <ProgressBar
                          value={release.completion_percent}
                          tone={
                            release.health === "RED"
                              ? "red"
                              : release.health === "AMBER"
                                ? "amber"
                                : "neutral"
                          }
                        />
                      </td>
                      <td className="td text-right text-xs tabular text-ink-600">
                        {hours(release.estimated_hours)} / {hours(release.actual_hours)}
                      </td>
                      <td className="td text-xs">
                        <span
                          className={
                            release.delay_days > 0
                              ? "font-medium text-rag-red"
                              : "text-ink-600"
                          }
                        >
                          {shortDate(release.planned_end)}
                        </span>
                      </td>
                      <td className="td">
                        <HealthPill health={release.health} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Project details">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="Customer" value={p.customer_name ?? DASH} />
              <Stat label="Product" value={p.product_name ?? DASH} />
              <Stat
                label="Car spaces"
                value={p.car_count ? p.car_count.toLocaleString() : DASH}
              />
              <Stat label="GFC date" value={shortDate(p.gfc_date)} />
              <Stat label="Type" value={p.project_type ?? DASH} />
              <Stat label="Team lead" value={<TeamLeadPicker project={p} />} />
              <Stat label="Sales order" value={p.sales_order ?? DASH} />
              <Stat label="Work order" value={p.work_order ?? DASH} />
              <Stat label="Start" value={shortDate(p.start_date)} />
              <Stat label="Required by" value={shortDate(p.required_completion_date)} />
              <Stat label="Internal deadline" value={shortDate(p.internal_deadline)} />
              <Stat label="Customer deadline" value={shortDate(p.customer_deadline)} />
            </dl>
            {p.description && (
              <p className="mt-4 border-t border-ink-100 pt-3 text-xs leading-relaxed text-ink-600">
                {p.description}
              </p>
            )}
          </Card>

          <Card title="Resource allocation" bodyClassName="">
            {(d?.resource_allocation.length ?? 0) === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-ink-500">
                No time logged against this project yet.
              </p>
            ) : (
              <table className="w-full">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">Designer</th>
                    <th className="th text-right">Tasks</th>
                    <th className="th text-right">Est</th>
                    <th className="th text-right">Act</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {d?.resource_allocation.map((row) => (
                    <tr key={row.user_id}>
                      <td className="td text-xs">{row.full_name ?? DASH}</td>
                      <td className="td text-right text-xs tabular">{row.tasks}</td>
                      <td className="td text-right text-xs tabular text-ink-500">
                        {hours(row.estimated_hours)}
                      </td>
                      <td
                        className={`td text-right text-xs tabular ${
                          row.actual_hours > row.estimated_hours
                            ? "font-medium text-rag-amber"
                            : "text-ink-800"
                        }`}
                      >
                        {hours(row.actual_hours)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>

      <ProjectCreateModal
        open={editing}
        project={p}
        onClose={() => setEditing(false)}
        onCreated={() => {
          setEditing(false);
          void project.refetch();
        }}
      />

      {projectId && applyingStandard && (
        <ApplyStandardModal
          open
          projectId={projectId}
          productId={p.product_id}
          productName={p.product_name}
          onClose={() => setApplyingStandard(false)}
          onApplied={() => setApplyingStandard(false)}
        />
      )}

      {projectId && creatingRelease && (
        <ReleaseCreateModal
          open
          projectId={projectId}
          productId={p.product_id}
          onClose={() => setCreatingRelease(false)}
          onCreated={(release) => {
            setCreatingRelease(false);
            navigate(`/releases/${release.id}`);
          }}
        />
      )}

      <DeleteEntityDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        entityLabel="project"
        code={p.code}
        name={p.name}
        impact={deletionImpact.data}
        impactLoading={deletionImpact.isLoading}
        isPending={deleteProject.isPending}
        error={deleteProject.error}
        onConfirm={() =>
          projectId &&
          deleteProject.mutate(projectId, {
            // The project no longer exists, so staying on its page would only
            // render a 404 once the queries refetch.
            onSuccess: () => {
              setDeleting(false);
              navigate("/projects", { replace: true });
            },
          })
        }
      />
    </>
  );
}

/**
 * Assign or reassign the team lead, in place.
 *
 * Everything else on this card is read-only, and a whole edit form for one
 * field would be ceremony -- reassigning a lead is a single decision, usually
 * made while looking at the project rather than while editing it. So it saves
 * on change and says so, and falls back to plain text for anyone without
 * permission to change it rather than showing a control that would be refused.
 */
function TeamLeadPicker({ project }: { project: ProjectDetailData }) {
  const can = useAuth((state) => state.can);
  const { data: leads } = useUsers({ role: "Team Lead" });
  const update = useUpdateProject(project.id);
  const [saved, setSaved] = useState(false);

  if (!can(P.projectUpdate)) {
    return <>{project.team_lead_name ?? DASH}</>;
  }

  const assign = (value: string) => {
    setSaved(false);
    update.mutate(
      // Clearing the field has to send null: an omitted key means "leave it
      // alone", so "Unassigned" would silently do nothing.
      { team_lead_id: value === "" ? null : value },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <div className="flex items-center gap-2">
      <Select
        aria-label="Team lead"
        className="py-1 text-sm font-normal"
        value={project.team_lead_id ?? ""}
        disabled={update.isPending}
        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
          assign(event.target.value)
        }
        placeholder="Unassigned"
        options={(leads?.items ?? []).map((u) => ({
          value: u.id,
          label: u.full_name,
        }))}
      />
      {update.isPending && <Spinner className="h-3.5 w-3.5 shrink-0" />}
      {saved && !update.isPending && (
        <Check className="h-3.5 w-3.5 shrink-0 text-rag-green" />
      )}
      {update.isError && (
        <span className="text-2xs text-rag-red">not saved</span>
      )}
    </div>
  );
}
