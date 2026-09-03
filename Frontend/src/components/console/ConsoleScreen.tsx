"use client";

import { useState } from "react";

import { useConsole } from "@/components/console/ConsoleContext";
import { FunnelBar, type FunnelKey } from "@/components/console/FunnelBar";
import { HeroMetrics } from "@/components/console/HeroMetrics";
import { SummarySentence } from "@/components/console/SummarySentence";
import { ErrorState, LoadingState, UnseededState } from "@/components/States";
import { useI18n } from "@/lib/i18n";

export function ConsoleScreen() {
  const { t } = useI18n();
  const { metrics, error, isInitialLoad, unseeded, refresh, seed, seeding } = useConsole();

  // Zone 1 owns the funnel selection; zones 2–3 will consume it as a filter.
  const [funnelSelection, setFunnelSelection] = useState<FunnelKey | null>(null);

  if (isInitialLoad) return <LoadingState rows={5} />;
  if (error) return <ErrorState error={error} onRetry={refresh} />;
  if (unseeded) return <UnseededState onSeed={seed} seeding={seeding} />;
  if (!metrics) return <LoadingState rows={5} />;

  return (
    <div className="flex flex-col gap-5">
      <section
        aria-labelledby="batch-evidence"
        className="flex flex-col gap-5 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5"
      >
        <h2 id="batch-evidence" className="sr-only">
          {t.console.batchEvidence}
        </h2>

        <SummarySentence metrics={metrics} />
        <HeroMetrics metrics={metrics} />
        <FunnelBar
          funnel={metrics.funnel}
          selected={funnelSelection}
          onSelect={setFunnelSelection}
        />
      </section>
    </div>
  );
}
