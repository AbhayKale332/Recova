"use client";

import { useI18n } from "@/lib/i18n";
import { formatAbsolute } from "@/lib/format";
import type { TraceStep } from "@/lib/simulation";

/**
 * Why the agent did what it did, one step at a time.
 *
 * Every line is rendered from an audit row that was actually written — this
 * shows the receipt, it does not narrate over it. The reasons come from the
 * policy sandbox and the compliance rules verbatim, which is why they name a
 * rule and a number rather than saying "blocked".
 *
 * Each step also carries the budget the agent still had at that moment, so a
 * reader watches the room to act shrink rather than only seeing where it ran out.
 */
export function DecisionTrace({ steps }: { steps: TraceStep[] }) {
  const { t, locale } = useI18n();

  if (!steps.length) {
    return <p className="text-[13px] text-[var(--muted)]">{t.sim.whyEmpty}</p>;
  }

  return (
    <ol className="flex flex-col">
      {steps.map((step, index) => (
        <li key={step.step} className="relative flex gap-3 pb-3 last:pb-0">
          {/* The rail joins the steps into one sequence; the last step ends it. */}
          {index < steps.length - 1 ? (
            <span
              aria-hidden
              className="absolute top-5 bottom-0 left-[7px] w-px bg-[var(--border)]"
            />
          ) : null}

          <span
            aria-hidden
            className={`mt-1 size-3.5 shrink-0 rounded-full ring-2 ring-[var(--surface)] ${dotClass(step)}`}
          />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <p className="text-[13px] font-medium">{step.decision}</p>
              <time
                className="tabular text-[11px] text-[var(--muted)]"
                dateTime={step.at}
                title={formatAbsolute(step.at, locale)}
              >
                {step.node.replace(/_/g, " ").toLowerCase()}
              </time>
            </div>

            {step.reason ? (
              <p className="mt-0.5 text-[12px] text-[var(--muted)]">{step.reason}</p>
            ) : null}

            <p className="tabular mt-1 text-[11px] text-[var(--muted)]">
              {budgetLine(step, t.sim.retriesBudget, t.sim.voiceBudget)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** A rule firing is the visual event in the trace; everything else is progress. */
function dotClass(step: TraceStep): string {
  if (step.rule) return "bg-[var(--stopped)]";
  if (step.outcome === "ESCALATED") return "bg-[var(--escalated)]";
  if (step.decision.toLowerCase().startsWith("recovered")) return "bg-[var(--recovered)]";
  return "bg-[var(--border)]";
}

function budgetLine(step: TraceStep, retriesLabel: string, voiceLabel: string): string {
  const b = step.allowed_at_this_moment;
  return [
    `${retriesLabel} ${b.retries_used}/${b.retries_cap}`,
    `${voiceLabel} ${b.voice_used}/${b.voice_cap}`,
  ].join(" · ");
}
