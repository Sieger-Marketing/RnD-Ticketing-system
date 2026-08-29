/**
 * The review queue (spec section 17).
 *
 * Three API rules shape this screen, and each one is handled here rather than
 * being discovered by the reviewer as a rejected click:
 *
 *  - A decision on a review that was never started fails. The state machine
 *    only allows Approved / Revision Required from "Under Review", so opening
 *    a review claims it first.
 *  - Returning work needs a revision category, and the category is *not*
 *    validated against the configured list. An invented one is accepted and
 *    silently books the rework as Controllable, which is the department's
 *    fault. So the category is a select, never free text.
 *  - Approving a task that went overdue while it sat in the queue fails, and
 *    the decision endpoint has no field to fix it. The delay reason has to be
 *    written onto the task first, so the form collects it up front.
 */

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Pagination } from "@/components/ui/Filters";
import { Field, FormError, Select, TextArea } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Card,
  CountBadge,
  EmptyState,
  ErrorState,
  InlineAlert,
  PageHeader,
  SkeletonRows,
  Spinner,
  StatusBadge,
} from "@/components/ui/primitives";
import {
  useReviewDecision,
  useReviewQueue,
  useReviews,
  useStartReview,
  useTask,
  useUpdateTask,
  useVocabularies,
} from "@/hooks/queries";
import { DASH, dateTime, durationHours, relative } from "@/lib/format";
import { P, useAuth } from "@/store/auth";
import type { Review } from "@/types/api";

type Decision = "Approved" | "Rejected" | "Revision Requested";

export default function Reviews() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { can, user } = useAuth();

  const canReview = can(P.reviewPerform);
  const [active, setActive] = useState<Review | null>(null);
  const [decision, setDecision] = useState<Decision>("Approved");
  const [comments, setComments] = useState("");
  const [category, setCategory] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [delayReason, setDelayReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  // Which review this dialog has already claimed, so re-renders do not
  // fire the start mutation again.
  const claimed = useRef<string | null>(null);

  const queue = useReviewQueue({ enabled: canReview });
  const [page, setPage] = useState(1);
  const all = useReviews({ page, page_size: 25 });
  const { data: vocab } = useVocabularies();

  // ReviewOut carries no task status, assignee or due date, so the decision
  // form joins the task it is about. Only for the open review, not every row.
  const task = useTask(active?.task_id);
  const startReview = useStartReview();
  const submitDecision = useReviewDecision(active?.id ?? "");
  const updateTask = useUpdateTask(active?.task_id ?? "");

  const categories = vocab?.revision_categories ?? [];
  const delayReasons = vocab?.delay_reasons ?? [];

  const isSelfReview = Boolean(task.data && task.data.assigned_to_id === user?.id);
  // Approval drives the task to Completed, which re-triggers the overdue rule.
  // require_delay_reason is a runtime setting; when an admin turns it off the
  // API stops asking, and the form must stop demanding it too.
  const needsDelayReason =
    (vocab?.require_delay_reason ?? true) &&
    decision === "Approved" &&
    Boolean(task.data?.is_overdue) &&
    !task.data?.delay_reason;

  const open = (review: Review) => {
    setError(null);
    setDecision("Approved");
    setComments("");
    setCategory("");
    setRootCause("");
    setDelayReason("");
    setActive(review);
  };

  /**
   * Claim the review, but only once we know whose task it is.
   *
   * Starting a review is a state change: it stamps review_started_at, claims
   * an unrouted review for the caller and moves the task to Under Review.
   * Firing that the instant the dialog opened meant a lead who is also the
   * assignee mutated the task and only then hit the self-review ban at
   * decision time, with no way to undo what the click had already done.
   */
  useEffect(() => {
    if (!active || active.status !== "Pending") return;
    if (!task.isSuccess) return;
    if (isSelfReview) return;
    if (claimed.current === active.id) return;
    claimed.current = active.id;
    startReview.mutate(active.id, { onError: setError });
    // startReview is a stable mutation object; re-running on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, task.isSuccess, isSelfReview]);

  const decide = () => {
    if (!active) return;
    setError(null);

    // Captured now rather than read inside the callback: on the overdue path
    // send() runs after a PATCH round trip, and the reviewer can change the
    // decision while that is in flight. Closing over the live state would post
    // a different verdict from the one they pressed.
    const chosen = {
      result: decision,
      comments: comments || undefined,
      category,
      rootCause,
    };

    const send = () =>
      submitDecision.mutate(
        {
          result: chosen.result,
          comments: chosen.comments,
          ...(chosen.result === "Approved"
            ? {}
            : {
                revision_category: chosen.category,
                root_cause: chosen.rootCause || undefined,
              }),
        },
        {
          onSuccess: () => {
            setActive(null);
            queryClient.invalidateQueries({ queryKey: ["review-queue"] });
          },
          onError: setError,
        },
      );

    // The decision endpoint has no delay_reason field, so the reason is
    // written onto the task before approving, otherwise the approval 422s.
    if (needsDelayReason) {
      updateTask.mutate(
        { delay_reason: delayReason },
        { onSuccess: send, onError: setError },
      );
      return;
    }
    send();
  };

  // Both guards below are derived from the joined task. While that request is
  // in flight they collapse to false, which previously left Approve enabled
  // and let a reviewer fire a decision the API would refuse -- the self-review
  // ban, or the missing delay reason on an overdue task. Nothing is
  // submittable until the task that decides those rules has actually arrived.
  const guardsKnown = task.isSuccess;

  const canSubmit =
    guardsKnown &&
    !submitDecision.isPending &&
    !updateTask.isPending &&
    !isSelfReview &&
    (decision === "Approved" ? !needsDelayReason || Boolean(delayReason) : Boolean(category));

  return (
    <>
      <PageHeader
        title="Reviews"
        subtitle={
          canReview
            ? "Work waiting on your judgement, oldest first."
            : "Reviews of your submitted work."
        }
      />

      {canReview && (
        <Card
          className="mb-4"
          title={
            <span className="flex items-center gap-2">
              My queue
              <CountBadge count={queue.data?.length ?? 0} />
            </span>
          }
          bodyClassName=""
        >
          {queue.isLoading && <SkeletonRows rows={4} />}
          {queue.isError && (
            <ErrorState
              message={queue.error instanceof Error ? queue.error.message : undefined}
              onRetry={() => void queue.refetch()}
            />
          )}
          {queue.data && queue.data.length === 0 && (
            <EmptyState
              title="Your queue is clear"
              description="Submitted work routed to you appears here."
              icon={<CheckCircle2 className="h-7 w-7 text-rag-green" />}
            />
          )}
          {queue.data && queue.data.length > 0 && (
            <ul className="divide-y divide-ink-100">
              {queue.data.map((review) => (
                <li
                  key={review.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-ink-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink-900">
                      {review.task_name}
                    </p>
                    <p className="truncate text-2xs text-ink-500" title={review.task_code ?? undefined}>
                      {[review.project_name, review.release_name]
                        .filter(Boolean)
                        .join(" · ") || review.task_code}
                      <span className="text-ink-400">
                        {" "}· round {review.round_number} · waiting{" "}
                        {relative(review.submitted_at)}
                      </span>
                    </p>
                    {review.comments && (
                      <p className="mt-0.5 max-w-xl text-xs text-ink-600">
                        “{review.comments}”
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={review.status} />
                    <button
                      type="button"
                      className="btn-primary px-2 py-1"
                      onClick={() => open(review)}
                    >
                      <ClipboardCheck className="h-3.5 w-3.5" />
                      Review
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Card
        title={
          <span className="flex items-center gap-2">
            All reviews
            {all.data && (
              <span className="text-2xs font-normal text-ink-500">
                {all.data.total.toLocaleString()} total
              </span>
            )}
          </span>
        }
        bodyClassName=""
      >
        {all.isLoading && <SkeletonRows rows={6} />}
        {all.data && all.data.items.length === 0 && (
          <EmptyState title="No reviews yet" />
        )}
        {all.data && all.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="border-b border-ink-200 bg-ink-50">
                <tr>
                  <th className="th">Task</th>
                  <th className="th">Round</th>
                  <th className="th">Reviewer</th>
                  <th className="th">Status</th>
                  <th className="th">Result</th>
                  <th className="th">Submitted</th>
                  <th className="th text-right">Turnaround</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {all.data.items.map((review) => (
                  <tr
                    key={review.id}
                    className="cursor-pointer hover:bg-ink-50"
                    onClick={() => navigate(`/tasks/${review.task_id}`)}
                  >
                    <td className="td max-w-[20rem]">
                      <div className="truncate font-medium text-ink-900">
                        {review.task_name}
                      </div>
                      <div className="font-mono text-2xs text-ink-400">
                        {review.task_code}
                      </div>
                    </td>
                    <td className="td text-xs tabular">{review.round_number}</td>
                    <td className="td text-xs text-ink-600">
                      {review.reviewer_name ?? (
                        canReview ? (
                          <button
                            type="button"
                            className="btn-secondary px-2 py-0.5 text-2xs"
                            onClick={(event) => {
                              event.stopPropagation();
                              // Starting an unrouted review claims it, which is
                              // the only way one reaches a queue at all.
                              startReview.mutate(review.id, { onError: setError });
                            }}
                            disabled={startReview.isPending}
                            title="Nobody is assigned to review this; take it yourself"
                          >
                            Claim
                          </button>
                        ) : (
                          <span className="text-rag-amber">Unrouted</span>
                        )
                      )}
                    </td>
                    <td className="td">
                      <StatusBadge status={review.status} />
                    </td>
                    <td className="td text-xs">
                      {review.result ? (
                        <span
                          className={
                            review.result === "Approved"
                              ? "text-rag-green"
                              : "text-rag-amber"
                          }
                        >
                          {review.result}
                        </span>
                      ) : (
                        <span className="text-ink-400">{DASH}</span>
                      )}
                    </td>
                    <td className="td text-xs text-ink-600">
                      {dateTime(review.submitted_at)}
                    </td>
                    <td className="td text-right text-xs tabular">
                      {durationHours(review.turnaround_hours)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {all.data && all.data.total > all.data.page_size && (
          <Pagination
            page={all.data.page}
            pages={all.data.pages}
            total={all.data.total}
            pageSize={all.data.page_size}
            onPage={setPage}
          />
        )}
      </Card>

      <Modal
        open={active !== null}
        onClose={() => setActive(null)}
        title="Review"
        description={active ? `${active.task_code} — ${active.task_name}` : undefined}
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setActive(null)}>
              Cancel
            </button>
            <button
              type="button"
              className={decision === "Approved" ? "btn-primary" : "btn-danger"}
              onClick={decide}
              disabled={!canSubmit}
            >
              {(submitDecision.isPending || updateTask.isPending) && <Spinner />}
              {decision === "Approved" ? "Approve" : "Return for rework"}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <FormError error={error} />

          {task.isLoading && (
            <InlineAlert tone="info">
              Loading the task this review is about. The decision opens once its
              rules are known.
            </InlineAlert>
          )}

          {isSelfReview && (
            <InlineAlert tone="error">
              This task is assigned to you, so reviewing it is refused. Nothing
              has been changed — ask another reviewer to take it, or reassign
              the task first.
            </InlineAlert>
          )}

          {task.data && (
            <div className="rounded-md bg-ink-50 p-3">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-700">
                <Link
                  to={`/tasks/${task.data.id}`}
                  className="text-signal-700 hover:underline"
                >
                  Open the task
                </Link>
                <span>Assignee: {task.data.assigned_to_name ?? DASH}</span>
                <span>Estimated {task.data.estimated_hours}h</span>
                <span>Actual {task.data.actual_hours}h</span>
                {task.data.revision_count > 0 && (
                  <span className="text-rag-amber">
                    {task.data.revision_count} previous revision
                    {task.data.revision_count === 1 ? "" : "s"}
                  </span>
                )}
              </div>
            </div>
          )}

          <Field label="Decision" htmlFor="decision" required>
            <Select
              id="decision"
              value={decision}
              onChange={(e) => setDecision(e.target.value as Decision)}
              options={[
                { value: "Approved", label: "Approve — the work is done" },
                {
                  value: "Revision Requested",
                  label: "Request revision — send it back with changes",
                },
                { value: "Rejected", label: "Reject — the work is not acceptable" },
              ]}
            />
          </Field>

          {decision !== "Approved" && (
            <>
              <InlineAlert tone="warn">
                Both options return the task to the designer as rework. The
                category decides whether those hours count against the team or
                against an external cause, so it is worth getting right.
              </InlineAlert>

              <Field label="Revision category" htmlFor="category" required>
                <Select
                  id="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="Choose a category"
                  options={categories.map((c) => ({
                    value: c.value,
                    label: `${c.value} (${c.accountability.toLowerCase()})`,
                  }))}
                />
              </Field>

              <Field
                label="Root cause"
                htmlFor="root_cause"
                hint="Optional, but it is what makes the rework analysis useful later."
              >
                <TextArea
                  id="root_cause"
                  rows={2}
                  value={rootCause}
                  onChange={(e) => setRootCause(e.target.value)}
                  placeholder="Structural loads were taken from the superseded revision of the civil drawing."
                />
              </Field>
            </>
          )}

          {needsDelayReason && (
            <>
              <InlineAlert tone="warn">
                This task passed its planned end date while it was in the queue.
                Approving it completes it, and a completed task that finished
                late has to say why.
              </InlineAlert>
              <Field label="Delay reason" htmlFor="review_delay" required>
                <Select
                  id="review_delay"
                  value={delayReason}
                  onChange={(e) => setDelayReason(e.target.value)}
                  placeholder="Choose a reason"
                  options={delayReasons.map((r) => ({
                    value: r.value,
                    label: `${r.value} (${r.accountability.toLowerCase()})`,
                  }))}
                />
              </Field>
            </>
          )}

          <Field label="Comments" htmlFor="comments">
            <TextArea
              id="comments"
              rows={3}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder={
                decision === "Approved"
                  ? "Anything worth recording about the approval."
                  : "What needs to change, specifically."
              }
            />
          </Field>

          {decision !== "Approved" && (
            <p className="flex items-start gap-1.5 text-2xs text-ink-500">
              <RotateCcw className="mt-0.5 h-3 w-3 shrink-0" />
              The task returns to Revision Required. Resolving the revision does
              not move it on by itself — the designer restarts it when the rework
              begins.
            </p>
          )}

          {decision === "Approved" && (
            <p className="flex items-start gap-1.5 text-2xs text-ink-500">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              Approving completes the task and releases anything waiting on it.
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
