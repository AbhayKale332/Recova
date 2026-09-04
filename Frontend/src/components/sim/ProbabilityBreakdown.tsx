"use client";

import { useI18n } from "@/lib/i18n";
import { formatRatio } from "@/lib/format";
import type { Contribution } from "@/lib/simulation";

/**
 * How likely this case was to pay, and what moved that number.
 *
 * The model is a starting rate per (problem, playbook, channel), adjusted for
 * the case's own features. Contributions are leave-one-out, so they rank and
 * size the drivers but do not sum exactly to the difference from the base rate —
 * the copy says "adjustments" rather than implying an exact decomposition.
 */
export function ProbabilityBreakdown({
  p,
  baseRate,
  contributions,
}: {
  p: number;
  baseRate: number;
  contributions: Contribution[];
}) {
  const { t } = useI18n();
  const widest = Math.max(1, ...contributions.map((c) => Math.abs(c.delta_pp)));

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
          {t.sim.probabilityTitle}
        </h3>
        <span className="tabular text-[20px] font-semibold">{formatRatio(p)}</span>
      </div>

      <p className="tabular flex items-baseline justify-between gap-3 text-[12px] text-[var(--muted)]">
        <span>{t.sim.baseRate}</span>
        <span>{formatRatio(baseRate)}</span>
      </p>

      {contributions.length ? (
        <ul className="flex flex-col gap-1.5">
          {contributions.map((c) => (
            <li key={c.feature} className="flex flex-col gap-0.5">
              <div className="flex items-baseline justify-between gap-3 text-[12px]">
                <span className="min-w-0 truncate" title={c.detail}>
                  {c.detail}
                </span>
                <span
                  className={`tabular shrink-0 font-medium ${
                    c.delta_pp < 0 ? "text-[var(--lost)]" : "text-[var(--recovered)]"
                  }`}
                >
                  {c.delta_pp > 0 ? "+" : ""}
                  {c.delta_pp.toFixed(1)} pp
                </span>
              </div>
              {/* Bars are scaled to the largest effect in this case, so the top
                  driver is legible even when every effect is small. */}
              <div className="h-1 w-full rounded-full bg-[var(--border)]" aria-hidden>
                <div
                  className={`h-full rounded-full ${
                    c.delta_pp < 0 ? "bg-[var(--lost)]" : "bg-[var(--recovered)]"
                  }`}
                  style={{ width: `${(Math.abs(c.delta_pp) / widest) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-[11px] text-[var(--muted)]">{t.sim.modelNote}</p>
    </section>
  );
}
