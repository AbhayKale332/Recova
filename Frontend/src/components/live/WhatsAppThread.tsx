"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { useI18n } from "@/lib/i18n";
import { formatClock } from "@/lib/format";
import type { ConversationMessage } from "@/lib/types";

/**
 * A WhatsApp-shaped thread from the customer's own phone: their own outgoing
 * texts on the right with delivery ticks, the agent's replies on the left, a
 * typing indicator, and a composer. Purely on-screen — `POST /reply` is the
 * whole transport, so nothing here can fail live on camera the way a real
 * WhatsApp round-trip could.
 */
export function WhatsAppThread({
  customerName,
  messages,
  typing,
  disabled,
  onSend,
}: {
  customerName: string;
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
          <Bubble key={message.id} message={message} locale={locale} />
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

function Bubble({ message, locale }: { message: ConversationMessage; locale: "en" | "hi" }) {
  if (message.sender === "SYSTEM") {
    return (
      <div className="mx-auto max-w-[85%] rounded-md bg-black/10 px-2.5 py-1 text-center text-[11px] text-neutral-700">
        {message.body}
      </div>
    );
  }

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
        <div className="mt-0.5 flex items-center justify-end gap-1 text-[10px] text-neutral-500">
          <span>{formatClock(message.created_at, locale)}</span>
          {mine ? <Ticks status={message.status} /> : null}
        </div>
      </div>
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
