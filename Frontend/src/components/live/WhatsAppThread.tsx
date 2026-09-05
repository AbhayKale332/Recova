"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "@/lib/api";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatClock, formatDate, formatMoney, paiseToRupees } from "@/lib/format";
import { Money } from "@/components/Money";
import type { ConversationMessage, PaymentArtifact } from "@/lib/types";

/**
 * A WhatsApp-shaped thread from the customer's own phone: their own outgoing
 * texts on the right with delivery ticks, the agent's replies on the left, a
 * typing indicator, and a composer. Purely on-screen — `POST /reply` is the
 * whole transport, so nothing here can fail live on camera the way a real
 * WhatsApp round-trip could.
 */
export function WhatsAppThread({
  sessionId,
  customerName,
  caseAmountInr,
  messages,
  typing,
  disabled,
  onSend,
}: {
  /** Needed to hit the demo "simulate payment" endpoint from an artifact
   * card — the endpoint is scoped to one live session. */
  sessionId: string;
  customerName: string;
  /** The case's full amount — a partial-plan card needs it to show the
   * remaining balance, which the artifact itself does not carry. */
  caseAmountInr: number;
  messages: ConversationMessage[];
  typing: "agent" | "customer" | null;
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const { t, locale } = useI18n();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, typing]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 bg-[var(--accent-ink)] px-3 py-2 text-white">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-white/20 text-[13px] font-semibold">
          {customerName.slice(0, 1).toUpperCase() || "?"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold">{customerName}</p>
          <p className="truncate text-[11px] text-white/80">
            {typing === "agent" ? t.live.agentTyping : t.live.online}
          </p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto px-2.5 py-3">
        {messages.map((message) => (
          <Bubble
            key={message.id}
            sessionId={sessionId}
            message={message}
            locale={locale}
            caseAmountInr={caseAmountInr}
          />
        ))}
        {typing === "agent" ? <TypingBubble /> : null}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={submit}
        className="flex items-center gap-2 border-t border-black/5 bg-[#f0f0f0] px-2 py-2"
      >
        <label className="sr-only" htmlFor="live-composer">
          {t.live.composerLabel}
        </label>
        <input
          id="live-composer"
          value={draft}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t.live.composerPlaceholder}
          maxLength={2000}
          className="min-w-0 flex-1 rounded-full border border-black/10 bg-white px-3 py-2 text-[13px] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !draft.trim()}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white disabled:opacity-50"
          aria-label={t.live.send}
        >
          <span aria-hidden>➤</span>
        </button>
      </form>
    </div>
  );
}

/** `message.meta.payment_artifact` travels as the backend's `PaymentArtifact.as_dict()`
 * shape (Message.meta_json is untyped JSON on the wire), never validated further —
 * only its presence and shape (an object) are checked. */
function extractArtifact(meta: ConversationMessage["meta"]): PaymentArtifact | null {
  if (!meta || typeof meta !== "object") return null;
  const raw = (meta as Record<string, unknown>).payment_artifact;
  return raw && typeof raw === "object" ? (raw as PaymentArtifact) : null;
}

function Bubble({
  sessionId,
  message,
  locale,
  caseAmountInr,
}: {
  sessionId: string;
  message: ConversationMessage;
  locale: "en" | "hi";
  caseAmountInr: number;
}) {
  if (message.sender === "SYSTEM") {
    return (
      <div className="mx-auto max-w-[85%] rounded-md bg-black/10 px-2.5 py-1 text-center text-[11px] text-neutral-700">
        {message.body}
      </div>
    );
  }

  const artifact = extractArtifact(message.meta);

  // The phone represents the customer's own device: their INBOUND (to the
  // engine) text is the phone owner's own outgoing bubble.
  const mine = message.direction === "INBOUND";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[78%] rounded-lg px-2.5 py-1.5 text-[13px] shadow-sm ${
          mine ? "bg-[#dcf8c6]" : "bg-white"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{message.body}</p>
        {artifact ? (
          <ArtifactCard
            sessionId={sessionId}
            artifact={artifact}
            caseAmountInr={caseAmountInr}
            locale={locale}
          />
        ) : null}
        <div className="mt-0.5 flex items-center justify-end gap-1 text-[10px] text-neutral-500">
          <span>{formatClock(message.created_at, locale)}</span>
          {mine ? <Ticks status={message.status} /> : null}
        </div>
      </div>
    </div>
  );
}

/**
 * The card under a payment bubble. A QR renders as a plain `<img>` (never
 * `next/image` — that needs `remotePatterns` config for an arbitrary
 * Razorpay host) with a link fallback on load failure; a link gets a
 * "Pay now" anchor; a partial plan states both figures, since the artifact
 * itself only carries what is being asked for *now*, not the case's balance.
 */
function ArtifactCard({
  sessionId,
  artifact,
  caseAmountInr,
  locale,
}: {
  sessionId: string;
  artifact: PaymentArtifact;
  caseAmountInr: number;
  locale: "en" | "hi";
}) {
  const { t } = useI18n();
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = artifact.kind === "QR" && artifact.image_url && !imageFailed;
  const showLink = artifact.url && (artifact.kind !== "QR" || !showImage);

  // This card renders a snapshot frozen at send time
  // (message.meta.payment_artifact) — a real reconciled payment lands as a
  // *new* SYSTEM message instead of mutating this one, so this local flag is
  // what actually hides the button once it's been used; it does not read
  // back the live artifact status after that point.
  const [simState, setSimState] = useState<"idle" | "pending" | "done" | "error">("idle");
  const isClosed = artifact.status === "closed" || artifact.status === "expired";
  const canSimulate =
    !isClosed &&
    (artifact.status === "created" || artifact.status === "partially_paid") &&
    simState !== "done";

  const simulate = async () => {
    setSimState("pending");
    try {
      await api.simulatePaymentArtifact(sessionId, artifact.id);
      setSimState("done");
    } catch {
      setSimState("error");
    }
  };

  return (
    <div className="mt-1.5 flex flex-col items-stretch gap-1.5 rounded-md border border-black/10 bg-black/[0.03] p-2">
      {showImage ? (
        <img
          src={artifact.image_url!}
          alt={t.live.scanQr}
          onError={() => setImageFailed(true)}
          className="mx-auto w-full rounded bg-white object-contain"
        />
      ) : null}

      {artifact.accept_partial ? (
        <p className="tabular text-center text-[12px] font-medium">
          {fillTemplate(t.live.partialPlanLine, {
            now: formatMoney(paiseToRupees(artifact.amount_minor)),
            balance: formatMoney(
              Math.max(caseAmountInr - paiseToRupees(artifact.amount_minor), 0),
            ),
            date: artifact.deadline ? formatDate(artifact.deadline, locale) : "—",
          })}
        </p>
      ) : (
        <p className="tabular text-center text-[13px] font-semibold">
          <Money value={artifact.amount_minor} unit="paise" />
        </p>
      )}

      {isClosed ? (
        <p className="rounded-full bg-neutral-200 px-3 py-1.5 text-center text-[12px] font-medium text-neutral-500 line-through">
          {t.sim.linkReplaced}
        </p>
      ) : showLink ? (
        <a
          href={artifact.url!}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-full bg-[var(--accent)] px-3 py-1.5 text-center text-[12px] font-semibold text-white"
        >
          {t.live.payNow}
        </a>
      ) : artifact.kind === "QR" && !showImage ? (
        <p className="text-center text-[11px] text-[var(--muted)]">{t.live.qrUnavailable}</p>
      ) : null}

      {artifact.detail === "simulated" && !isClosed ? (
        <p className="text-center text-[10px] text-[var(--muted)]">{t.live.artifactSimulated}</p>
      ) : null}

      {canSimulate ? (
        <button
          type="button"
          onClick={simulate}
          disabled={simState === "pending"}
          className="rounded-full border border-dashed border-[var(--accent)] px-3 py-1.5 text-center text-[11px] font-medium text-[var(--accent)] disabled:opacity-60"
        >
          {simState === "pending" ? t.live.simulatingPayment : t.live.simulatePayment}
        </button>
      ) : null}
      {simState === "error" ? (
        <p className="text-center text-[10px] text-red-600">{t.live.paymentSimulateFailed}</p>
      ) : null}
    </div>
  );
}

/** WhatsApp-style ticks apply only to the phone owner's own sent messages. */
function Ticks({ status }: { status: ConversationMessage["status"] }) {
  if (status === "SENT") return <span aria-hidden>✓</span>;
  return (
    <span aria-hidden className={status === "READ" ? "text-[#53bdeb]" : undefined}>
      ✓✓
    </span>
  );
}

function TypingBubble() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 rounded-lg bg-white px-3 py-2.5 shadow-sm">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 animate-bounce rounded-full bg-neutral-400"
            style={{ animationDelay: `${i * 120}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
