"use client";

import { Money } from "@/components/Money";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatCount, formatMoneyCompact, formatRatio } from "@/lib/format";
import type { SimComplete } from "@/lib/simulation";

/**
 * The result of a run. Money leads (Vision §4, pillar 1) — the rate is never the
 * biggest thing on screen.
 *
 * Three figures, kept visually distinct because they mean different things and
 * do not add up:
 *   Recovered  measured; the engine drove these cases to settlement
 *   Deferred   held by a rule that defers rather than stops; not lost
 *   Projected  modelled expected recovery with a 95% band; not money that moved
 */
export function ProjectionPanel({ complete }: { complete: SimComplete }) {
  const { t } = useI18n();
  const [low, high] = complete.projected_band;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
            {t.sim.measured}
          </p>
          <Money
            value={complete.recovered_inr}
            compact
            className="mt-0.5 block text-[44px] leading-none font-semibold tracking-tight text-[var(--recovered)] sm:text-[56px]"
          />
          <p className="tabular mt-1.5 text-[13px] text-[var(--muted)]">
            {fillTemplate(t.console.ofAtRisk, {
              amount: formatMoneyCompact(complete.at_risk_inr),
            })}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 lg:gap-x-8">
          <Stat
            label={t.sim.projected}
            hint={t.sim.projectedHint}
            value={<Money value={complete.projected_inr} compact />}
            /* The band is what makes this readable as an estimate rather than a
               claim, so it sits directly under the figure. */
            note={fillTemplate(t.sim.band, {
              low: formatMoneyCompact(low),
              high: formatMoneyCompact(high),
            })}
          />
          <Stat
            label={t.sim.deferred}
            hint={t.sim.deferredHint}
            value={<Money value={complete.deferred_inr} compact />}
            tone="text-[var(--inflight)]"
            note={
              complete.counts.waiting
                ? `${formatCount(complete.counts.waiting)} ${t.summary.caseWordPlural}`
                : undefined
            }
          />
          <Stat
            label={t.console.grrrShort}
            hint={t.console.grrr}
            value={formatRatio(complete.grrr)}
          />
          <Stat
            label={t.funnel.escalated}
            hint={t.statusMeaning.ESCALATED}
            value={formatCount(complete.counts.escalated)}
            tone="text-[var(--escalated)]"
            note={`${formatCount(complete.counts.stopped)} ${t.funnel.cancelled.toLowerCase()}`}
          />
        </dl>
      </div>

      <p className="text-[12px] text-[var(--muted)]">{t.sim.notAdditive}</p>
    </div>
  );
}

function Stat({
  label,
  hint,
  value,
  note,
  tone = "text-[var(--ink)]",
}: {
  label: string;
  hint: string;
  value: React.ReactNode;
  note?: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[12px] text-[var(--muted)]" title={hint}>
        {label}
      </dt>
      <dd className={`tabular mt-0.5 text-[20px] font-semibold ${tone}`}>{value}</dd>
      {note ? <p className="tabular mt-0.5 text-[11px] text-[var(--muted)]">{note}</p> : null}
    </div>
  );
}
