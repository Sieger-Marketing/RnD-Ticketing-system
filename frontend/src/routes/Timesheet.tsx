/**
 * Personal timesheet (spec section 15).
 *
 * Four API facts shape this screen:
 *
 *  - There is no edit endpoint. A row can be deleted and re-logged, but not
 *    amended, so the UI offers delete rather than pretending to edit.
 *  - A running entry is returned with hours = 0, and every server-side total
 *    excludes it, so it is shown as live and left out of the totals.
 *  - `/entries` is paginated and caps at 200 a page. The headline hours come
 *    from `/summary`, which counts the whole period, because adding up one
 *    page silently under-reported a long range.
 *  - A manual entry with no interval is given 09:00 by the server and then
 *    refused for overlapping the last one. The interval is built client-side;
 *    see lib/timeEntry.
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
  InlineAlert,
  KpiCard,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import { ResponsiveTable } from "@/components/ui/ResponsiveTable";
import {
  useAllTimeEntries,
  useDeleteTimeEntry,
  useLogTime,
  useMyWork,
  useRunningTimer,
  useStopTimer,
  useTimeSummary,
} from "@/hooks/queries";
import { DASH, hours, localDaysAgo, localToday, shortDate } from "@/lib/format";
import { buildManualEntry } from "@/lib/timeEntry";
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

export default function Timesheet() {
  const { can, user } = useAuth();
  const canLog = can(P.timeLogOwn);

  const [from, setFrom] = useState(localDaysAgo(13));
  const [to, setTo] = useState(localToday());
  const [logging, setLogging] = useState(false);
  const [form, setForm] = useState({ task_id: "", entry_date: "", hours: "", description: "" });
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const range = { user_id: user?.id, date_from: from, date_to: to };
  const entries = useAllTimeEntries(range);
  const summary = useTimeSummary(range);
  const running = useRunningTimer();
  // Completed tasks are included: an entry can only be corrected by deleting
  // and re-logging it, and the task it belonged to may well have finished by
  // then. Excluding them made that correction impossible.
  const myWork = useMyWork({ include_completed: true });
  const stopTimer = useStopTimer();
  const logTime = useLogTime();
  const deleteEntry = useDeleteTimeEntry();

  const elapsed = useElapsed(running.data?.started_at);

  const rows = entries.data?.items ?? [];
  // Running rows carry hours = 0 and are excluded from every server aggregate.
  const completed = rows.filter((r) => !r.is_running);

  // Headline hours come from the server; day counts need the rows themselves.
  const loggedHours = summary.data?.logged_hours ?? null;
  const reworkHours = summary.data?.rework_hours ?? null;

  const byDay = new Map<string, number>();
  for (const row of completed) {
    byDay.set(row.entry_date, (byDay.get(row.entry_date) ?? 0) + row.hours);
  }
  const days = [...byDay.entries()].sort((a, b) => b[0].localeCompare(a[0]));

  const openLogForm = () => {
    logTime.reset();
    setForm({ task_id: "", entry_date: localToday(), hours: "", description: "" });
    setLogging(true);
  };

  const submitEntry = () => {
    logTime.mutate(
      buildManualEntry({
        taskId: form.task_id,
        entryDate: form.entry_date,
        hours: Number(form.hours),
        description: form.description || undefined,
        existing: rows,
      }),
      { onSuccess: () => setLogging(false) },
    );
  };

  return (
    <>
      <PageHeader
        title="My Timesheet"
        subtitle={`${from} to ${to}`}
        actions={
          canLog && (
            <button type="button" className="btn-primary" onClick={openLogForm}>
              Log time
            </button>
          )
        }
      />

      {running.data && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-signal-200 bg-signal-50 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="flex h-2 w-2 animate-pulse rounded-full bg-signal-600" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink-900">
                Timer running on{" "}
                {[running.data.project_name, running.data.release_name]
                  .filter(Boolean)
                  .join(" · ") || running.data.task_code}
              </p>
              <p className="truncate text-xs text-ink-600">{running.data.task_name}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg tabular text-signal-700">{elapsed}</span>
            {/* Stopping is a mutation like any other and needs the same
                permission; without this check a reader who lost time.log_own
                sees a Stop button that can only 403. */}
            {canLog && (
              <button
                type="button"
                className="btn-danger px-2 py-1"
                onClick={() => stopTimer.mutate()}
                disabled={stopTimer.isPending}
              >
                {stopTimer.isPending ? <Spinner /> : <Square className="h-3.5 w-3.5" />}
                Stop
              </button>
            )}
          </div>
        </div>
      )}

      {stopTimer.error && (
        <div className="mb-3">
          <FormError error={stopTimer.error} />
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Logged"
          value={hours(loggedHours)}
          hint={`${completed.length} entries shown`}
          icon={<Clock className="h-4 w-4" />}
        />
        <KpiCard
          label="Rework"
          value={hours(reworkHours)}
          tone={(reworkHours ?? 0) > 0 ? "warn" : "good"}
          hint="Time against an open revision"
        />
        <KpiCard label="Days worked" value={days.length} hint="Days with an entry" />
        <KpiCard
          label="Daily average"
          value={days.length && loggedHours !== null ? hours(loggedHours / days.length) : DASH}
          hint="Across days worked"
        />
      </div>

      {entries.data?.truncated && (
        <div className="mb-3">
          <InlineAlert tone="warn">
            This range holds {entries.data.total} entries and only the first{" "}
            {rows.length} are listed. The hours above still cover the whole
            period; narrow the dates to see every row.
          </InlineAlert>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-ink-200 bg-white p-3">
        <div>
          <label className="label" htmlFor="from">
            From
          </label>
          <TextInput id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
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
            setFrom(localDaysAgo(13));
            setTo(localToday());
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

        {entries.data && (
          <ResponsiveTable
            rows={rows}
            rowKey={(e) => e.id}
            minWidth="44rem"
            empty={
              <EmptyState
                title="No time logged in this range"
                description="Start a timer from a task, or log time manually."
              />
            }
            columns={[
              {
                key: "task",
                header: "Work",
                mobile: "primary",
                cell: (e) => (
                  <Link
                    to={`/tasks/${e.task_id}`}
                    className="block min-w-0 text-signal-700 hover:underline"
                    onClick={(event) => event.stopPropagation()}
                    title={e.task_code ?? undefined}
                  >
                    <span className="block truncate">
                      {e.project_name ?? "No project"}
                      {e.release_name && (
                        <span className="text-ink-500"> · {e.release_name}</span>
                      )}
                    </span>
                    <span className="block truncate text-2xs text-ink-500">
                      {e.task_name}
                    </span>
                  </Link>
                ),
              },
              {
                key: "date",
                header: "Date",
                mobile: "field",
                cell: (e) => <span className="text-xs">{shortDate(e.entry_date)}</span>,
              },
              {
                key: "hours",
                header: "Hours",
                align: "right",
                mobile: "field",
                cell: (e) =>
                  e.is_running ? (
                    <span className="text-xs text-signal-700">running</span>
                  ) : (
                    <span className="text-xs tabular">{hours(e.hours)}</span>
                  ),
              },
              {
                key: "source",
                header: "Source",
                mobile: "field",
                cell: (e) => (
                  <span className="text-2xs text-ink-500">
                    {e.source}
                    {e.is_rework && (
                      <span className="ml-1 rounded bg-rag-amberBg px-1 text-rag-amber">
                        rework
                      </span>
                    )}
                  </span>
                ),
              },
              {
                key: "note",
                header: "Note",
                mobile: "field",
                className: "max-w-[18rem]",
                cell: (e) => (
                  <span className="truncate text-2xs text-ink-500">
                    {e.description ?? DASH}
                  </span>
                ),
              },
              {
                key: "actions",
                header: "",
                cell: (e) =>
                  !e.is_running && canLog ? (
                    <button
                      type="button"
                      className="btn-ghost px-1"
                      onClick={(event) => {
                        event.stopPropagation();
                        deleteEntry.reset();
                        setPendingDelete(e.id);
                      }}
                      aria-label="Delete this entry"
                      title="Entries cannot be edited, only deleted and re-logged"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-rag-red" />
                    </button>
                  ) : null,
              },
            ]}
          />
        )}
      </Card>

      {days.length > 0 && (
        <Card className="mt-4" title="Daily totals">
          <div className="space-y-1.5">
            {days.map(([day, dayHours]) => (
              <div key={day} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-xs text-ink-600 sm:w-28">
                  {shortDate(day)}
                </span>
                <div className="h-3 flex-1 overflow-hidden rounded bg-ink-100">
                  <div
                    className="h-full rounded bg-ink-700"
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
        description="The entry is placed after whatever you already logged that day, so it cannot clash with it."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setLogging(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={submitEntry}
              disabled={
                logTime.isPending ||
                !form.task_id ||
                !form.entry_date ||
                !form.hours ||
                Number(form.hours) <= 0
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
                  {[task.project_name, task.release_name, task.name]
                    .filter(Boolean)
                    .join(" · ")}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date" htmlFor="ts_date" required>
              <TextInput
                id="ts_date"
                type="date"
                max={localToday()}
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
