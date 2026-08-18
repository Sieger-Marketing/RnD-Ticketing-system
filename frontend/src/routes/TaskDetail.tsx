/**
 * Task detail: the screen a designer actually works from, and where a Team
 * Lead assigns, re-estimates and manages dependencies (spec sections 10-11).
 *
 * Available actions come from the API's `allowed_transitions`, so the buttons
 * on screen are exactly the moves the state machine will accept.
 */

import { AlertTriangle, ArrowLeft, Link2, Play, Send, Square, Trash2, UserPlus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { AssigneePicker } from "@/components/AssigneePicker";
import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Card,
  ErrorState,
  InlineAlert,
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
  useAssignTask,
  useDelayReasons,
  useEstimateTask,
  useLogTime,
  useMoveTask,
  useRemoveDependency,
  useRunningTimer,
  useStartTimer,
  useStopTimer,
  useSubmitForReview,
  useTask,
  useTimeEntries,
} from "@/hooks/queries";
import { DASH, dateTime, durationHours, hours, percent, shortDate, variance } from "@/lib/format";
import { P, useAuth } from "@/store/auth";
import type { TaskStatus } from "@/types/api";

/** Transitions worth a dedicated button, in the order a designer meets them. */
const PRIMARY_ACTIONS: { status: TaskStatus; label: string; icon?: ReactNode }[] = [
  { status: "In Progress", label: "Start work", icon: <Play className="h-3.5 w-3.5" /> },
  { status: "Blocked", label: "Raise blocker", icon: <AlertTriangle className="h-3.5 w-3.5" /> },
  { status: "Completed", label: "Mark complete" },
];

export default function TaskDetail() {
  const { taskId = "" } = useParams<{ taskId: string }>();
  const { can, user } = useAuth();

  const [assigning, setAssigning] = useState(false);
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [estimateHours, setEstimateHours] = useState("");
  const [estimateReason, setEstimateReason] = useState("");
  const [blocking, setBlocking] = useState(false);
  const [blockerNote, setBlockerNote] = useState("");
  const [delayReason, setDelayReason] = useState("");
  const [loggingTime, setLoggingTime] = useState(false);
  const [timeForm, setTimeForm] = useState({ entry_date: "", hours: "", description: "" });
  const [submitting, setSubmitting] = useState(false);
  const [submitNote, setSubmitNote] = useState("");
  const [submitDelayReason, setSubmitDelayReason] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);

  const task = useTask(taskId);
  const entries = useTimeEntries({ task_id: taskId, page_size: 50 });
  const running = useRunningTimer();
  const { data: delayReasonRows } = useDelayReasons();

  const move = useMoveTask();
  const assign = useAssignTask(taskId);
  const estimate = useEstimateTask(taskId);
  const startTimer = useStartTimer();
  const stopTimer = useStopTimer();
  const logTime = useLogTime();
  const submitReview = useSubmitForReview();
  const removeDependency = useRemoveDependency(taskId);

  const delayReasons = delayReasonRows ?? [];

  if (task.isLoading) {
    return (
      <>
        <PageHeader title="Task" />
        <div className="card">
          <SkeletonRows rows={6} />
        </div>
      </>
    );
  }

  if (task.isError || !task.data) {
    return (
      <div className="card">
        <ErrorState
          title="Could not load this task"
          message={task.error instanceof Error ? task.error.message : undefined}
          onRetry={() => void task.refetch()}
        />
      </div>
    );
  }

  const t = task.data;
  const isMine = t.assigned_to_id === user?.id;
  const timerOnThisTask = running.data?.task_id === t.id;
  const allowed = new Set(t.allowed_transitions);

  const doMove = (status: TaskStatus, body: Record<string, string> = {}) => {
    setActionError(null);
    move.mutate(
      { taskId: t.id, status, ...body },
      {
        onSuccess: () => {
          setBlocking(false);
          setBlockerNote("");
          setDelayReason("");
        },
        onError: setActionError,
      },
    );
  };

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Link
          to="/tasks"
          className="inline-flex items-center gap-1 text-xs text-ink-500 hover:text-ink-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          All tasks
        </Link>
        <Link to={`/releases/${t.release_id}`} className="text-xs text-brand-600 hover:underline">
          {t.release_code}
        </Link>
        <Link to={`/projects/${t.project_id}`} className="text-xs text-brand-600 hover:underline">
          {t.project_code}
        </Link>
      </div>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {t.name}
            <StatusBadge status={t.status} />
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono">{t.code}</span>
            <span>{t.task_type}</span>
            <PriorityLabel priority={t.priority} />
            <span>Complexity {t.complexity}/5</span>
            {t.is_overdue && (
              <span className="font-medium text-rag-red">{t.delay_days} days overdue</span>
            )}
          </span>
        }
        actions={
          <>
            {can(P.taskAssign) && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setAssigneeId(t.assigned_to_id);
                  setAssigning(true);
                }}
              >
                <UserPlus className="h-4 w-4" />
                {t.assigned_to_id ? "Reassign" : "Assign"}
              </button>
            )}

            {can(P.taskEstimate) && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setEstimateHours(String(t.estimated_hours));
                  setEstimateReason("");
                  setEstimating(true);
                }}
              >
                Re-estimate
              </button>
            )}

            {PRIMARY_ACTIONS.filter((a) => allowed.has(a.status)).map((action) => (
              <button
                key={action.status}
                type="button"
                className={action.status === "Blocked" ? "btn-secondary" : "btn-primary"}
                onClick={() =>
                  action.status === "Blocked" ? setBlocking(true) : doMove(action.status)
                }
                disabled={move.isPending}
              >
                {action.icon}
                {action.label}
              </button>
            ))}

            {t.requires_review && allowed.has("Submitted for Review") && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  setSubmitNote("");
                  setSubmitDelayReason("");
                  setSubmitting(true);
                }}
              >
                <Send className="h-4 w-4" />
                Submit for review
              </button>
            )}
          </>
        }
      />

      {actionError && (
        <div className="mb-3">
          <FormError error={actionError} />
        </div>
      )}

      {!t.can_start && t.blocked_by.length > 0 && (
        <div className="mb-4">
          <InlineAlert tone="warn">
            <span className="font-medium">Waiting on prerequisites.</span> This task
            cannot start until{" "}
            {t.blocked_by.map((d) => d.depends_on_code).join(", ")} {t.blocked_by.length === 1 ? "is" : "are"} complete.
          </InlineAlert>
        </div>
      )}

      {t.blocker_reason && (
        <div className="mb-4">
          <InlineAlert tone="error">
            <span className="font-medium">Blocked.</span> {t.blocker_reason}
          </InlineAlert>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard label="Progress" value={percent(t.completion_percent)} />
        <KpiCard
          label="Estimated"
          value={hours(t.estimated_hours)}
          hint={
            t.original_estimated_hours !== t.estimated_hours
              ? `originally ${hours(t.original_estimated_hours)}`
              : undefined
          }
        />
        <KpiCard label="Actual" value={hours(t.actual_hours)} />
        <KpiCard
          label="Variance"
          value={variance(t.effort_variance)}
          tone={(t.effort_variance ?? 0) > 0 ? "warn" : "good"}
        />
        <KpiCard
          label="Efficiency"
          value={percent(t.efficiency_percent)}
          tone={toneFor(t.efficiency_percent, { good: 95, warn: 80 })}
        />
        <KpiCard
          label="Rework"
          value={hours(t.rework_hours)}
          hint={`${t.revision_count} revision${t.revision_count === 1 ? "" : "s"}`}
          tone={t.rework_hours > 0 ? "warn" : "good"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Description">
            {t.description ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-700">
                {t.description}
              </p>
            ) : (
              <p className="text-sm text-ink-400">No description.</p>
            )}
            <div className="mt-4">
              <ProgressBar value={t.completion_percent} />
            </div>
          </Card>

          <Card
            title="Time log"
            action={
              isMine &&
              can(P.timeLogOwn) && (
                <div className="flex items-center gap-2">
                  {timerOnThisTask ? (
                    <button
                      type="button"
                      className="btn-danger px-2 py-1"
                      onClick={() => stopTimer.mutate()}
                      disabled={stopTimer.isPending}
                    >
                      {stopTimer.isPending ? <Spinner /> : <Square className="h-3.5 w-3.5" />}
                      Stop timer
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary px-2 py-1"
                      onClick={() => startTimer.mutate({ task_id: t.id })}
                      disabled={startTimer.isPending || Boolean(running.data)}
                      title={
                        running.data
                          ? `A timer is already running on ${running.data.task_code}`
                          : undefined
                      }
                    >
                      {startTimer.isPending ? <Spinner /> : <Play className="h-3.5 w-3.5" />}
                      Start timer
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-secondary px-2 py-1"
                    onClick={() => {
                      setTimeForm({
                        entry_date: new Date().toISOString().slice(0, 10),
                        hours: "",
                        description: "",
                      });
                      setLoggingTime(true);
                    }}
                  >
                    Log time
                  </button>
                </div>
              )
            }
            bodyClassName=""
          >
            {(startTimer.error || stopTimer.error) && (
              <div className="p-4">
                <FormError error={startTimer.error ?? stopTimer.error} />
              </div>
            )}

            {entries.data && entries.data.items.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-500">
                No time logged against this task yet.
              </p>
            )}

            {entries.data && entries.data.items.length > 0 && (
              <table className="w-full">
                <thead className="border-b border-ink-200 bg-ink-50">
                  <tr>
                    <th className="th">Date</th>
                    <th className="th">Who</th>
                    <th className="th text-right">Hours</th>
                    <th className="th">Source</th>
                    <th className="th">Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {entries.data.items.map((entry) => (
                    <tr key={entry.id} className={entry.is_running ? "bg-brand-50" : undefined}>
                      <td className="td text-xs">{shortDate(entry.entry_date)}</td>
                      <td className="td text-xs">{entry.user_name}</td>
                      <td className="td text-right text-xs tabular">
                        {entry.is_running ? (
                          <span className="text-brand-600">running…</span>
                        ) : (
                          hours(entry.hours)
                        )}
                      </td>
                      <td className="td text-2xs text-ink-500">
                        {entry.source}
                        {entry.is_rework && (
                          <span className="ml-1 rounded bg-rag-amberBg px-1 text-rag-amber">
                            rework
                          </span>
                        )}
                      </td>
                      <td className="td max-w-[16rem] truncate text-2xs text-ink-500">
                        {entry.description ?? DASH}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Dependencies" bodyClassName="">
            {t.dependencies.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-ink-500">
                This task does not wait on anything.
              </p>
            ) : (
              <ul className="divide-y divide-ink-100">
                {t.dependencies.map((dep) => (
                  <li
                    key={dep.id}
                    className="flex items-center justify-between gap-3 px-4 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <Link2 className="h-3.5 w-3.5 shrink-0 text-ink-400" />
                      <div className="min-w-0">
                        <p className="truncate text-xs text-ink-900">{dep.depends_on_name}</p>
                        <p className="font-mono text-2xs text-ink-400">
                          {dep.depends_on_code} · {dep.depends_on_status}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {dep.is_satisfied ? (
                        <span className="rounded bg-rag-greenBg px-1.5 py-0.5 text-2xs text-rag-green">
                          satisfied
                        </span>
                      ) : (
                        <span className="rounded bg-rag-amberBg px-1.5 py-0.5 text-2xs text-rag-amber">
                          {dep.is_blocking ? "blocking" : "pending"}
                        </span>
                      )}
                      {can(P.taskUpdate) && (
                        <button
                          type="button"
                          className="btn-ghost px-1"
                          onClick={() => removeDependency.mutate(dep.id)}
                          aria-label={`Remove dependency on ${dep.depends_on_code}`}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-rag-red" />
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Assignment">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="Assignee" value={t.assigned_to_name ?? "Unassigned"} />
              <Stat label="Required skill" value={t.required_skill_name ?? DASH} />
              <Stat label="Planned start" value={shortDate(t.planned_start)} />
              <Stat label="Planned end" value={shortDate(t.planned_end)} />
              <Stat label="Assigned" value={dateTime(t.assigned_at)} />
              <Stat label="Started" value={dateTime(t.started_at)} />
              <Stat label="Submitted" value={dateTime(t.submitted_at)} />
              <Stat label="Completed" value={dateTime(t.completed_at)} />
            </dl>
          </Card>

          <Card title="Flow metrics">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="Cycle time" value={durationHours(t.cycle_time_hours)} />
              <Stat label="Queue time" value={durationHours(t.queue_time_hours)} />
              <Stat label="Blocked hours" value={hours(t.blocked_hours)} />
              <Stat label="Submissions" value={t.submission_count} />
              <Stat label="Review status" value={t.review_status} />
              <Stat label="Mandatory" value={t.is_mandatory ? "Yes" : "No"} />
            </dl>
            {t.delay_reason && (
              <div className="mt-4 border-t border-ink-100 pt-3">
                <p className="text-2xs uppercase tracking-wide text-ink-500">Delay reason</p>
                <p className="mt-0.5 text-xs text-ink-800">{t.delay_reason}</p>
                {t.delay_note && <p className="mt-0.5 text-2xs text-ink-500">{t.delay_note}</p>}
              </div>
            )}
          </Card>

          <Card title="Available moves">
            {t.allowed_transitions.length === 0 ? (
              <p className="text-xs text-ink-500">
                This task is in a terminal state.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {t.allowed_transitions.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className="rounded-full border border-ink-300 px-2 py-0.5 text-2xs text-ink-700 hover:bg-ink-100 disabled:opacity-50"
                    onClick={() =>
                      status === "Blocked" ? setBlocking(true) : doMove(status)
                    }
                    disabled={move.isPending}
                  >
                    {status}
                  </button>
                ))}
              </div>
            )}
            <p className="mt-2 text-2xs text-ink-400">
              Taken from the workflow state machine, so these are exactly the moves
              the API will accept from here.
            </p>
          </Card>
        </div>
      </div>

      {/* Assign */}
      <Modal
        open={assigning}
        onClose={() => setAssigning(false)}
        title="Assign this task"
        description={`${t.code} — ${hours(t.estimated_hours)} estimated${
          t.required_skill_name ? `, needs ${t.required_skill_name}` : ""
        }`}
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setAssigning(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                assign.mutate(assigneeId, { onSuccess: () => setAssigning(false) })
              }
              disabled={assign.isPending}
            >
              {assign.isPending && <Spinner />}
              {assigneeId ? "Assign" : "Leave unassigned"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={assign.error} />
          <AssigneePicker
            taskId={t.id}
            requiredSkillId={null}
            selectedId={assigneeId}
            onSelect={setAssigneeId}
          />
        </div>
      </Modal>

      {/* Re-estimate */}
      <Modal
        open={estimating}
        onClose={() => setEstimating(false)}
        title="Re-estimate"
        description="The original estimate is preserved so effort accuracy stays measurable."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEstimating(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                estimate.mutate(
                  {
                    estimated_hours: Number(estimateHours),
                    reason: estimateReason || undefined,
                  },
                  { onSuccess: () => setEstimating(false) },
                )
              }
              disabled={estimate.isPending || estimateHours === ""}
            >
              {estimate.isPending && <Spinner />}
              Save estimate
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={estimate.error} />
          <InlineAlert tone="info">
            Original estimate: {hours(t.original_estimated_hours)}. Changing the
            current estimate never overwrites it.
          </InlineAlert>
          <Field label="Estimated hours" htmlFor="est" required>
            <TextInput
              id="est"
              type="number"
              min={0}
              step={0.5}
              value={estimateHours}
              onChange={(e) => setEstimateHours(e.target.value)}
            />
          </Field>
          <Field label="Why is it changing?" htmlFor="est_reason">
            <TextArea
              id="est_reason"
              value={estimateReason}
              onChange={(e) => setEstimateReason(e.target.value)}
              rows={2}
              placeholder="Customer added two more bay configurations."
            />
          </Field>
        </div>
      </Modal>

      {/* Blocker */}
      <Modal
        open={blocking}
        onClose={() => setBlocking(false)}
        title="Raise a blocker"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setBlocking(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                doMove("Blocked", {
                  note: blockerNote,
                  ...(delayReason ? { delay_reason: delayReason } : {}),
                })
              }
              disabled={move.isPending || blockerNote.trim().length < 5}
            >
              {move.isPending && <Spinner />}
              Block task
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={actionError} />
          <Field label="What is it waiting on?" htmlFor="blocker_note" required>
            <TextArea
              id="blocker_note"
              value={blockerNote}
              onChange={(e) => setBlockerNote(e.target.value)}
              placeholder="Vendor has not confirmed the drive unit envelope."
            />
          </Field>
          {delayReasons.length > 0 && (
            <Field label="Category" htmlFor="blocker_reason">
              <Select
                id="blocker_reason"
                value={delayReason}
                onChange={(e) => setDelayReason(e.target.value)}
                placeholder="Not categorised"
                options={delayReasons.map((r) => ({
                  value: r.value,
                  label: `${r.value} (${r.accountability.toLowerCase()})`,
                }))}
              />
            </Field>
          )}
        </div>
      </Modal>

      {/* Manual time entry */}
      <Modal
        open={loggingTime}
        onClose={() => setLoggingTime(false)}
        title="Log time"
        description="Overlapping entries and future dates are refused, so the totals stay trustworthy."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setLoggingTime(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                logTime.mutate(
                  {
                    task_id: t.id,
                    entry_date: timeForm.entry_date,
                    hours: Number(timeForm.hours),
                    description: timeForm.description || undefined,
                  },
                  { onSuccess: () => setLoggingTime(false) },
                )
              }
              disabled={logTime.isPending || !timeForm.entry_date || !timeForm.hours}
            >
              {logTime.isPending && <Spinner />}
              Log time
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={logTime.error} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date" htmlFor="entry_date" required>
              <TextInput
                id="entry_date"
                type="date"
                value={timeForm.entry_date}
                onChange={(e) => setTimeForm((f) => ({ ...f, entry_date: e.target.value }))}
              />
            </Field>
            <Field label="Hours" htmlFor="entry_hours" required>
              <TextInput
                id="entry_hours"
                type="number"
                min={0.25}
                step={0.25}
                value={timeForm.hours}
                onChange={(e) => setTimeForm((f) => ({ ...f, hours: e.target.value }))}
              />
            </Field>
          </div>
          <Field label="What did you do?" htmlFor="entry_desc">
            <TextArea
              id="entry_desc"
              rows={2}
              value={timeForm.description}
              onChange={(e) => setTimeForm((f) => ({ ...f, description: e.target.value }))}
            />
          </Field>
        </div>
      </Modal>

      {/* Submit for review */}
      <Modal
        open={submitting}
        onClose={() => setSubmitting(false)}
        title="Submit for review"
        description="A reviewer is routed automatically if you do not name one."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setSubmitting(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                submitReview.mutate(
                  {
                    task_id: t.id,
                    note: submitNote || undefined,
                    delay_reason: submitDelayReason || undefined,
                  },
                  { onSuccess: () => setSubmitting(false) },
                )
              }
              disabled={
                submitReview.isPending || (t.is_overdue && !submitDelayReason)
              }
            >
              {submitReview.isPending && <Spinner />}
              Submit
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={submitReview.error} />

          {t.is_overdue && (
            <>
              <InlineAlert tone="warn">
                This task passed its planned end date {t.delay_days} day
                {t.delay_days === 1 ? "" : "s"} ago. Submitting it needs a delay
                reason, which is what separates controllable delays from external
                ones in the analytics.
              </InlineAlert>
              <Field label="Delay reason" htmlFor="submit_delay" required>
                <Select
                  id="submit_delay"
                  value={submitDelayReason}
                  onChange={(e) => setSubmitDelayReason(e.target.value)}
                  placeholder="Choose a reason"
                  options={delayReasons.map((r) => ({
                  value: r.value,
                  label: `${r.value} (${r.accountability.toLowerCase()})`,
                }))}
                />
              </Field>
            </>
          )}

          <Field label="Note for the reviewer" htmlFor="submit_note">
            <TextArea
              id="submit_note"
              rows={3}
              value={submitNote}
              onChange={(e) => setSubmitNote(e.target.value)}
              placeholder="Layout revised after the structural feedback; drawing 3 is the one to check."
            />
          </Field>
        </div>
      </Modal>
    </>
  );
}
