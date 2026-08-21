/**
 * How every date and rule in the system connects — and which of them you can
 * change from here.
 *
 * The distinction this screen exists to make honest: some rules are settings
 * and take effect the moment you save them; others are structural and would
 * need a code change. Showing both in one place, clearly marked, is the point.
 * A settings screen that quietly omits the rules it cannot alter leaves people
 * hunting for a control that was never there.
 *
 * Everything editable here writes straight through to the API. Most of these
 * numbers are applied when a figure is read, so a change shows up everywhere at
 * once. The health colours are the exception: they are stored on each record,
 * so the API re-rates the department on save. Either way the rule is that a
 * saved change is a change already in force, never one waiting for a job to run.
 */

import { Check, Lock, Sliders } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Field, TextInput } from "@/components/ui/form";
import {
  Card,
  ErrorState,
  InlineAlert,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import { useSettings, useUpdateSetting } from "@/hooks/queries";
import { useAuth } from "@/store/auth";
import type { AppSetting } from "@/types/api";

/** A number living inside a JSON setting, e.g. health.rules.red_delay_days. */
interface Knob {
  setting: string;
  path?: string;
  label: string;
  hint: string;
  unit?: string;
  min?: number;
  max?: number;
}

interface Group {
  title: string;
  blurb: string;
  knobs?: Knob[];
  toggles?: { setting: string; label: string; hint: string }[];
  lists?: { setting: string; label: string; hint: string }[];
  fixed?: { rule: string; why: string }[];
}

const GROUPS: Group[] = [
  {
    title: "When a date turns a bar amber or red",
    blurb:
      "A colour is stored on each record, so saving a change here re-rates every project and release straight away rather than waiting for someone to touch them.",
    knobs: [
      {
        setting: "health.rules",
        path: "amber_delay_days",
        label: "Amber after",
        hint: "Days past a committed date before the bar turns amber.",
        unit: "days",
        min: 0,
        max: 60,
      },
      {
        setting: "health.rules",
        path: "red_delay_days",
        label: "Red after",
        hint: "Days past a committed date before it turns red.",
        unit: "days",
        min: 0,
        max: 90,
      },
      {
        setting: "health.rules",
        path: "amber_overdue_tasks",
        label: "Amber at",
        hint: "Overdue tasks in one release before it turns amber.",
        unit: "tasks",
        min: 1,
        max: 20,
      },
      {
        setting: "health.rules",
        path: "red_overdue_tasks",
        label: "Red at",
        hint: "Overdue tasks in one release before it turns red.",
        unit: "tasks",
        min: 1,
        max: 40,
      },
      {
        setting: "health.rules",
        path: "deadline_proximity_days",
        label: "Warn within",
        hint: "Days before a deadline that unfinished work starts warning.",
        unit: "days",
        min: 1,
        max: 60,
      },
    ],
    fixed: [
      {
        rule: "The deadline warning only fires below 75% complete",
        why: "Fixed in code. The window above is configurable; this threshold is not.",
      },
    ],
  },
  {
    title: "The other things that colour a bar",
    blurb:
      "Same amber-then-red pattern, measured on the work rather than on the calendar.",
    knobs: [
      {
        setting: "health.rules",
        path: "amber_blocked_tasks",
        label: "Amber at",
        hint: "Blocked tasks in one release before it turns amber.",
        unit: "tasks",
        min: 1,
        max: 20,
      },
      {
        setting: "health.rules",
        path: "red_blocked_tasks",
        label: "Red at",
        hint: "Blocked tasks in one release before it turns red.",
        unit: "tasks",
        min: 1,
        max: 40,
      },
      {
        setting: "health.rules",
        path: "amber_effort_overrun_percent",
        label: "Amber past",
        hint: "How far actual hours may run over the estimate before amber.",
        unit: "%",
        min: 0,
        max: 200,
      },
      {
        setting: "health.rules",
        path: "red_effort_overrun_percent",
        label: "Red past",
        hint: "How far actual hours may run over the estimate before red.",
        unit: "%",
        min: 0,
        max: 300,
      },
      {
        setting: "health.rules",
        path: "amber_rework_percent",
        label: "Amber past",
        hint: "Share of hours spent on rework before amber.",
        unit: "%",
        min: 0,
        max: 100,
      },
      {
        setting: "health.rules",
        path: "red_rework_percent",
        label: "Red past",
        hint: "Share of hours spent on rework before red.",
        unit: "%",
        min: 0,
        max: 100,
      },
    ],
    fixed: [
      {
        rule: "Overrun and rework need hours logged before they say anything",
        why:
          "With no estimate or no time booked the figure is unknown, and unknown shows as a dash rather than as healthy.",
      },
    ],
  },
  {
    title: "When somebody has to explain themselves",
    blurb:
      "Both rules refuse the change and name the allowed reasons, rather than accepting it and asking later.",
    knobs: [
      {
        setting: "workflow.variance_threshold_percent",
        label: "Ask about hours beyond",
        hint:
          "How far actual hours may drift from the estimate, either way, before a reason is required.",
        unit: "%",
        min: 0,
        max: 200,
      },
    ],
    toggles: [
      {
        setting: "workflow.require_variance_reason",
        label: "Require a reason when hours drift",
        hint: "Applies when finishing work whose hours differ materially from the estimate.",
      },
      {
        setting: "workflow.require_delay_reason",
        label: "Require a reason when work is late",
        hint: "Applies when submitting or completing something past its planned end.",
      },
    ],
    lists: [
      {
        setting: "workflow.hold_reasons",
        label: "Reasons work may be put on hold",
        hint: "One per line. A hold is refused without one of these.",
      },
      {
        setting: "workflow.variance_reasons",
        label: "Reasons hours differ from the estimate",
        hint: "One per line.",
      },
    ],
  },
  {
    title: "How generated task dates are laid out",
    blurb: "Used when a release's tasks are created from the standard.",
    lists: [
      {
        setting: "capacity.working_days",
        label: "Working days",
        hint:
          "0 is Monday, 6 is Sunday. One per line. Generated dates skip everything not listed.",
      },
    ],
    fixed: [
      {
        rule: "Tasks are laid end to end at 8 hours a day",
        why: "Fixed in code. A starting point for the team lead to re-plan, not a schedule.",
      },
    ],
  },
  {
    title: "The date model itself",
    blurb:
      "These are structural. Changing any of them is a code change, not a setting — listed so you can see the whole model in one place.",
    fixed: [
      {
        rule: "Design commits to the Mfg. Release date, not to dispatch",
        why:
          "Dispatch is when the system ships and belongs to production. Every delay figure now measures against handover.",
      },
      {
        rule: "A task cannot start before its release starts",
        why: "Refused outright.",
      },
      {
        rule: "A task finishing past the release end moves the release end out",
        why: "The move is recorded, and the baseline does not move with it.",
      },
      {
        rule: "The baseline is stamped once and never changes",
        why:
          "Delivery is judged against it. Judged against a target that follows the work, everything is always on time.",
      },
      {
        rule: "Forecast = the later of a phase's target and today",
        why:
          "Uses no estimates. It is what makes a stalled release slide forward instead of sitting on a date already passed.",
      },
      {
        rule: "A project forecasts at the latest of its completion-critical releases",
        why: "Releases not marked completion-critical are excluded from the roll-up.",
      },
      {
        rule: "Actual start and end are observed from the tasks",
        why: "First task to start, last to finish. Never typed, never the day a button was pressed.",
      },
    ],
  },
];

function readValue(settings: AppSetting[], key: string, path?: string): unknown {
  const setting = settings.find((s) => s.key === key);
  if (!setting) return undefined;
  if (!path) return setting.value;
  const value = setting.value as Record<string, unknown> | null;
  return value ? value[path] : undefined;
}

function NumberKnob({
  knob,
  settings,
  onSave,
  saving,
  readOnly,
}: {
  knob: Knob;
  settings: AppSetting[];
  onSave: (key: string, value: unknown) => void;
  saving: boolean;
  readOnly: boolean;
}) {
  const current = readValue(settings, knob.setting, knob.path);
  const [draft, setDraft] = useState(String(current ?? ""));
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setDraft(String(current ?? ""));
  }, [current]);

  const dirty = draft !== String(current ?? "");

  const save = () => {
    const next = Number(draft);
    if (Number.isNaN(next)) return;
    if (knob.path) {
      const whole = settings.find((s) => s.key === knob.setting)?.value as Record<
        string,
        unknown
      >;
      onSave(knob.setting, { ...whole, [knob.path]: next });
    } else {
      onSave(knob.setting, next);
    }
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return (
    <Field label={knob.label} hint={knob.hint}>
      <div className="flex items-center gap-2">
        <TextInput
          type="number"
          className="w-24"
          min={knob.min}
          max={knob.max}
          value={draft}
          disabled={readOnly}
          onChange={(event) => setDraft(event.target.value)}
        />
        {knob.unit && <span className="text-xs text-ink-500">{knob.unit}</span>}
        {dirty && !readOnly && (
          <button type="button" className="btn-primary py-1" onClick={save} disabled={saving}>
            {saving ? <Spinner className="h-3.5 w-3.5" /> : "Save"}
          </button>
        )}
        {saved && !dirty && (
          <span className="flex items-center gap-1 text-xs text-rag-green">
            <Check className="h-3.5 w-3.5" />
            saved
          </span>
        )}
      </div>
    </Field>
  );
}

function ListKnob({
  setting,
  label,
  hint,
  settings,
  onSave,
  saving,
  readOnly,
}: {
  setting: string;
  label: string;
  hint: string;
  settings: AppSetting[];
  onSave: (key: string, value: unknown) => void;
  saving: boolean;
  readOnly: boolean;
}) {
  const current = readValue(settings, setting) as unknown[] | undefined;
  const asText = useMemo(
    () =>
      (current ?? [])
        .map((v) => (typeof v === "object" && v !== null ? (v as { value: string }).value : String(v)))
        .join("\n"),
    [current],
  );
  const [draft, setDraft] = useState(asText);
  useEffect(() => setDraft(asText), [asText]);

  const numeric = (current ?? []).every((v) => typeof v === "number");
  const structured = (current ?? []).some((v) => typeof v === "object" && v !== null);
  const dirty = draft !== asText;

  const save = () => {
    const lines = draft.split("\n").map((l) => l.trim()).filter(Boolean);
    onSave(setting, numeric ? lines.map(Number) : lines);
  };

  return (
    <Field label={label} hint={hint}>
      <textarea
        className="input font-mono text-xs"
        rows={Math.min(Math.max((current ?? []).length, 3), 10)}
        value={draft}
        disabled={structured || readOnly}
        onChange={(event) => setDraft(event.target.value)}
      />
      {structured ? (
        <p className="mt-1 text-2xs text-ink-500">
          These carry an accountability flag as well as a name, so they are not
          editable as plain text here.
        </p>
      ) : (
        dirty && !readOnly && (
          <button type="button" className="btn-primary mt-2 py-1" onClick={save} disabled={saving}>
            {saving ? <Spinner className="h-3.5 w-3.5" /> : "Save"}
          </button>
        )
      )}
    </Field>
  );
}

export default function Connections() {
  const can = useAuth((state) => state.can);
  const readOnly = !can("settings.manage");
  const settings = useSettings();
  const update = useUpdateSetting();
  const [error, setError] = useState<string | null>(null);

  const save = (key: string, value: unknown) => {
    setError(null);
    update.mutate({ key, value }, { onError: (e) => setError((e as Error).message) });
  };

  const rows = settings.data ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Connection map"
        subtitle="How the dates relate, and which of the rules you can change here."
      />

      {readOnly && (
        <InlineAlert tone="info">
          You can see every rule here, but changing one needs the settings
          permission. Nothing on this page will save.
        </InlineAlert>
      )}

      {settings.isError && <ErrorState onRetry={() => void settings.refetch()} />}
      {settings.isLoading && <SkeletonRows rows={5} cols={2} />}

      {error && (
        <InlineAlert tone="error">
          <p className="font-medium">That change was not saved.</p>
          <p>{error}</p>
        </InlineAlert>
      )}

      {settings.data && (
        <>
          <Card title="The shape of it">
            <div className="overflow-x-auto">
              <svg
                viewBox="0 0 880 330"
                role="img"
                aria-label="Commitments constrain downward from project to release to task; actuals observed at the bottom roll a forecast back up, which is compared against the commitment."
                className="min-w-[36rem] w-full h-auto text-ink-600"
              >
                <defs>
                  <marker id="cm-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
                  </marker>
                  <marker id="cm-r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill="#9b2423" />
                  </marker>
                </defs>

                <rect x="20" y="16" width="250" height="52" rx="8" fill="none" stroke="#9b2423" strokeWidth="2" />
                <text x="145" y="38" textAnchor="middle" fontSize="13" fontWeight="600" fill="#9b2423">COMMITMENT</text>
                <text x="145" y="55" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">required date · frozen</text>

                <line x1="145" y1="68" x2="145" y2="96" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />
                <text x="155" y="87" fontSize="10" fill="currentColor" opacity="0.85">constrains</text>

                <rect x="20" y="98" width="250" height="52" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <text x="145" y="120" textAnchor="middle" fontSize="12.5" fontWeight="600" fill="currentColor">PROJECT</text>
                <text x="145" y="137" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">start · required · forecast</text>

                <line x1="145" y1="150" x2="145" y2="178" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />

                <rect x="20" y="180" width="250" height="60" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <text x="145" y="202" textAnchor="middle" fontSize="12.5" fontWeight="600" fill="currentColor">DESIGN RELEASE</text>
                <text x="145" y="219" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">handover commitment · baseline</text>
                <text x="145" y="233" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">forecast · dispatch</text>

                <line x1="145" y1="240" x2="145" y2="268" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />
                <text x="155" y="259" fontSize="10" fill="currentColor" opacity="0.85">cannot start earlier</text>

                <rect x="20" y="270" width="250" height="46" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <text x="145" y="298" textAnchor="middle" fontSize="12.5" fontWeight="600" fill="currentColor">TASK / PHASE</text>

                <path d="M278,293 L360,293 L360,214" fill="none" stroke="#9b2423" strokeWidth="2" markerEnd="url(#cm-r)" />
                <text x="368" y="258" fontSize="10.5" fill="#9b2423">overrun moves</text>
                <text x="368" y="271" fontSize="10.5" fill="#9b2423">the target out</text>

                <rect x="470" y="180" width="240" height="60" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" />
                <text x="590" y="202" textAnchor="middle" fontSize="12" fontWeight="600" fill="currentColor">ACTUALS</text>
                <text x="590" y="219" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">first start · last finish</text>
                <text x="590" y="233" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">observed, never typed</text>

                <line x1="470" y1="210" x2="400" y2="210" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />

                <rect x="470" y="98" width="240" height="52" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <text x="590" y="120" textAnchor="middle" fontSize="12.5" fontWeight="600" fill="currentColor">FORECAST</text>
                <text x="590" y="137" textAnchor="middle" fontSize="10.5" fill="currentColor" opacity="0.8">max(target, today)</text>

                <line x1="590" y1="180" x2="590" y2="152" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />
                <text x="600" y="170" fontSize="10" fill="currentColor" opacity="0.85">rolls up</text>

                <path d="M470,124 L300,44" fill="none" stroke="#9b2423" strokeWidth="2" markerEnd="url(#cm-r)" />
                <text x="330" y="96" fontSize="10.5" fill="#9b2423">compared against</text>

                <rect x="746" y="98" width="118" height="52" rx="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <text x="805" y="120" textAnchor="middle" fontSize="11.5" fontWeight="600" fill="currentColor">VARIANCE</text>
                <text x="805" y="137" textAnchor="middle" fontSize="10" fill="currentColor" opacity="0.8">late by N days</text>
                <line x1="718" y1="124" x2="742" y2="124" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#cm-a)" />
              </svg>
            </div>
            <p className="mt-2 text-2xs text-ink-500">
              Constraints run down the left. Reality is observed at the bottom right and
              rolls a forecast back up, which is compared against the commitment — the
              commitment itself never moves on its own.
            </p>
          </Card>

          {GROUPS.map((group) => (
            <Card key={group.title} title={group.title}>
              <p className="mb-3 text-xs text-ink-500">{group.blurb}</p>

              {group.knobs && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {group.knobs.map((knob) => (
                    <NumberKnob
                      key={`${knob.setting}.${knob.path ?? ""}`}
                      knob={knob}
                      settings={rows}
                      onSave={save}
                      saving={update.isPending}
                      readOnly={readOnly}
                    />
                  ))}
                </div>
              )}

              {group.toggles && (
                <div className="mt-3 space-y-2">
                  {group.toggles.map((toggle) => {
                    const on = Boolean(readValue(rows, toggle.setting));
                    return (
                      <label
                        key={toggle.setting}
                        className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2"
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={on}
                          disabled={readOnly}
                          onChange={(event) => save(toggle.setting, event.target.checked)}
                        />
                        <span className="min-w-0 text-sm text-ink-900">
                          {toggle.label}
                          <span className="mt-0.5 block text-xs text-ink-500">
                            {toggle.hint}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}

              {group.lists && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {group.lists.map((list) => (
                    <ListKnob
                      key={list.setting}
                      {...list}
                      settings={rows}
                      onSave={save}
                      saving={update.isPending}
                      readOnly={readOnly}
                    />
                  ))}
                </div>
              )}

              {group.fixed && (
                <ul className="mt-4 space-y-2 border-t border-ink-200 pt-3">
                  {group.fixed.map((item) => (
                    <li key={item.rule} className="flex items-start gap-2">
                      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-400" />
                      <span className="min-w-0 text-sm text-ink-800">
                        {item.rule}
                        <span className="mt-0.5 block text-xs text-ink-500">{item.why}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ))}

          <p className="flex items-start gap-1.5 text-2xs text-ink-500">
            <Sliders className="mt-px h-3.5 w-3.5 shrink-0" />
            Saving a threshold re-rates the whole department immediately — the amber and
            red colours are stored on each record, so they are rewritten on save rather
            than left to drift until something else touches the project. The rest apply
            when a figure is read. Amber must sit before red, or the change is refused.
            Every change is recorded in the audit trail against your name.
          </p>
        </>
      )}
    </div>
  );
}
