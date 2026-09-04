"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { streamSimulation, isAbort } from "@/lib/api";
import type {
  Scenario,
  SimCase,
  SimComplete,
  SimProgress,
  SimStart,
} from "@/lib/simulation";

/**
 * Drives POST /simulate/batch and holds the state of one run.
 *
 * Modelled on useRecoveryRun, with two differences the volume forces:
 *
 * 1. It reads the POST body stream rather than using EventSource, because a
 *    scenario is a nested object (see `streamSimulation`).
 * 2. Cases are accumulated in a ref and flushed to state on a frame, not on
 *    every event. At ~65 cases/sec a setState per case would re-render the table
 *    hundreds of times and make the throughput readout measure React instead of
 *    the engine.
 */

export type SimPhase = "idle" | "running" | "done" | "error";

export interface SimulationRun {
  phase: SimPhase;
  scenario: Scenario | null;
  start: SimStart | null;
  progress: SimProgress | null;
  cases: SimCase[];
  complete: SimComplete | null;
  error: string | null;
  run: (scenario: Scenario, concurrency?: number) => void;
  stop: () => void;
  reset: () => void;
}

export function useSimulationRun(): SimulationRun {
  const [phase, setPhase] = useState<SimPhase>("idle");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [start, setStart] = useState<SimStart | null>(null);
  const [progress, setProgress] = useState<SimProgress | null>(null);
  const [cases, setCases] = useState<SimCase[]>([]);
  const [complete, setComplete] = useState<SimComplete | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const bufferRef = useRef<SimCase[]>([]);
  const frameRef = useRef<number | null>(null);

  const cancelFrame = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  /** Move whatever has arrived since the last paint into state, once. */
  const flush = useCallback(() => {
    frameRef.current = null;
    if (!bufferRef.current.length) return;
    const batch = bufferRef.current;
    bufferRef.current = [];
    setCases((current) => [...current, ...batch]);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(flush);
  }, [flush]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    cancelFrame();
  }, [cancelFrame]);

  // A run outliving its screen would keep streaming into nothing.
  useEffect(() => stop, [stop]);

  const reset = useCallback(() => {
    stop();
    bufferRef.current = [];
    setPhase("idle");
    setStart(null);
    setProgress(null);
    setCases([]);
    setComplete(null);
    setError(null);
  }, [stop]);

  const run = useCallback(
    (next: Scenario, concurrency = 8) => {
      stop();
      bufferRef.current = [];
      const controller = new AbortController();
      abortRef.current = controller;

      setScenario(next);
      setPhase("running");
      setStart(null);
      setProgress(null);
      setCases([]);
      setComplete(null);
      setError(null);

      void (async () => {
        try {
          for await (const { event, data } of streamSimulation(next, {
            concurrency,
            signal: controller.signal,
          })) {
            switch (event) {
              case "start":
                setStart(data as SimStart);
                break;
              case "progress":
                setProgress(data as SimProgress);
                break;
              case "case":
                bufferRef.current.push(data as SimCase);
                scheduleFlush();
                break;
              case "complete":
                flush();
                setComplete(data as SimComplete);
                setPhase("done");
                break;
              default:
                break;
            }
          }
          // The stream can end without `complete` if the user stopped it.
          setPhase((current) => (current === "running" ? "idle" : current));
        } catch (caught) {
          if (isAbort(caught) || controller.signal.aborted) return;
          setError(caught instanceof Error ? caught.message : String(caught));
          setPhase("error");
        } finally {
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [flush, scheduleFlush, stop],
  );

  return { phase, scenario, start, progress, cases, complete, error, run, stop, reset };
}
