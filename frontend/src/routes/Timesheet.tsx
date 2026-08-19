/**
 * Personal timesheet (spec section 15).
 *
 * Two API facts shape this screen:
 *
 *  - There is no edit endpoint. A row can be deleted and re-logged, but not
 *    amended, so the UI offers delete rather than pretending to edit.
 *  - A running entry is returned with hours = 0, and every server-side total
 *    excludes it. Summing the rows naively would therefore disagree with the
 *    summary, so running entries are shown as live and left out of the totals.
 */

import { Clock, Square, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Field, FormError, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import {
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import {
  useDeleteTimeEntry,
  useLogTime,
  useMyWork,
  useRunningTimer,
  useStopTimer,
  useTimeEntries,
} from "@/hooks/queries";
import { DASH, hours, shortDate } from "@/lib/format";
import { P, useAuth } from "@/store/auth";

/** Elapsed time for a running entry, recomputed each second. */
function useElapsed(startedAt: string | null | undefined): string {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!startedAt) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  if (!startedAt) return DASH;
  const seconds = Math.max(0, (Date.now() - new Date(startedAt).getTime()) / 1000);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function Timesheet() {
  const { can, user } = useAuth();
  const canLog = can(P.timeLogOwn);

  const [from, setFrom] = useState(isoDaysAgo(13));
  const [to, setTo] = useState(new Date().toISOString().slice(0, 10));
  const [logging, setLogging] = useState(false);
  const [form, setForm] = useState({ task_id: "", entry_date: "", hours: "", description: "" });
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const entries = useTimeEntries({
    user_id: user?.id,
    date_from: from,
    date_to: to,
    page_size: 200,
  });
  const running = useRunningTimer();
  const myWork = useMyWork();
  const stopTimer = useStopTimer();
  const logTime = useLogTime();
  const deleteEntry = useDeleteTimeEntry();

  const elapsed = useElapsed(running.data?.started_at);

  const rows = entries.data?.items ?? [];
  // Running rows carry hours = 0 and are excluded from every server aggregate;
  // excluding them here keeps this page agreeing with the rest of the app.
  const completed = rows.filter((r) => !r.is_running);
  const total = completed.reduce((sum, r) => sum + r.hours, 0);
  const reworkTotal = completed
    .filter((r) => r.is_rework)
    .reduce((sum, r) => sum + r.hours, 0);

  const byDay = new Map<string, number>();
  for (const row of completed) {
    byDay.set(row.entry_date, (byDay.get(row.entry_date) ?? 0) + row.hours);
  }
  const days = [...byDay.entries()].sort((a, b) => b[0].localeCompare(a[0]));

  return (
    <>
      <PageHeader
        title="My Timesheet"
        subtitle={`${from} to ${to}`}
        actions={
          canLog && (
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setForm({
                  task_id: "",
                  entry_date: new Date().toISOString().slice(0, 10),
                  hours: "",
                  description: "",
                });
                setLogging(true);
              }}
            >
              Log time
            </button>
          )
        }
      />

      {running.data && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-signal-200 bg-signal-50 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="flex h-2 w-2 animate-pulse rounded-full bg-signal-600" />
            <div>
              <p className="text-sm font-medium text-ink-900">
                Timer running on {running.data.task_code}
              </p>
              <p className="text-xs text-ink-600">{running.data.task_name}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg tabular text-signal-700">{elapsed}</span>
            <button
              type="button"
              className="btn-danger px-2 py-1"
              onClick={() => stopTimer.mutate()}
              disabled={stopTimer.isPending}
            >
              {stopTimer.isPending ? <Spinner /> : <Square className="h-3.5 w-3.5" />}
              Stop
            </button>
          </div>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Logged"
          value={hours(total)}
          hint={`${completed.length} entries`}
          icon={<Clock className="h-4 w-4" />}
        />
        <KpiCard
          label="Rework"
          value={hours(reworkTotal)}
          tone={reworkTotal > 0 ? "warn" : "good"}
          hint="Time against an open revision"
        />
        <KpiCard
          label="Days worked"
          value={days.length}
          hint="Days with at least one entry"
        />
        <KpiCard
          label="Daily average"
          value={days.length ? hours(total / days.length) : DASH}
          hint="Across days worked"
        />
      </div>

      <div className="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-ink-200 bg-white p-3">
        <div>
          <label className="label" htmlFor="from">
            From
          </label>
          <TextInput
            id="from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="to">
            To
          </label>
          <TextInput id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => {
            setFrom(isoDaysAgo(13));
            setTo(new Date().toISOString().slice(0, 10));
          }}
        >
          Last 14 days
        </button>
      </div>

      <Card bodyClassName="">
        {entries.isLoading && <SkeletonRows rows={8} cols={5} />}

        {entries.isError && (
          <ErrorState
            message={entries.error instanceof Error ? entries.error.message : undefined}
            onRetry={() => void entries.refetch()}
          />
        )}

        {entries.data && rows.length === 0 && (
          <EmptyState
            title="No time logged in this range"
            description="Start a timer from a task, or log time manually."
          />
        )}

        {entries.data && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="border-b border-ink-200 bg-ink-50">
                <tr>
                  <th className="th">Date</th>
                  <th className="th">Task</th>
                  <th className="th text-right">Hours</th>
                  <th className="th">Source</th>
                  <th className="th">Note</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {rows.map((entry) => (
                  <tr
                    key={entry.id}
                    className={entry.is_running ? "bg-signal-50" : "hover:bg-ink-50"}
                  >
                    <td className="td text-xs">{shortDate(entry.entry_date)}</td>
                    <td className="td max-w-[20rem]">
                      <Link
                        to={`/tasks/${entry.task_id}`}
                        className="truncate text-xs text-signal-700 hover:underline"
                      >
                        {entry.task_name}
                      </Link>
                      <div className="font-mono text-2xs text-ink-400">
                        {entry.task_code}
                      </div>
                    </td>
                    <td className="td text-right text-xs tabular">
                      {entry.is_running ? (
                        <span className="text-signal-700">running</span>
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
                    <td className="td max-w-[18rem] truncate text-2xs text-ink-500">
                      {entry.description ?? DASH}
                    </td>
                    <td className="td">
                      {!entry.is_running && canLog && (
                        <button
                          type="button"
                          className="btn-ghost px-1"
                          onClick={() => setPendingDelete(entry.id)}
                          aria-label="Delete this entry"
                          title="Entries cannot be edited, only deleted and re-logged"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-rag-red" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {days.length > 0 && (
        <Card className="mt-4" title="Daily totals">
          <div className="space-y-1.5">
            {days.map(([day, dayHours]) => (
              <div key={day} className="flex items-center gap-3">
                <span className="w-28 shrink-0 text-xs text-ink-600">
                  {shortDate(day)}
                </span>
                <div className="h-3 flex-1 overflow-hidden rounded bg-ink-100">
                  <div
                    className="h-full rounded bg-signal-500"
                    style={{ width: `${Math.min(100, (dayHours / 8) * 100)}%` }}
                  />
                </div>
                <span className="w-12 shrink-0 text-right text-xs tabular text-ink-800">
                  {hours(dayHours)}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-2xs text-ink-400">
            Bars are scaled against an eight-hour day.
          </p>
        </Card>
      )}

      <Modal
        open={logging}
        onClose={() => setLogging(false)}
        title="Log time"
        description="Overlapping entries and future dates are refused, so the totals stay trustworthy."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setLogging(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                logTime.mutate(
                  {
                    task_id: form.task_id,
                    entry_date: form.entry_date,
                    hours: Number(form.hours),
                    description: form.description || undefined,
                  },
                  { onSuccess: () => setLogging(false) },
                )
              }
              disabled={
                logTime.isPending || !form.task_id || !form.entry_date || !form.hours
              }
            >
              {logTime.isPending && <Spinner />}
              Log time
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <FormError error={logTime.error} />
          <Field
            label="Task"
            htmlFor="ts_task"
            required
            hint="Only tasks assigned to you accept your time."
          >
            <select
              id="ts_task"
              className="input"
              value={form.task_id}
              onChange={(e) => setForm((f) => ({ ...f, task_id: e.target.value }))}
            >
              <option value="">Choose a task</option>
              {(myWork.data ?? []).map((task) => (
                <option key={task.id} value={task.id}>
                  {task.code} — {task.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date" htmlFor="ts_date" required>
              <TextInput
                id="ts_date"
                type="date"
                max={new Date().toISOString().slice(0, 10)}
                value={form.entry_date}
                onChange={(e) => setForm((f) => ({ ...f, entry_date: e.target.value }))}
              />
            </Field>
            <Field label="Hours" htmlFor="ts_hours" required hint="Up to 16 in one entry.">
              <TextInput
                id="ts_hours"
                type="number"
                min={0.25}
                max={16}
                step={0.25}
                value={form.hours}
                onChange={(e) => setForm((f) => ({ ...f, hours: e.target.value }))}
              />
            </Field>
          </div>
          <Field label="What did you do?" htmlFor="ts_desc">
            <TextArea
              id="ts_desc"
              rows={2}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </Field>
        </div>
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="Delete this entry?"
        description="Time entries cannot be edited. Deleting removes the hours from every total that includes them."
        size="sm"
        footer={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setPendingDelete(null)}
            >
              Keep it
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={() =>
                pendingDelete &&
                deleteEntry.mutate(pendingDelete, {
                  onSuccess: () => setPendingDelete(null),
                })
              }
              disabled={deleteEntry.isPending}
            >
              {deleteEntry.isPending && <Spinner />}
              Delete
            </button>
          </>
        }
      >
        <FormError error={deleteEntry.error} />
      </Modal>
    </>
  );
}
