/**
 * Design release detail — where the workflow in spec section 47 is driven:
 * assign a lead, accept, generate tasks from a template, then complete.
 */

import { AlertTriangle, ArrowLeft, Check, Sparkles, UserPlus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { TaskTable } from "@/components/TaskTable";
import { Field, FormError, Select, TextArea } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Card,
  ErrorState,
  HealthPill,
  InlineAlert,
  KpiCard,
  PageHeader,
  PriorityLabel,
  SkeletonRows,
  Spinner,
  Stat,
  StatusBadge,
  toneFor,
} from "@/components/ui/primitives";
import {
  useAcceptRelease,
  useApplyTemplate,
  useAssignLead,
  useCompleteRelease,
  useCompletionBlockers,
  useRelease,
  useReleaseTasks,
  useSuggestedTemplate,
  useUsers,
} from "@/hooks/queries";
import { DASH, hours, percent, shortDate, variance } from "@/lib/format";
import { P, useAuth } from "@/store/auth";

export default function ReleaseDetail() {
  const { releaseId = "" } = useParams<{ releaseId: string }>();
  const navigate = useNavigate();
  const { can, user } = useAuth();

  const [assigning, setAssigning] = useState(false);
  const [leadId, setLeadId] = useState("");
  const [completing, setCompleting] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");

  const release = useRelease(releaseId);
  const tasks = useReleaseTasks(releaseId);
  const suggestion = useSuggestedTemplate(releaseId);
  const blockers = useCompletionBlockers(releaseId);
  const { data: leads } = useUsers({ role: "Team Lead" });

  const assignLead = useAssignLead(releaseId);
  const accept = useAcceptRelease(releaseId);
  const applyTemplate = useApplyTemplate(releaseId);
  const complete = useCompleteRelease(releaseId);

  if (release.isLoading) {
    return (
      <>
        <PageHeader title="Release" />
        <div className="card">
          <SkeletonRows rows={7} />
        </div>
      </>
    );
  }

  if (release.isError || !release.data) {
    return (
      <div className="card">
        <ErrorState
          title="Could not load this release"
          message={release.error instanceof Error ? release.error.message : undefined}
          onRetry={() => void release.refetch()}
        />
      </div>
    );
  }

  const r = release.data;
  const taskList = tasks.data ?? [];
  const isMyRelease = r.team_lead_id === user?.id;
  const canComplete = blockers.data?.can_complete_cleanly ?? false;
  const blockingTasks = blockers.data?.blocking_tasks ?? [];
  const isFinished = r.status === "Completed" || r.status === "Cancelled";

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Link
          to="/releases"
          className="inline-flex items-center gap-1 text-xs text-ink-500 hover:text-ink-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          All releases
        </Link>
        <Link
          to={`/projects/${r.project_id}`}
          className="text-xs text-brand-600 hover:underline"
        >
          {r.project_code} · {r.project_name}
        </Link>
      </div>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {r.name}
            <StatusBadge status={r.status} />
            <HealthPill health={r.health} />
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono">{r.code}</span>
            <span>{r.release_type}</span>
            <PriorityLabel priority={r.priority} />
            <span>
              {shortDate(r.planned_start)} → {shortDate(r.planned_end)}
            </span>
            {r.delay_days > 0 && (
              <span className="font-medium text-rag-red">{r.delay_days} days late</span>
            )}
          </span>
        }
        actions={
          <>
            {can(P.releaseAssignLead) && !isFinished && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setLeadId(r.team_lead_id ?? "");
                  setAssigning(true);
                }}
              >
                <UserPlus className="h-4 w-4" />
                {r.team_lead_id ? "Reassign lead" : "Assign lead"}
              </button>
            )}

            {can(P.releaseAccept) && isMyRelease && r.status === "Assigned" && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => accept.mutate()}
                disabled={accept.isPending}
              >
                {accept.isPending && <Spinner />}
                Accept release
              </button>
            )}

            {can(P.releaseComplete) && !isFinished && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  setOverrideReason("");
                  setCompleting(true);
                }}
              >
                <Check className="h-4 w-4" />
                Complete release
              </button>
            )}
          </>
        }
      />

      {accept.isError && (
        <div className="mb-3">
          <FormError error={accept.error} />
        </div>
      )}

      {r.health_reasons.length > 0 && (
        <div
          className={`mb-4 rounded-lg border-l-4 bg-white p-4 shadow-card ${
            r.health === "RED" ? "border-l-rag-red" : "border-l-rag-amber"
          }`}
        >
          <p className="mb-1.5 text-xs font-semibold text-ink-900">
            Why this release is {r.health}
          </p>
          <ul className="space-y-1">
            {r.health_reasons.map((reason, i) => (
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

      {r.completion_override_reason && (
        <div className="mb-4">
          <InlineAlert tone="warn">
            <span className="font-medium">Completed with an override.</span>{" "}
            {r.completion_override_reason}
          </InlineAlert>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard label="Completion" value={percent(r.completion_percent)} />
        <KpiCard
          label="Tasks"
          value={taskList.length}
          hint={`${taskList.filter((t) => t.status === "Completed").length} completed`}
        />
        <KpiCard
          label="Efficiency"
          value={percent(r.efficiency_percent)}
          tone={toneFor(r.efficiency_percent, { good: 95, warn: 85 })}
          hint={`${hours(r.estimated_hours)} vs ${hours(r.actual_hours)}`}
        />
        <KpiCard
          label="Effort variance"
          value={variance(r.effort_variance)}
          tone={(r.effort_variance ?? 0) > 0 ? "warn" : "good"}
        />
        <KpiCard
          label="Rework"
          value={hours(r.rework_hours)}
          hint={`${r.revision_count} revision${r.revision_count === 1 ? "" : "s"}`}
          tone={r.rework_hours > 0 ? "warn" : "good"}
        />
        <KpiCard
          label="Delay"
          value={r.delay_days > 0 ? `${r.delay_days}d` : "On time"}
          tone={r.delay_days > 0 ? "bad" : "good"}
          hint={r.delay_reason ?? undefined}
        />
      </div>

      {/* Task generation is offered only while the release has no tasks; after
          that, adding work is a per-task action so a template can never
          silently duplicate an existing plan. */}
      {taskList.length === 0 && can(P.templateApply) && !isFinished && (
        <Card className="mb-4" title="Generate standard tasks">
          {suggestion.isLoading && (
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <Spinner />
              Finding a matching template…
            </div>
          )}

          {suggestion.data?.suggested ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="flex items-center gap-1.5 text-sm font-medium text-ink-900">
                  <Sparkles className="h-3.5 w-3.5 text-brand-600" />
                  {suggestion.data.suggested.template_name} v
                  {suggestion.data.suggested.version_number}
                </p>
                <p className="mt-0.5 text-xs text-ink-500">
                  {suggestion.data.suggested.task_count} standard tasks ·{" "}
                  {suggestion.data.suggested.total_estimated_hours.toFixed(1)}h
                  estimated. The release keeps this version even after the
                  template is revised.
                </p>
              </div>
              <button
                type="button"
                className="btn-primary"
                onClick={() =>
                  applyTemplate.mutate(suggestion.data!.suggested!.version_id)
                }
                disabled={applyTemplate.isPending}
              >
                {applyTemplate.isPending && <Spinner />}
                Generate {suggestion.data.suggested.task_count} tasks
              </button>
            </div>
          ) : (
            suggestion.isFetched && (
              <p className="text-xs text-ink-500">
                No published template matches “{r.release_type}”. Add tasks by
                hand, or publish a matching template for this release type first.
              </p>
            )
          )}

          {applyTemplate.isError && (
            <div className="mt-3">
              <FormError error={applyTemplate.error} />
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title={`Tasks (${taskList.length})`}
          bodyClassName=""
        >
          {tasks.isLoading && <SkeletonRows rows={5} />}
          {tasks.data && (
            <TaskTable
              tasks={taskList}
              columns={[
                "code",
                "name",
                "assignee",
                "status",
                "priority",
                "due",
                "hours",
                "progress",
              ]}
              onSelect={(task) => navigate(`/tasks/${task.id}`)}
              emptyTitle="No tasks in this release"
              emptyDescription="Generate them from a template, or add them individually."
            />
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Release details">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="Sequence" value={r.sequence_number} />
              <Stat label="Type" value={r.release_type} />
              <Stat label="Team lead" value={r.team_lead_name ?? DASH} />
              <Stat label="Review status" value={r.review_status} />
              <Stat label="Planned start" value={shortDate(r.planned_start)} />
              <Stat label="Planned end" value={shortDate(r.planned_end)} />
              <Stat label="Actual start" value={shortDate(r.actual_start)} />
              <Stat label="Actual end" value={shortDate(r.actual_end)} />
            </dl>

            {r.template_name && (
              <div className="mt-4 border-t border-ink-100 pt-3">
                <p className="text-2xs uppercase tracking-wide text-ink-500">
                  Generated from
                </p>
                <p className="mt-0.5 text-xs text-ink-800">
                  {r.template_name} · {r.template_version_label}
                </p>
                <p className="mt-1 text-2xs text-ink-400">
                  Pinned at creation. Later template revisions do not change this
                  release.
                </p>
              </div>
            )}

            {r.description && (
              <p className="mt-4 border-t border-ink-100 pt-3 text-xs leading-relaxed text-ink-600">
                {r.description}
              </p>
            )}
          </Card>

          {!isFinished && blockingTasks.length > 0 && (
            <Card title="Blocking completion">
              <p className="mb-2 text-xs text-ink-600">
                These mandatory tasks are not finished. Completing the release now
                requires a manager override, which is recorded in the audit log.
              </p>
              <ul className="space-y-1.5">
                {blockingTasks.map((task) => (
                  <li key={task.code} className="flex items-start gap-1.5">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-rag-amber" />
                    <span className="text-xs text-ink-800">
                      {task.name}{" "}
                      <span className="text-ink-400">({task.status})</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={assigning}
        onClose={() => setAssigning(false)}
        title="Assign team lead"
        description="The lead breaks the release into tasks and assigns designers."
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setAssigning(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                assignLead.mutate(leadId, { onSuccess: () => setAssigning(false) })
              }
              disabled={!leadId || assignLead.isPending}
            >
              {assignLead.isPending && <Spinner />}
              Assign
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={assignLead.error} />
          <Field label="Team lead" htmlFor="lead" required>
            <Select
              id="lead"
              value={leadId}
              onChange={(e) => setLeadId(e.target.value)}
              placeholder="Select a team lead"
              options={(leads?.items ?? []).map((u) => ({
                value: u.id,
                label: u.full_name,
              }))}
            />
          </Field>
        </div>
      </Modal>

      <Modal
        open={completing}
        onClose={() => setCompleting(false)}
        title="Complete release"
        description={
          canComplete
            ? "All mandatory tasks are finished."
            : "Mandatory tasks are still open."
        }
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setCompleting(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={canComplete ? "btn-primary" : "btn-danger"}
              onClick={() =>
                complete.mutate(overrideReason || undefined, {
                  onSuccess: () => setCompleting(false),
                })
              }
              disabled={
                complete.isPending ||
                (!canComplete && overrideReason.trim().length < 5)
              }
            >
              {complete.isPending && <Spinner />}
              {canComplete ? "Complete release" : "Override and complete"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={complete.error} />

          {canComplete ? (
            <InlineAlert tone="success">
              Every mandatory task is complete. Finishing the release will roll its
              hours and completion up to the project.
            </InlineAlert>
          ) : (
            <>
              <InlineAlert tone="warn">
                {blockingTasks.length} mandatory task
                {blockingTasks.length === 1 ? " is" : "s are"} not complete. An
                override is recorded against your name in the audit log with the
                reason you give below.
              </InlineAlert>

              <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md bg-ink-50 p-2">
                {blockingTasks.map((task) => (
                  <li key={task.code} className="text-2xs text-ink-700">
                    <span className="font-mono">{task.code}</span> {task.name} —{" "}
                    {task.status}
                  </li>
                ))}
              </ul>

              <Field
                label="Override reason"
                htmlFor="override"
                required
                hint="At least a few words. This is permanent."
              >
                <TextArea
                  id="override"
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Customer accepted the partial scope; remaining checks moved to DR-005."
                />
              </Field>
            </>
          )}
        </div>
      </Modal>
    </>
  );
}
