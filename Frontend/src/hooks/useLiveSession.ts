"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, isAbort, liveSessionStreamUrl } from "@/lib/api";
import type { Bounds } from "@/lib/bounds";
import type { Channel, StoppingRule } from "@/lib/types";
import type {
  LiveBoundsWire,
  LiveCallOffer,
  LiveDecision,
  LiveDiagnosis,
  LiveDispatchEvent,
  LiveReminder,
  LiveStart,
  LiveStep,
  RouteDecision,
} from "@/lib/simulation";
import type { ConversationMessage, LifecycleStatus, Metrics, PaymentArtifact } from "@/lib/types";

/**
 * GET /api/v1/live/sessions/{id}/stream, plus the `reply` POST action.
 *
 * Modelled on useRecoveryRun: the live stream is a plain GET with no request
 * body, so EventSource is the right transport, same reasoning as that hook.
 * This is deliberately *not* useSimulationRun's pattern (reading the POST
 * body stream by hand) — that hook only exists because a scenario is a nested
 * object EventSource has no way to send; the live session is created first
 * via a separate POST, and the stream itself takes no body. There is also no
 * volume problem here (a handful of events per human turn, not ~65 cases/sec),
 * so unlike useSimulationRun this hook does not batch state updates onto a
 * frame — each event can just set state directly.
 *
 * Event names come from backend/application/operations/live_session.py:
 *   start · step · diagnosis · route · decision · typing · message ·
 *   dispatch · artifact · call_offer · bounds · status · complete
 */

export type LivePhase = "idle" | "connecting" | "streaming" | "done" | "error";

export type LiveTurnEvent =
  | { kind: "start"; at: number; data: LiveStart }
  | { kind: "step"; at: number; data: LiveStep }
  | { kind: "diagnosis"; at: number; data: LiveDiagnosis }
  | { kind: "route"; at: number; data: RouteDecision }
  | { kind: "decision"; at: number; data: LiveDecision }
  | { kind: "message"; at: number; data: ConversationMessage }
  | { kind: "dispatch"; at: number; data: LiveDispatchEvent }
  | { kind: "reminder"; at: number; data: LiveReminder }
  | { kind: "artifact"; at: number; data: PaymentArtifact }
  | { kind: "call_offer"; at: number; data: LiveCallOffer }
  | { kind: "status"; at: number; data: { final_state: LifecycleStatus } }
  | { kind: "complete"; at: number; data: { final_state: LifecycleStatus; metrics: Metrics } };

export interface LiveSessionState {
  phase: LivePhase;
  /** Every event in order, for AuditTicker — a live projection of the same
   * audit rows the backend wrote alongside each one. */
  events: LiveTurnEvent[];
  start: LiveStart | null;
  diagnosis: LiveDiagnosis | null;
  /**
   * The most recent route decision. Before the human's first reply this is
   * the opening's seeded route (`provider: "deterministic"`) carried inside
   * `decision.route_decision` — never a claimed provider call. RouterChip
   * reads `provider === "deterministic"` to render that turn visibly
   * differently from a real, taken one.
   */
  route: RouteDecision | null;
  decision: LiveDecision | null;
  typing: "agent" | "customer" | null;
  messages: ConversationMessage[];
  dispatch: LiveDispatchEvent | null;
  /** The most recent calendar reminder booked from the conversation, or null. */
  reminder: LiveReminder | null;
  /** The most recently minted payment artifact — the same object each
   * carrying message's `meta.payment_artifact` points at, kept here too so
   * the agent column (BoundsGauge's balance line) can read it without
   * walking the message list. */
  artifact: PaymentArtifact | null;
  callOffer: LiveCallOffer | null;
  bounds: Bounds | null;
  finalState: LifecycleStatus | null;
  metrics: Metrics | null;
  error: string | null;
  sending: boolean;
  reply: (text: string) => Promise<void>;
  /** Closes the stream and tells the backend to drop the in-process session
   * (durable rows are untouched). Call this from an explicit exit action, not
   * an unmount effect — see the note above `useEffect` below. */
  exit: () => Promise<void>;
}

function parse<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Channels come over the wire as plain strings; the backend enum already
 * constrains the values, same cast `computeBounds` uses for the same field. */
function toBounds(wire: LiveBoundsWire): Bounds {
  return {
    ...wire,
    channelsAllowed: wire.channelsAllowed as Channel[],
    channelsUsed: wire.channelsUsed as Channel[],
    channelsRemaining: wire.channelsRemaining as Channel[],
    armedRule: wire.armedRule as StoppingRule | null,
    firedRule: wire.firedRule as StoppingRule | null,
    nextActionAt: wire.nextActionAt ? new Date(wire.nextActionAt) : null,
  };
}

export function useLiveSession(sessionId: string | null): LiveSessionState {
  const [phase, setPhase] = useState<LivePhase>(sessionId ? "connecting" : "idle");
  const [events, setEvents] = useState<LiveTurnEvent[]>([]);
  const [start, setStart] = useState<LiveStart | null>(null);
  const [diagnosis, setDiagnosis] = useState<LiveDiagnosis | null>(null);
  const [route, setRoute] = useState<RouteDecision | null>(null);
  const [decision, setDecision] = useState<LiveDecision | null>(null);
  const [typing, setTyping] = useState<"agent" | "customer" | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [dispatch, setDispatch] = useState<LiveDispatchEvent | null>(null);
  const [reminder, setReminder] = useState<LiveReminder | null>(null);
  const [artifact, setArtifact] = useState<PaymentArtifact | null>(null);
  const [callOffer, setCallOffer] = useState<LiveCallOffer | null>(null);
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [finalState, setFinalState] = useState<LifecycleStatus | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // A different session id means a different run; reset during render (React's
  // "adjust state when props change") rather than as the first act of an
  // effect, so the effect body below never calls setState synchronously —
  // only from inside the EventSource listeners, which are genuine external
  // subscriptions.
  const [seenId, setSeenId] = useState(sessionId);
  if (seenId !== sessionId) {
    setSeenId(sessionId);
    setPhase(sessionId ? "connecting" : "idle");
    setEvents([]);
    setStart(null);
    setDiagnosis(null);
    setRoute(null);
    setDecision(null);
    setTyping(null);
    setMessages([]);
    setDispatch(null);
    setReminder(null);
    setArtifact(null);
    setCallOffer(null);
    setBounds(null);
    setFinalState(null);
    setMetrics(null);
    setError(null);
  }

  const sourceRef = useRef<EventSource | null>(null);
  const completedRef = useRef(false);
  const exitedRef = useRef(false);

  const close = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  // Auto-connects on mount because the theatre is entered with `?case=<id>`,
  // not a "run" button. StrictMode double-invokes this in dev — the cleanup's
  // `close()` aborts the first EventSource before it does any harm, the same
  // property useRecoveryRun relies on for its own EventSource.
  useEffect(() => {
    if (!sessionId) return;
    completedRef.current = false;
    exitedRef.current = false;

    const source = new EventSource(liveSessionStreamUrl(sessionId));
    sourceRef.current = source;

    const push = (event: LiveTurnEvent) => setEvents((prev) => [...prev, event]);

    source.addEventListener("start", (e) => {
      const data = parse<LiveStart>((e as MessageEvent<string>).data);
      if (!data) return;
      setPhase("streaming");
      setStart(data);
      push({ kind: "start", at: Date.now(), data });
    });

    source.addEventListener("step", (e) => {
      const data = parse<LiveStep>((e as MessageEvent<string>).data);
      if (data) push({ kind: "step", at: Date.now(), data });
    });

    source.addEventListener("diagnosis", (e) => {
      const data = parse<LiveDiagnosis>((e as MessageEvent<string>).data);
      if (!data) return;
      setDiagnosis(data);
      push({ kind: "diagnosis", at: Date.now(), data });
    });

    source.addEventListener("route", (e) => {
      const data = parse<RouteDecision>((e as MessageEvent<string>).data);
      if (!data) return;
      setRoute(data);
      push({ kind: "route", at: Date.now(), data });
    });

    source.addEventListener("decision", (e) => {
      const data = parse<LiveDecision>((e as MessageEvent<string>).data);
      if (!data) return;
      setDecision(data);
      setRoute(data.route_decision);
      push({ kind: "decision", at: Date.now(), data });
    });

    source.addEventListener("typing", (e) => {
      const data = parse<{ who: "agent" | "customer" }>((e as MessageEvent<string>).data);
      setTyping(data?.who ?? null);
    });

    source.addEventListener("message", (e) => {
      const data = parse<ConversationMessage>((e as MessageEvent<string>).data);
      if (!data) return;
      setTyping(null);
      setMessages((prev) => [...prev, data]);
      push({ kind: "message", at: Date.now(), data });
    });

    source.addEventListener("dispatch", (e) => {
      const data = parse<LiveDispatchEvent>((e as MessageEvent<string>).data);
      if (!data) return;
      setDispatch(data);
      push({ kind: "dispatch", at: Date.now(), data });
    });

    source.addEventListener("reminder", (e) => {
      const data = parse<LiveReminder>((e as MessageEvent<string>).data);
      if (!data) return;
      setReminder(data);
      push({ kind: "reminder", at: Date.now(), data });
    });

    source.addEventListener("artifact", (e) => {
      const data = parse<PaymentArtifact>((e as MessageEvent<string>).data);
      if (!data) return;
      setArtifact(data);
      push({ kind: "artifact", at: Date.now(), data });
    });

    source.addEventListener("artifact_closed", (e) => {
      const data = parse<{ id: number }>((e as MessageEvent<string>).data);
      if (!data?.id) return;
      setMessages((prev) =>
        prev.map((msg) => {
          const art = msg.meta &&
            typeof msg.meta === "object" &&
            (msg.meta as Record<string, unknown>).payment_artifact;
          if (art && typeof art === "object" && (art as Record<string, unknown>).id === data.id) {
            return {
              ...msg,
              meta: {
                ...(msg.meta as Record<string, unknown>),
                payment_artifact: {
                  ...(art as Record<string, unknown>),
                  status: "closed",
                },
              },
            } as ConversationMessage;
          }
          return msg;
        })
      );
    });

    source.addEventListener("call_offer", (e) => {
      const data = parse<LiveCallOffer>((e as MessageEvent<string>).data);
      if (!data) return;
      setCallOffer(data);
      push({ kind: "call_offer", at: Date.now(), data });
    });

    source.addEventListener("bounds", (e) => {
      const data = parse<LiveBoundsWire>((e as MessageEvent<string>).data);
      if (data) setBounds(toBounds(data));
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
        push({ kind: "complete", at: Date.now(), data });
      }
      completedRef.current = true;
      setTyping(null);
      setPhase("done");
      close();
    });

    // An intentional exit closes the source itself, which also fires this —
    // don't report that as a stream failure.
    source.addEventListener("error", () => {
      if (completedRef.current || exitedRef.current) return;
      close();
      setTyping(null);
      setPhase("error");
      setError("The live session stream closed before it finished.");
    });

    return close;
  }, [sessionId, close]);

  const reply = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!sessionId || !trimmed) return;
      setSending(true);
      try {
        await api.replyLiveSession(sessionId, trimmed);
      } catch (caught) {
        if (!isAbort(caught)) {
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      } finally {
        setSending(false);
      }
    },
    [sessionId],
  );

  const exit = useCallback(async () => {
    exitedRef.current = true;
    close();
    if (!sessionId) return;
    try {
      await api.deleteLiveSession(sessionId);
    } catch {
      // Best-effort: prune_sessions on the next server start is the backstop,
      // and every durable row survives regardless (live_session.close()).
    }
  }, [sessionId, close]);

  return {
    phase,
    events,
    start,
    diagnosis,
    route,
    decision,
    typing,
    messages,
    dispatch,
    reminder,
    artifact,
    callOffer,
    bounds,
    finalState,
    metrics,
    error,
    sending,
    reply,
    exit,
  };
}
