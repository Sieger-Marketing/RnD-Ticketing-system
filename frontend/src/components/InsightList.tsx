/**
 * The management insight panel (spec section 46).
 *
 * Deliberately shows wins alongside problems: a panel that only ever reports
 * bad news trains people to stop reading it.
 */

import clsx from "clsx";
import { AlertTriangle, CheckCircle2, OctagonAlert } from "lucide-react";

import { EmptyState } from "@/components/ui/primitives";
import type { Insight } from "@/types/api";

const TONE = {
  critical: {
    bar: "border-l-rag-red",
    text: "text-rag-red",
    Icon: OctagonAlert,
  },
  warning: {
    bar: "border-l-rag-amber",
    text: "text-rag-amber",
    Icon: AlertTriangle,
  },
  positive: {
    bar: "border-l-rag-green",
    text: "text-rag-green",
    Icon: CheckCircle2,
  },
} as const;

export function InsightList({ insights }: { insights: Insight[] }) {
  if (insights.length === 0) {
    return (
      <EmptyState
        title="No exceptions right now"
        description="Nothing in the data crosses a configured threshold."
        icon={<CheckCircle2 className="h-7 w-7 text-rag-green" />}
      />
    );
  }

  return (
    <ul className="divide-y divide-ink-100">
      {insights.map((insight, index) => {
        const tone = TONE[insight.severity] ?? TONE.warning;
        const { Icon } = tone;
        return (
          <li
            key={`${insight.code}-${insight.entity_id}-${index}`}
            className={clsx("flex items-start gap-2 border-l-2 px-3 py-2.5", tone.bar)}
          >
            <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", tone.text)} />
            <p className="text-xs leading-relaxed text-ink-800">{insight.message}</p>
          </li>
        );
      })}
    </ul>
  );
}
