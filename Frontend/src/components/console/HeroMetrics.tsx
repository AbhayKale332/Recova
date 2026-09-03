"use client";

import type { ReactNode } from "react";

import { Money } from "@/components/Money";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatDuration, formatMoneyCompact, formatRatio } from "@/lib/format";
import type { Metrics } from "@/lib/types";

/**
 * Money leads, not the rate (Vision §4, pillar 1). `recovered_inr` is the only
 * figure at display size; GRRR, TTR, in-flight and lost support it.
 */
export function HeroMetrics({ metrics }: { metrics: Metrics }) {
  const { t } = useI18n();

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
          {t.console.heroLabel}
        </p>
        <Money
          value={metrics.recovered_inr}
          compact
          className="mt-0.5 block text-[44px] leading-none font-semibold tracking-tight text-[var(--recovered)] sm:text-[56px]"
        />
        {/* The denominator: never larger than the numerator. */}
        <p className="tabular mt-1.5 text-[13px] text-[var(--muted)]">
          {fillTemplate(t.console.ofAtRisk, {
            amount: formatMoneyCompact(metrics.at_risk_inr),
          })}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 lg:gap-x-8">
        <Stat label={t.console.grrrShort} hint={t.console.grrr} value={formatRatio(metrics.grrr)} />
        <Stat
          label={t.console.avgTtrShort}
          hint={t.console.avgTtr}
          value={formatDuration(metrics.avg_time_to_recovery_seconds)}
        />
        <Stat
          label={t.console.inFlight}
          hint={t.console.inFlightHint}
          value={<Money value={metrics.in_flight_inr} compact />}
          tone="text-[var(--inflight)]"
        />
        <Stat
          label={t.console.lost}
          hint={t.console.lostHint}
          value={<Money value={metrics.lost_inr} compact />}
          tone="text-[var(--lost)]"
        />
      </dl>
    </div>
  );
}

function Stat({
  label,
  hint,
  value,
  tone = "text-[var(--ink)]",
}: {
  label: string;
  hint: string;
  value: ReactNode;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[12px] text-[var(--muted)]" title={hint}>
        {label}
      </dt>
      <dd className={`tabular mt-0.5 text-[20px] font-semibold ${tone}`}>{value}</dd>
    </div>
  );
}
