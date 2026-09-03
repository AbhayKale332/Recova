"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatCount } from "@/lib/format";
import { TONE_FILL, type Tone } from "@/lib/status";
import type { Funnel, LifecycleStatus } from "@/lib/types";

/**
 * The six-segment funnel from /metrics. Selecting a segment filters the case
 * list below it.
 *
 * `at_risk` is the denominator and `intervened` counts cases the engine has
 * acted on at least once — neither maps to a single lifecycle status, so they
 * scope the list by "everything" and "worked" respectively. The four outcome
 * segments map straight to a status filter.
 */

export type FunnelKey = keyof Funnel;

/** How a segment scopes the case list. */
export const FUNNEL_STATUS: Partial<Record<FunnelKey, LifecycleStatus>> = {
  recovered: "RECOVERED",
  escalated: "ESCALATED",
  cancelled: "CANCELLED",
  failed: "FAILED",
};

const SEGMENTS: { key: FunnelKey; tone: Tone }[] = [
  { key: "at_risk", tone: "muted" },
  { key: "intervened", tone: "muted" },
  { key: "recovered", tone: "recovered" },
  { key: "escalated", tone: "escalated" },
  { key: "cancelled", tone: "stopped" },
  { key: "failed", tone: "lost" },
];

/** The segments that partition the outcome bar. `at_risk` is the whole; `intervened` overlaps. */
const BAR_SEGMENTS: { key: FunnelKey; tone: Tone }[] = SEGMENTS.filter(
  (s) => s.key !== "at_risk" && s.key !== "intervened",
);

export function FunnelBar({
  funnel,
  selected,
  onSelect,
}: {
  funnel: Funnel;
  selected: FunnelKey | null;
  onSelect: (key: FunnelKey | null) => void;
}) {
  const { t } = useI18n();
  const total = funnel.at_risk;

  if (total === 0) return null;

  // Anything not in a terminal state is still open; shown so the bar sums to 100%.
  const closed = funnel.recovered + funnel.escalated + funnel.cancelled + funnel.failed;
  const open = Math.max(0, total - closed);

  return (
    <section aria-labelledby="funnel-heading" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id="funnel-heading" className="text-[13px] font-semibold text-[var(--ink)]">
          {fillTemplate(t.console.funnelTitle, { count: formatCount(total) })}
        </h3>
        <p className="text-[12px] text-[var(--muted)]">
          {selected
            ? fillTemplate(t.console.funnelSelected, { label: t.funnel[selected] })
            : t.console.funnelHint}
        </p>
      </div>

      <div className="flex h-8 w-full overflow-hidden rounded ring-1 ring-[var(--border)] ring-inset">
        {BAR_SEGMENTS.map(({ key, tone }) => {
          const count = funnel[key];
          if (count === 0) return null;
          const pct = (count / total) * 100;
          const active = selected === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelect(active ? null : key)}
              aria-pressed={active}
              style={{ width: `${pct}%` }}
              title={`${t.funnel[key]} — ${formatCount(count)} (${pct.toFixed(1)}%)`}
              className={`group relative min-w-[2px] transition-opacity duration-150 ${TONE_FILL[tone]} ${
                selected && !active ? "opacity-35" : "opacity-100"
              } hover:opacity-90`}
            >
              <span className="sr-only">
                {t.funnel[key]}: {formatCount(count)}
              </span>
              {pct > 9 ? (
                <span
                  className="tabular pointer-events-none absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-white"
                  aria-hidden
                >
                  {formatCount(count)}
                </span>
              ) : null}
            </button>
          );
        })}
        {open > 0 ? (
          <div
            style={{ width: `${(open / total) * 100}%` }}
            className="min-w-[2px] bg-neutral-200"
            title={`${t.funnel.intervened} — ${formatCount(open)}`}
          />
        ) : null}
      </div>

      {/* The legend carries the numbers as text, so the bar is never the only
          way to read a value. `at_risk` and `intervened` sit here too. */}
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
        {SEGMENTS.map(({ key, tone }) => {
          const count = funnel[key];
          const selectable = key !== "at_risk";
          const active = selected === key;
          return (
            <li key={key}>
              <button
                type="button"
                disabled={!selectable}
                onClick={() => onSelect(active ? null : key)}
                aria-pressed={selectable ? active : undefined}
                className={`flex items-center gap-1.5 rounded px-1 py-0.5 text-[12px] transition-colors duration-150 ${
                  selectable ? "hover:bg-neutral-100" : "cursor-default"
                } ${active ? "bg-neutral-100 font-semibold" : ""}`}
              >
                <span
                  className={`size-2 shrink-0 rounded-full ${TONE_FILL[tone]}`}
                  aria-hidden
                />
                <span className="text-[var(--muted)]">{t.funnel[key]}</span>
                <span className="tabular font-semibold text-[var(--ink)]">
                  {formatCount(count)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
