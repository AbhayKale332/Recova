"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatCount, formatRatio } from "@/lib/format";
import { TONE_FILL, type Tone } from "@/lib/status";
import type { SimComplete } from "@/lib/simulation";

/**
 * What the batch does *not* show on its own: of N cases, how many production
 * would actually hand to the advisory model. The run keeps diagnosis
 * deterministic (see backend simulation/runner.py), so this is measured per
 * case by `simulation/triage.py` rather than by making the calls.
 *
 * `llm` is deliberately outside the lane bar — a case can consult the model and
 * still close on its own, so it overlaps every lane. The bar partitions the
 * book by *outcome*; the LLM figure sits above it as an annotation.
 */
const LANES: { key: "closed" | "human" | "postponed" | "in_flight"; tone: Tone }[] = [
  { key: "closed", tone: "recovered" },
  { key: "human", tone: "escalated" },
  { key: "postponed", tone: "inflight" },
  { key: "in_flight", tone: "muted" },
];

const LANE_LABEL = {
  closed: "laneClosed",
  human: "laneHuman",
  postponed: "lanePostponed",
  in_flight: "laneInFlight",
} as const;

export function RoutingBreakdown({ complete }: { complete: SimComplete }) {
  const { t } = useI18n();
  const r = complete.routing;
  if (!r || r.total === 0) return null;

  const modelNote =
    r.model_calls_made > 0
      ? fillTemplate(t.routing.madeNote, { count: formatCount(r.model_calls_made) })
      : fillTemplate(t.routing.savedNote, { count: formatCount(r.model_calls_saved) });

  const reasons = Object.entries(r.llm_reasons).sort((a, b) => b[1] - a[1]);

  return (
    <section aria-labelledby="routing-heading" className="flex flex-col gap-4">
      <div className="min-w-0">
        <h3 id="routing-heading" className="text-[13px] font-semibold text-[var(--ink)]">
          {t.routing.title}
        </h3>
        <p className="mt-0.5 max-w-[64ch] text-[12px] text-[var(--muted)]">{t.routing.subtitle}</p>
      </div>

      {/* The headline: how many need the model, and what that saved. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
            {t.routing.llmLabel}
          </p>
          <p className="tabular mt-0.5 flex items-baseline gap-2">
            <span className="text-[32px] leading-none font-semibold tracking-tight text-[var(--accent-ink)]">
              {formatCount(r.llm)}
            </span>
            <span className="text-[13px] text-[var(--muted)]">
              {fillTemplate(t.routing.share, { pct: formatRatio(r.llm_share) })}
            </span>
          </p>
          <p className="tabular mt-1 text-[12px] text-[var(--muted)]">{modelNote}</p>
        </div>

        <p className="tabular text-[13px] text-[var(--ink)]">
          <span className="font-semibold">{formatCount(r.deterministic_only)}</span>{" "}
          <span className="text-[var(--muted)]">{t.routing.deterministicLabel.toLowerCase()}</span>
        </p>
      </div>

      <p className="text-[11px] text-[var(--muted)]">{t.routing.overlapNote}</p>

      {/* Outcome lanes — these partition the book and sum to the total. */}
      <div className="flex h-8 w-full overflow-hidden rounded ring-1 ring-[var(--border)] ring-inset">
        {LANES.map(({ key, tone }) => {
          const count = r[key];
          if (count === 0) return null;
          const pct = (count / r.total) * 100;
          return (
            <div
              key={key}
              style={{ width: `${pct}%` }}
              title={`${t.routing[LANE_LABEL[key]]} — ${formatCount(count)} (${pct.toFixed(1)}%)`}
              className={`relative min-w-[2px] ${TONE_FILL[tone]}`}
            >
              {pct > 9 ? (
                <span
                  className="tabular pointer-events-none absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-white"
                  aria-hidden
                >
                  {formatCount(count)}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
        {LANES.map(({ key, tone }) => (
          <li key={key} className="flex items-center gap-1.5 text-[12px]">
            <span className={`size-2 shrink-0 rounded-full ${TONE_FILL[tone]}`} aria-hidden />
            <span className="text-[var(--muted)]">{t.routing[LANE_LABEL[key]]}</span>
            <span className="tabular font-semibold text-[var(--ink)]">{formatCount(r[key])}</span>
          </li>
        ))}
      </ul>

      {reasons.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-medium text-[var(--muted)]">{t.routing.reasonsLabel}</p>
          <ul className="flex flex-wrap gap-1.5">
            {reasons.map(([reason, count]) => (
              <li
                key={reason}
                className="tabular rounded border border-[var(--border)] bg-[var(--accent-wash)] px-1.5 py-0.5 text-[11px] text-[var(--accent-ink)]"
              >
                {reason} · {formatCount(count)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
