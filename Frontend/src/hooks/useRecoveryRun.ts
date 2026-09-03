"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { runStreamUrl } from "@/lib/api";
import type { Locale } from "@/lib/i18n/dictionaries/en";
import type { ConversationMessage, LifecycleStatus, Metrics } from "@/lib/types";

/**
 * EventSource wrapper for GET /transactions/{id}/run.
 *
 * Event names come from backend/application/operations/live_recovery.py:
 *   start · step · diagnosis · typing · message · call · status · complete
 */

export interface RunStart {
  transaction_id: string;
  failure_class: number;
  amount_inr: number;
  customer_name: string;
}

export interface RunDiagnosis {
  root_cause: string;
  playbook: string;
  confidence: number;
}

export type RunStepPhase =
  | "flagged"
  | "stopped"
  | "escalated"
  | "waiting"
  | "calling";

export interface RunStep {
  phase: RunStepPhase;
  label?: string;
  rule?: string;
  p2p_date?: string;
}

export interface RunCall {
  id: number;
  duration_sec: number;
  turns: number;
}

export type RunEvent =
  | { kind: "start"; at: number; data: RunStart }
  | { kind: "step"; at: number; data: RunStep }
  | { kind: "diagnosis"; at: number; data: RunDiagnosis }
  | { kind: "message"; at: number; data: ConversationMessage }
  | { kind: "call"; at: number; data: RunCall }
  | { kind: "status"; at: number; data: { final_state: LifecycleStatus } };

export type RunPhase = "idle" | "connecting" | "streaming" | "done" | "error";

export interface RecoveryRun {
  phase: RunPhase;
  events: RunEvent[];
  /** Whose turn indicator is showing, cleared by the next real event. */
  typing: "agent" | "customer" | null;
  diagnosis: RunDiagnosis | null;
  start: RunStart | null;
  finalState: LifecycleStatus | null;
  /** Fresh metrics the backend sends with `complete` — no refetch needed. */
  metrics: Metrics | null;
  error: string | null;
  run: () => void;
  stop: () => void;
  reset: () => void;
}

function parse<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function useRecoveryRun(
  transactionId: string | null,
  locale: Locale,
): RecoveryRun {
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [typing, setTyping] = useState<"agent" | "customer" | null>(null);
  const [diagnosis, setDiagnosis] = useState<RunDiagnosis | null>(null);
  const [start, setStart] = useState<RunStart | null>(null);
  const [finalState, setFinalState] = useState<LifecycleStatus | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceRef = useRef<EventSource | null>(null);
  /** Set once `complete` arrives, so the socket closing isn't reported as a failure. */
  const completedRef = useRef(false);

  const close = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  useEffect(() => close, [close]);

  // A different case means a different run; never show one case's steps under
  // another. Cleared during render (React's "adjust state when props change"),
  // with the socket torn down by the effect's cleanup below.
  const [seenId, setSeenId] = useState(transactionId);
  if (seenId !== transactionId) {
    setSeenId(transactionId);
    setPhase("idle");
    setEvents([]);
    setTyping(null);
    setDiagnosis(null);
    setStart(null);
    setFinalState(null);
    setMetrics(null);
    setError(null);
  }

  useEffect(() => {
    completedRef.current = false;
    // Closing on unmount *and* whenever the case changes, so a stream for the
    // previously selected case can never emit into the new one.
    return close;
  }, [transactionId, close]);

  const reset = useCallback(() => {
    close();
    completedRef.current = false;
    setPhase("idle");
    setEvents([]);
    setTyping(null);
    setDiagnosis(null);
    setStart(null);
    setFinalState(null);
    setMetrics(null);
    setError(null);
  }, [close]);

  const stop = useCallback(() => {
    close();
    setTyping(null);
    setPhase((current) => (current === "streaming" || current === "connecting" ? "done" : current));
  }, [close]);

  const run = useCallback(() => {
    if (!transactionId) return;
    close();
    completedRef.current = false;
    setEvents([]);
    setTyping(null);
    setDiagnosis(null);
    setStart(null);
    setFinalState(null);
    setMetrics(null);
    setError(null);
    setPhase("connecting");

    const source = new EventSource(runStreamUrl(transactionId, locale));
    sourceRef.current = source;

    const push = (event: RunEvent) => {
      setPhase("streaming");
      setTyping(null);
      setEvents((prev) => [...prev, event]);
    };

    source.addEventListener("start", (e) => {
      const data = parse<RunStart>((e as MessageEvent<string>).data);
      if (!data) return;
      setStart(data);
      push({ kind: "start", at: Date.now(), data });
    });

    source.addEventListener("step", (e) => {
      const data = parse<RunStep>((e as MessageEvent<string>).data);
      if (data) push({ kind: "step", at: Date.now(), data });
    });

    source.addEventListener("diagnosis", (e) => {
      const data = parse<RunDiagnosis>((e as MessageEvent<string>).data);
      if (!data) return;
      setDiagnosis(data);
      push({ kind: "diagnosis", at: Date.now(), data });
    });

    source.addEventListener("typing", (e) => {
      const data = parse<{ who: "agent" | "customer" }>((e as MessageEvent<string>).data);
      setPhase("streaming");
      setTyping(data?.who ?? null);
    });

    source.addEventListener("message", (e) => {
      const data = parse<ConversationMessage>((e as MessageEvent<string>).data);
      if (data) push({ kind: "message", at: Date.now(), data });
    });

    source.addEventListener("call", (e) => {
      const data = parse<RunCall>((e as MessageEvent<string>).data);
      if (data) push({ kind: "call", at: Date.now(), data });
    });

    source.addEventListener("status", (e) => {
      const data = parse<{ final_state: LifecycleStatus }>((e as MessageEvent<string>).data);
      if (!data) return;
      setFinalState(data.final_state);
      push({ kind: "status", at: Date.now(), data });
    });

    source.addEventListener("complete", (e) => {
      const data = parse<{ final_state: LifecycleStatus; metrics: Metrics }>(
        (e as MessageEvent<string>).data,
      );
      if (data) {
        setFinalState(data.final_state);
        setMetrics(data.metrics);
      }
      completedRef.current = true;
      setTyping(null);
      setPhase("done");
      close();
    });

    // EventSource reports every transport failure the same way and would
    // reconnect on its own, replaying the whole run. Close it and say so.
    source.addEventListener("error", () => {
      if (completedRef.current) return;
      close();
      setTyping(null);
      setPhase("error");
      setError(
        `The live run stream to ${runStreamUrl(transactionId, locale)} closed before it finished.`,
      );
    });
  }, [transactionId, locale, close]);

  return {
    phase,
    events,
    typing,
    diagnosis,
    start,
    finalState,
    metrics,
    error,
    run,
    stop,
    reset,
  };
}
