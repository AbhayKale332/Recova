"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { describeError, useApi, useMutation } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fillTemplate } from "@/lib/i18n";
import { useToast } from "@/components/Toast";
import type { Metrics } from "@/lib/types";

/**
 * One /metrics fetch for the whole console: the top bar reads it, zone 1 reads
 * it, and the live run hands back fresh metrics on `complete` so a recovery
 * updates the hero number without a refetch.
 */

interface ConsoleValue {
  metrics: Metrics | null;
  error: Error | null;
  isInitialLoad: boolean;
  isRefreshing: boolean;
  /** The database is empty — every surface offers seeding instead of a blank page. */
  unseeded: boolean;
  refresh: () => void;
  /** Apply metrics that arrived over the SSE run rather than refetching. */
  applyMetrics: (metrics: Metrics) => void;
  seed: () => void;
  seeding: boolean;
}

const ConsoleContext = createContext<ConsoleValue | null>(null);

export function ConsoleProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const toast = useToast();
  const [override, setOverride] = useState<Metrics | null>(null);

  const fetchMetrics = useCallback((signal: AbortSignal) => api.metrics(signal), []);
  const state = useApi<Metrics>(fetchMetrics);

  const seedMutation = useMutation(api.seed);

  const refresh = useCallback(() => {
    setOverride(null);
    state.refresh();
  }, [state]);

  const seed = useCallback(async () => {
    const result = await seedMutation.run();
    if (result.ok) {
      toast.success(
        fillTemplate(t.errors.seedOk, { count: result.data.seeded }),
        Object.entries(result.data.by_state)
          .map(([key, value]) => `${key} ${value}`)
          .join(" · "),
      );
      refresh();
    } else {
      toast.failure(t.errors.seedFailed, describeError(result.error));
    }
  }, [seedMutation, toast, t, refresh]);

  // A fresher payload from the SSE run wins over the last fetch.
  const metrics = override ?? state.data;

  const value = useMemo<ConsoleValue>(
    () => ({
      metrics,
      error: state.error,
      isInitialLoad: state.isInitialLoad,
      isRefreshing: state.isRefreshing,
      unseeded: state.phase === "success" && (metrics?.counts.total ?? 0) === 0,
      refresh,
      applyMetrics: setOverride,
      seed,
      seeding: seedMutation.pending,
    }),
    [
      metrics,
      state.error,
      state.isInitialLoad,
      state.isRefreshing,
      state.phase,
      refresh,
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
