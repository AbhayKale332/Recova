"use client";

import { useEffect, useRef, useState } from "react";

import { useToast } from "@/components/Toast";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { describeVapiError } from "@/lib/vapi-error";
import { ArtifactCard } from "@/components/live/WhatsAppThread";
import type { LiveCallOffer } from "@/lib/simulation";
import type { PaymentArtifact } from "@/lib/types";

interface Turn {
  id: string;
  speaker: "AGENT" | "CUSTOMER";
  text: string;
  at_offset_sec: number;
}

/** Product-level function names named in the assistant config
 * (`voice_agent.build_assistant`) → the `AgentTool` enum value
 * `POST /agent/tool` expects. No MCP tool name ever appears here — that is
 * the whole point of naming these at the product level. */
const TOOL_CALL_MAP: Record<string, string> = {
  create_payment_qr: "GENERATE_QR_CODE",
  create_payment_link: "GENERATE_PAYMENT_LINK",
  offer_partial_plan: "OFFER_PARTIAL_PLAN",
};

/**
 * Live Voice Call Stage.
 *
 * Lazily loads `@vapi-ai/web`, requests microphone permissions, starts the call
 * using the public key and transient assistant configuration from
 * `api.callWebLiveSession(sessionId)`, displays speaking/listening indicators,
 * streams real-time transcripts, ingests each completed turn via
 * `api.ingestLiveCallTurn()`, and provides an End call control.
 */
export function CallStage({
  offer,
  sessionId,
  artifact,
  caseAmountInr,
}: {
  offer: LiveCallOffer | null;
  sessionId?: string | null;
  /** The session's most recently minted artifact — the same object the
   * WhatsApp thread renders, kept in sync via the `artifact` SSE event that
   * `run_agent_tool` triggers server-side, so this card and the thread's
   * card never disagree. */
  artifact?: PaymentArtifact | null;
  caseAmountInr?: number;
}) {
  const { t, locale } = useI18n();
  const toast = useToast();

  const [callStatus, setCallStatus] = useState<
    "idle" | "requesting_mic" | "connecting" | "active" | "ended" | "error"
  >("idle");
  const [speakingState, setSpeakingState] = useState<"speaking" | "listening" | "idle">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [partialTranscript, setPartialTranscript] = useState<{
    speaker: "AGENT" | "CUSTOMER";
    text: string;
  } | null>(null);
  const [durationSec, setDurationSec] = useState(0);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vapiRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const startedCallRef = useRef<boolean>(false);
  const transcriptBoxRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number | null>(null);

  // Timer for duration when active
  useEffect(() => {
    if (callStatus !== "active") return;
    const interval = setInterval(() => {
      if (startTimeRef.current) {
        setDurationSec(Math.max(0, Math.floor((Date.now() - startTimeRef.current) / 1000)));
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [callStatus]);

  // Scroll transcript to bottom as messages arrive
  useEffect(() => {
    transcriptBoxRef.current?.scrollTo({
      top: transcriptBoxRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns.length, partialTranscript]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (vapiRef.current) {
        try {
          vapiRef.current.stop();
        } catch {
          // ignore cleanup errors
        }
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  // Initiate call upon offer
  useEffect(() => {
    if (!offer || startedCallRef.current) return;
    startedCallRef.current = true;

    let isCancelled = false;

    async function startVoiceCall() {
      // 1. Request microphone access
      setCallStatus("requesting_mic");
      try {
        if (navigator.mediaDevices?.getUserMedia) {
          const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          streamRef.current = micStream;
        }
      } catch (err) {
        if (isCancelled) return;
        console.warn("Microphone access failed:", err);
        setCallStatus("error");
        setErrorMessage(t.live.callMicDenied);
        toast.failure(t.live.callTitle, t.live.callMicDenied);
        return;
      }

      if (isCancelled) return;

      // 2. Fetch web call configuration
      setCallStatus("connecting");
      let publicKey = offer?.public_key;
      let assistantConfig = offer?.assistant;

      if ((!publicKey || !assistantConfig) && sessionId) {
        try {
          const fetched = await api.callWebLiveSession(sessionId);
          publicKey = fetched.public_key;
          assistantConfig = fetched.assistant;
        } catch (err: unknown) {
          if (isCancelled) return;
          console.warn("Failed to get web call config:", err);
          const reason =
            err && typeof err === "object" && "detail" in err
              ? String((err as { detail: unknown }).detail)
              : t.live.callNotConfigured;
          setCallStatus("error");
          setErrorMessage(reason);
          toast.failure(t.live.callTitle, reason);
          return;
        }
      }

      if (!publicKey || !assistantConfig) {
        if (isCancelled) return;
        setCallStatus("error");
        setErrorMessage(t.live.callNotConfigured);
        toast.info(t.live.callTitle, t.live.callNotConfigured);
        return;
      }

      // 3. Dynamically import @vapi-ai/web client
      try {
        const { default: Vapi } = await import("@vapi-ai/web");
        if (isCancelled) return;

        const vapi = new Vapi(publicKey);
        vapiRef.current = vapi;

        // Client-side tools have no `server.url` — Vapi cannot get a result
        // back from a webhook, so an `add-message` Live Call Control message
        // is the documented way to feed the outcome back into the
        // conversation: a refusal reaches Rekha's mouth as the sandbox's own
        // sentence, not a paraphrase.
        const addSystemMessage = (content: string) =>
          vapi.send({ type: "add-message", message: { role: "system", content } });

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const handleToolCalls = async (message: any) => {
          if (!sessionId) return;
          const calls: unknown[] = message?.toolCallList ?? message?.toolCalls ?? [];

          for (const call of calls as Array<{
            function?: { name?: string; arguments?: string };
          }>) {
            const name = call.function?.name;
            if (!name) continue;
            let args: Record<string, unknown> = {};
            try {
              args = JSON.parse(call.function?.arguments ?? "{}");
            } catch {
              args = {};
            }

            try {
              if (name === "check_payment_status") {
                const result = await api.checkPaymentStatus(sessionId);
                const content =
                  result.found && result.artifact
                    ? result.artifact.status === "created"
                      ? "No payment received yet."
                      : `Payment received: ₹${(result.artifact.amount_paid_minor / 100).toLocaleString("en-IN")}.`
                    : "No payment link or QR has been created yet.";
                addSystemMessage(content);
                continue;
              }

              const tool = TOOL_CALL_MAP[name];
              if (!tool) continue;

              const result = await api.runAgentTool(sessionId, { tool, args });
              const content = result.allowed
                ? result.artifact
                  ? `${name.replace(/_/g, " ")} ready for ₹${(result.artifact.amount_minor / 100).toLocaleString("en-IN")}. Tell the customer.`
                  : `${name.replace(/_/g, " ")} done. Tell the customer.`
                : `Refused: ${result.sandbox_reason ?? result.reason}`;
              addSystemMessage(content);
            } catch (err) {
              console.warn("Agent tool call failed:", name, err);
              addSystemMessage("That didn't go through on our side — apologize and offer to try again.");
            }
          }
        };

        // Tracks whether the call has already resolved (started or failed) so a
        // late, non-critical `error` event (e.g. audio-processing setup, which
        // the SDK explicitly treats as "don't throw, this is non-critical")
        // cannot re-fail an already-active call. React state can't be read
        // synchronously here - `callStatus` in this closure is a snapshot from
        // whenever this effect ran, not the current value.
        let settled = false;

        vapi.on("call-start", () => {
          if (isCancelled) return;
          settled = true;
          setCallStatus("active");
          startTimeRef.current = Date.now();
          setSpeakingState("listening");
        });

        vapi.on("speech-start", () => {
          if (isCancelled) return;
          setSpeakingState("speaking");
        });

        vapi.on("speech-end", () => {
          if (isCancelled) return;
          setSpeakingState("listening");
        });

        vapi.on("call-end", () => {
          if (isCancelled) return;
          settled = true;
          setCallStatus("ended");
          setSpeakingState("idle");
        });

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        vapi.on("message", (message: any) => {
          if (isCancelled) return;

          if (message?.type === "tool-calls") {
            handleToolCalls(message);
            return;
          }

          if (message?.type === "transcript") {
            const role: "AGENT" | "CUSTOMER" =
              message.role === "assistant" || message.role === "agent" ? "AGENT" : "CUSTOMER";
            const text = String(message.transcript || "").trim();
            if (!text) return;

            if (message.transcriptType === "partial") {
              setPartialTranscript({ speaker: role, text });
            } else if (message.transcriptType === "final") {
              setPartialTranscript(null);
              const offset = startTimeRef.current
                ? Math.max(0, Math.floor((Date.now() - startTimeRef.current) / 1000))
                : 0;
              const newTurn: Turn = {
                id: `turn_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                speaker: role,
                text,
                at_offset_sec: offset,
              };
              setTurns((prev) => [...prev, newTurn]);

              // Ingest turn to backend for durable persistence and audit trail
              if (sessionId) {
                api
                  .ingestLiveCallTurn(sessionId, {
                    speaker: role,
                    text,
                    at_offset_sec: offset,
                  })
                  .catch((err) => console.warn("Failed to ingest turn:", err));
              }
            }
          }
        });

        const failCall = (reason: string) => {
          if (isCancelled || settled) return;
          settled = true;
          console.warn("Vapi call failed to start:", reason);
          setCallStatus("error");
          setErrorMessage(reason);
          toast.failure(t.live.callTitle, reason);
        };

        vapi.on("call-start-failed", (event) => {
          failCall(describeVapiError(event));
        });

        vapi.on("error", (err) => {
          console.warn("Vapi error event:", err);
          // Only a real failure, not this SDK's DOM-level camera/audio-processing
          // warnings, should end a call that never started - `settled` (checked
          // inside failCall) is what actually draws that line, since both fire
          // through this same event.
          failCall(describeVapiError(err));
        });

        // Hard timeout: the SDK can also stall silently (e.g. a WebRTC/room-join
        // negotiation that never resolves and never fires an event at all).
        const connectTimeout = window.setTimeout(() => {
          failCall(t.live.callTimeout);
        }, 20000);
        vapi.on("call-start", () => window.clearTimeout(connectTimeout));
        vapi.on("call-start-failed", () => window.clearTimeout(connectTimeout));
        vapi.on("error", () => window.clearTimeout(connectTimeout));

        // Start call with transient assistant configuration. `start()` resolves
        // to `null` on failure rather than rejecting - the `call-start-failed`
        // and `error` listeners above are what actually surface it, but this is
        // a backstop in case neither fires.
        const call = await vapi.start(assistantConfig as Parameters<typeof vapi.start>[0]);
        if (call == null) {
          failCall(t.live.callNotConfigured);
        }
      } catch (err) {
        if (isCancelled) return;
        console.error("Failed to start Vapi web call:", err);
        setCallStatus("error");
        const msg = err instanceof Error ? err.message : t.live.callNotConfigured;
        setErrorMessage(msg);
        toast.failure(t.live.callTitle, msg);
      }
    }

    startVoiceCall();

    return () => {
      isCancelled = true;
    };
  }, [offer, sessionId, t, toast]);

  const handleEndCall = () => {
    if (vapiRef.current) {
      try {
        vapiRef.current.stop();
      } catch (err) {
        console.warn("Error stopping vapi:", err);
      }
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCallStatus("ended");
    setSpeakingState("idle");
  };

  if (!offer) return null;

  const minutes = Math.floor(durationSec / 60);
  const seconds = durationSec % 60;
  const timeFormatted = `${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 shadow-sm">
      {/* Call Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
        <div className="flex items-center gap-2.5">
          <span className="relative flex size-3">
            {callStatus === "active" ? (
              <>
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-75" />
                <span className="relative inline-flex size-3 rounded-full bg-[var(--accent)]" />
              </>
            ) : callStatus === "connecting" || callStatus === "requesting_mic" ? (
              <>
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--warn)] opacity-75" />
                <span className="relative inline-flex size-3 rounded-full bg-[var(--warn)]" />
              </>
            ) : (
              <span className="relative inline-flex size-3 rounded-full bg-[var(--muted)]" />
            )}
          </span>
          <div>
            <h3 className="text-[13px] font-semibold tracking-tight text-[var(--text)]">
              {t.live.callTitle}
            </h3>
            <p className="text-[11px] text-[var(--muted)]">
              {callStatus === "requesting_mic" && t.live.callMicPermission}
              {callStatus === "connecting" && t.live.callConnecting}
              {callStatus === "active" && t.live.callActive}
              {callStatus === "ended" && t.live.callEnded}
              {callStatus === "error" && (errorMessage || t.live.callNotConfigured)}
              {callStatus === "idle" && t.live.callWaiting}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {callStatus === "active" ? (
            <span className="tabular font-mono text-[12px] font-medium text-[var(--text)]">
              {timeFormatted}
            </span>
          ) : null}
          {offer.call_session_id != null ? (
            <span className="rounded bg-[var(--bg)] px-2 py-0.5 text-[11px] text-[var(--muted)]">
              {fillTemplate(t.live.callSessionId, { id: offer.call_session_id })}
            </span>
          ) : null}
          {callStatus === "active" ? (
            <button
              type="button"
              onClick={handleEndCall}
              className="flex items-center gap-1.5 rounded-md bg-[var(--danger)] px-2.5 py-1 text-[12px] font-medium text-white transition hover:opacity-90 active:scale-95"
            >
              <svg className="size-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z" />
              </svg>
              <span>{t.live.callEnd}</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Speaking / Listening Activity Banner */}
      {callStatus === "active" ? (
        <div className="flex items-center justify-between rounded-md border border-[var(--border)] bg-[var(--bg)] px-3 py-2">
          <div className="flex items-center gap-2.5">
            {speakingState === "speaking" ? (
              <div className="flex items-center gap-0.5">
                <span className="h-3 w-1 animate-pulse rounded-full bg-[var(--accent)]" />
                <span className="h-5 w-1 animate-pulse rounded-full bg-[var(--accent)] delay-75" />
                <span className="h-4 w-1 animate-pulse rounded-full bg-[var(--accent)] delay-150" />
                <span className="h-2 w-1 animate-pulse rounded-full bg-[var(--accent)] delay-200" />
              </div>
            ) : (
              <div className="flex size-5 items-center justify-center rounded-full bg-[var(--accent-ink)] text-white">
                <svg className="size-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
            )}
            <span className="text-[12px] font-medium text-[var(--text)]">
              {speakingState === "speaking" ? t.live.callSpeaking : t.live.callListening}
            </span>
          </div>

          <span className="text-[11px] text-[var(--muted)]">
            ElevenLabs • {offer.call_session_id ? `Vapi #${offer.call_session_id}` : "Vapi"}
          </span>
        </div>
      ) : null}

      {/* Payment artifact minted mid-call — same card the WhatsApp thread
          renders, kept in sync via the `artifact` SSE event. */}
      {artifact && sessionId && (callStatus === "active" || callStatus === "ended") ? (
        <ArtifactCard
          sessionId={sessionId}
          artifact={artifact}
          caseAmountInr={caseAmountInr ?? artifact.amount_minor / 100}
          locale={locale}
        />
      ) : null}

      {/* Live Transcript Stream */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
            {t.live.callLiveTranscript}
          </p>
          {turns.length > 0 ? (
            <span className="text-[11px] text-[var(--muted)]">
              {turns.length} {turns.length === 1 ? "turn" : "turns"}
            </span>
          ) : null}
        </div>

        <div
          ref={transcriptBoxRef}
          className="flex max-h-[160px] min-h-[70px] flex-col gap-2 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--bg)] p-2.5 text-[12px]"
        >
          {turns.length === 0 && !partialTranscript ? (
            <p className="my-auto text-center text-[12px] text-[var(--muted)]">
              {callStatus === "connecting" || callStatus === "requesting_mic"
                ? t.live.callConnecting
                : callStatus === "error"
                ? errorMessage || t.live.callNotConfigured
                : t.live.callWaiting}
            </p>
          ) : (
            <>
              {turns.map((turn) => (
                <div
                  key={turn.id}
                  className={`flex flex-col gap-0.5 rounded px-2 py-1 ${
                    turn.speaker === "AGENT"
                      ? "border-l-2 border-[var(--accent)] bg-[var(--surface)] text-[var(--text)]"
                      : "border-l-2 border-[var(--border)] bg-[var(--surface)]/60 text-[var(--text)]"
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] font-semibold tracking-wider text-[var(--muted)] uppercase">
                    <span>{turn.speaker === "AGENT" ? t.live.agentLabel : t.live.customerLabel}</span>
                    <span className="font-mono text-[9px]">{turn.at_offset_sec}s</span>
                  </div>
                  <p className="text-[12px] leading-relaxed">{turn.text}</p>
                </div>
              ))}

              {partialTranscript ? (
                <div
                  className={`flex flex-col gap-0.5 rounded px-2 py-1 opacity-70 ${
                    partialTranscript.speaker === "AGENT"
                      ? "border-l-2 border-[var(--accent)] bg-[var(--surface)]"
                      : "border-l-2 border-[var(--border)] bg-[var(--surface)]/60"
                  }`}
                >
                  <div className="text-[10px] font-semibold tracking-wider text-[var(--muted)] uppercase">
                    <span>
                      {partialTranscript.speaker === "AGENT" ? t.live.agentLabel : t.live.customerLabel}
                    </span>
                  </div>
                  <p className="text-[12px] italic leading-relaxed">{partialTranscript.text}…</p>
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
