"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";


import { describeError, useApi, useMutation } from "@/hooks/useApi";
import { useSimulationRun, type SimulationRun } from "@/hooks/useSimulationRun";
import { api } from "@/lib/api";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { decodeScenario, defaultScenario, type SavedScenario, type Scenario, type ScenarioPreset } from "@/lib/simulation";
import { useToast } from "@/components/Toast";
import type { PolicyResponse } from "@/lib/types";

/**
 * The console's state is a *run*, not a fetch.
 *
 * It used to hold one GET /metrics, which meant the first screen showed money
 * that was already in the database — indistinguishable from a hardcoded figure.
 * Now the user describes a scenario, the engine works it, and every number on
 * screen is the output of that run.
 *
 * The seeded batch is still reachable: /console/guardrails and /console/audit
 * read the real book, so `seed` stays here for them.
 */

interface ConsoleValue {
  scenario: Scenario;
  setScenario: (next: Scenario) => void;
  presets: ScenarioPreset[];
  applyPreset: (preset: ScenarioPreset) => void;
  savedScenarios: SavedScenario[];
  applySavedScenario: (saved: SavedScenario) => void;
  saveScenario: () => void;
  deleteScenario: (slug: string) => void;
  concurrency: number;
  setConcurrency: (next: number) => void;
  /** Policy is read once for the bounds gauge's channel list. */
  policy: PolicyResponse | null;
  run: SimulationRun;
  start: () => void;
  seed: () => void;
  seeding: boolean;
}

const ConsoleContext = createContext<ConsoleValue | null>(null);

export function ConsoleProvider({ children }: { children: ReactNode }) {
  const { t, locale } = useI18n();
  const toast = useToast();

  const [scenario, setScenario] = useState<Scenario>(() => defaultScenario(locale));
  const [concurrency, setConcurrency] = useState(8);
  const run = useSimulationRun();

  const fetchPolicy = useCallback((signal: AbortSignal) => api.policy(signal), []);
  const policyState = useApi<PolicyResponse>(fetchPolicy);

  const fetchPresets = useCallback((signal: AbortSignal) => api.scenarios(signal), []);
  const presetState = useApi<{ presets: ScenarioPreset[]; saved: SavedScenario[] }>(fetchPresets);

  const applyPreset = useCallback(
    (preset: ScenarioPreset) => setScenario(preset.scenario),
    [],
  );

  const applySavedScenario = useCallback((saved: SavedScenario) => setScenario(saved.payload), []);

  useEffect(() => {
    const encoded = new URLSearchParams(window.location.search).get("s");
    if (!encoded) return;
    const shared = decodeScenario(encoded);
    if (!shared) return;
    const timer = window.setTimeout(() => setScenario(shared), 0);
    return () => window.clearTimeout(timer);
  }, []);

  // The locale is stamped on at launch rather than mirrored into scenario state.
  // The backend drafts outreach in it, so it has to travel with the request
  // (Vision §9) — but syncing it into state on every toggle would only be a
  // second copy that can go stale.
  const start = useCallback(
    () => run.run({ ...scenario, locale }, concurrency),
    [run, scenario, locale, concurrency],
  );

  const saveMutation = useMutation(api.saveScenario);
  const deleteMutation = useMutation(api.deleteScenario);

  const saveScenario = useCallback(async () => {
    const slug = scenario.name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 80) || "custom-scenario";
    const result = await saveMutation.run({
      slug,
      name: scenario.name.trim() || "Custom scenario",
      description: scenario.description,
      payload: scenario,
    });
    if (result.ok) {
      presetState.refresh();
      toast.success(t.sim.savedTitle, result.data.name);
    } else {
      toast.failure(t.sim.saveFailed, describeError(result.error));
    }
  }, [presetState, saveMutation, scenario, t.sim, toast]);

  const deleteScenario = useCallback(async (slug: string) => {
    const result = await deleteMutation.run(slug);
    if (result.ok) {
      presetState.refresh();
      toast.success(t.sim.deletedTitle);
    } else {
      toast.failure(t.sim.deleteFailed, describeError(result.error));
    }
  }, [deleteMutation, presetState, t.sim, toast]);

  const seedMutation = useMutation(api.seed);
  const seed = useCallback(async () => {
    const result = await seedMutation.run();
    if (result.ok) {
      toast.success(fillTemplate(t.errors.seedOk, { count: result.data.seeded }));
    } else {
      toast.failure(t.errors.seedFailed, describeError(result.error));
    }
  }, [seedMutation, toast, t]);

  // A failed run is the one thing here the user cannot see any other way.
  useEffect(() => {
    if (run.phase === "error" && run.error) toast.failure(t.batch.failureTitle, run.error);
  }, [run.phase, run.error, toast, t]);

  const value = useMemo<ConsoleValue>(
    () => ({
      scenario,
      setScenario,
      presets: presetState.data?.presets ?? [],
      applyPreset,
      savedScenarios: presetState.data?.saved ?? [],
      applySavedScenario,
      saveScenario,
      deleteScenario,
      concurrency,
      setConcurrency,
      policy: policyState.data,
      run,
      start,
      seed,
      seeding: seedMutation.pending,
    }),
    [
      scenario,
      presetState.data,
      applyPreset,
      applySavedScenario,
      saveScenario,
      deleteScenario,
      concurrency,
      policyState.data,
      run,
      start,
      seed,
      seedMutation.pending,
    ],
  );

  return <ConsoleContext.Provider value={value}>{children}</ConsoleContext.Provider>;
}

export function useConsole(): ConsoleValue {
  const value = useContext(ConsoleContext);
  if (!value) throw new Error("useConsole must be used inside <ConsoleProvider>");
  return value;
}
