"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useConsole } from "@/components/console/ConsoleContext";
import { FunnelBar, FUNNEL_STATUS, type FunnelKey } from "@/components/console/FunnelBar";
import { SummarySentence } from "@/components/console/SummarySentence";
import { EmptyState } from "@/components/States";
import { CaseFilters, EMPTY_FILTERS, type CaseFilterState } from "@/components/sim/CaseFilters";
import { CasePanel } from "@/components/sim/CasePanel";
import { CaseTable } from "@/components/sim/CaseTable";
import { ProjectionPanel } from "@/components/sim/ProjectionPanel";
import { RunProgress } from "@/components/sim/RunProgress";
import { ScenarioForm } from "@/components/sim/ScenarioForm";
import { useI18n } from "@/lib/i18n";
import type { Funnel } from "@/lib/types";

/**
 * The console: describe a book of at-risk payments, run it through the real
 * engine, read what it recovered and where it stopped itself.
 *
 * Zone 1 (the batch evidence) is now the *result* of that run rather than a
 * fetch, zone 2 lists the cases the run produced, and zone 3 opens one of them
 * as a right-hand panel via `?case=`.
 */
export function ConsoleScreen() {
  const { t } = useI18n();
  const {
    scenario,
    setScenario,
    savedScenarios,
    applySavedScenario,
    saveScenario,
    deleteScenario,
    policy,
    run,
    start,
    seed,
    seeding,
  } = useConsole();

  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("case");

  const [filters, setFilters] = useState<CaseFilterState>(EMPTY_FILTERS);
  const [funnelSelection, setFunnelSelection] = useState<FunnelKey | null>(null);

  const running = run.phase === "running";

  const select = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (id) next.set("case", id);
      else next.delete("case");
      const qs = next.toString();
      router.replace(qs ? `/console?${qs}` : "/console", { scroll: false });
    },
    [params, router],
  );

  // The funnel and the filter bar both scope the same list, so a funnel segment
  // is folded into the filter state rather than applied as a second pass.
  const statusFromFunnel = funnelSelection ? FUNNEL_STATUS[funnelSelection] : undefined;

  const visible = useMemo(() => {
    const needle = filters.q.trim().toLowerCase();
    return run.cases.filter((row) => {
      if (filters.failureClass && row.failure_class !== filters.failureClass) return false;
      if (filters.status && row.final_state !== filters.status) return false;
      if (statusFromFunnel && row.final_state !== statusFromFunnel) return false;
      if (funnelSelection === "intervened" && !row.stopped_by && row.final_state === "PENDING") {
        return false;
      }
      if (!needle) return true;
      return (
        row.customer_name.toLowerCase().includes(needle) ||
        row.transaction_id.toLowerCase().includes(needle)
      );
    });
  }, [run.cases, filters, statusFromFunnel, funnelSelection]);

  const selectedCase = useMemo(
    () => run.cases.find((row) => row.transaction_id === selectedId) ?? null,
    [run.cases, selectedId],
  );

  return (
    <div className="flex flex-col gap-5">
      <section
        aria-labelledby="scenario-heading"
        className="flex flex-col gap-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5"
      >
        <div className="min-w-0">
          <h2 id="scenario-heading" className="text-[15px] font-semibold tracking-tight">
            {t.sim.title}
          </h2>
          <p className="mt-0.5 max-w-[64ch] text-[13px] text-[var(--muted)]">{t.sim.subtitle}</p>
        </div>

        <ScenarioForm
          scenario={scenario}
          onChange={setScenario}
          savedScenarios={savedScenarios}
          onSavedScenario={applySavedScenario}
          onSaveScenario={saveScenario}
          onDeleteScenario={deleteScenario}
          disabled={running}
        />
      </section>

      {run.start ? (
        <section
          aria-labelledby="run-heading"
          className="flex flex-col gap-5 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5"
        >
          <h2 id="run-heading" className="sr-only">
            {t.console.batchEvidence}
          </h2>

          <RunProgress
            start={run.start}
            progress={run.progress}
            throughput={run.complete?.throughput ?? null}
            running={running}
          />

          {run.complete ? (
            <>
              <SummarySentence metrics={run.complete.metrics} />
              <ProjectionPanel complete={run.complete} />
              <FunnelBar
                funnel={run.complete.funnel as unknown as Funnel}
                selected={funnelSelection}
                onSelect={setFunnelSelection}
              />
            </>
          ) : null}
        </section>
      ) : (
        <EmptyState
          title={t.sim.idleTitle}
          body={t.sim.idleBody}
          action={
            <button
              type="button"
              onClick={seed}
              disabled={seeding}
              className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[13px] font-medium disabled:opacity-60"
            >
              {seeding ? t.actions.seeding : t.actions.seed}
            </button>
          }
        />
      )}

      {run.cases.length ? (
        <section
          aria-labelledby="cases-heading"
          className="flex flex-col gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5"
        >
          <h2 id="cases-heading" className="text-[15px] font-semibold tracking-tight">
            {t.sim.casesFromRun}
          </h2>

          <CaseFilters
            filters={filters}
            shown={visible.length}
            total={run.cases.length}
            onChange={setFilters}
          />

          <CaseTable cases={visible} selectedId={selectedId} onSelect={select} />
        </section>
      ) : null}

      <CasePanel simCase={selectedCase} policy={policy} onClose={() => select(null)} />

      {/* The run controls live at the bottom of the console: describe the book
       * above, then run it from here. Sticky so it stays reachable while the
       * scenario form and results scroll. */}
      <div className="sticky bottom-0 z-20 -mx-3 mt-1 flex items-center justify-end gap-3 border-t border-[var(--border)] bg-[var(--bg)]/95 px-3 py-3 backdrop-blur sm:-mx-4 sm:px-4">
        {running ? (
          <button
            type="button"
            onClick={run.stop}
            className="rounded-md border border-[var(--border)] px-4 py-2 text-[15px] font-medium"
          >
            {t.sim.stop}
          </button>
        ) : null}
        <button
          type="button"
          onClick={start}
          disabled={running}
          className="rounded-md bg-[var(--accent)] px-5 py-2 text-[15px] font-semibold text-white transition-opacity duration-150 disabled:opacity-60"
        >
          {running ? t.sim.running : run.complete ? t.sim.again : t.sim.run}
        </button>
      </div>
    </div>
  );
}
