/**
 * Lifecycle status → label + tone (Vision Appendix D).
 *
 * ESCALATED, CANCELLED and FAILED are three different outcomes. Collapsing them
 * into "unsuccessful" destroys the compliance story, so they get three tones,
 * three labels and three meanings.
 */

import type { Dictionary } from "@/lib/i18n/dictionaries/en";
import type { LifecycleStatus, StoppingRule } from "@/lib/types";

export type Tone = "muted" | "inflight" | "recovered" | "escalated" | "stopped" | "lost";

export const STATUS_TONE: Record<LifecycleStatus, Tone> = {
  PENDING: "muted",
  DIAGNOSING: "inflight",
  WAITING: "inflight",
  INTERVENING: "inflight",
  RECOVERED: "recovered",
  ESCALATED: "escalated",
  CANCELLED: "stopped",
  FAILED: "lost",
};

/** Statuses the recovery loop can still act on. */
export const OPEN_STATUSES: LifecycleStatus[] = [
  "PENDING",
  "DIAGNOSING",
  "WAITING",
  "INTERVENING",
];

const TERMINAL: ReadonlySet<LifecycleStatus> = new Set<LifecycleStatus>([
  "RECOVERED",
  "ESCALATED",
  "CANCELLED",
  "FAILED",
]);

export function isTerminal(status: LifecycleStatus): boolean {
  return TERMINAL.has(status);
}

export function statusLabel(status: LifecycleStatus, t: Dictionary): string {
  return t.status[status] ?? status;
}

export function statusMeaning(status: LifecycleStatus, t: Dictionary): string {
  return t.statusMeaning[status] ?? "";
}

/** Tailwind classes per tone. One place, so a tone never drifts between screens. */
export const TONE_CLASS: Record<Tone, string> = {
  muted: "bg-neutral-100 text-neutral-700 ring-neutral-300",
  inflight: "bg-amber-50 text-amber-800 ring-amber-300",
  recovered: "bg-green-50 text-green-800 ring-green-300",
  escalated: "bg-blue-50 text-blue-800 ring-blue-300",
  stopped: "bg-slate-100 text-slate-700 ring-slate-400",
  lost: "bg-rose-50 text-rose-800 ring-rose-300",
};

/** The solid fill for the funnel bar and other filled marks. */
export const TONE_FILL: Record<Tone, string> = {
  muted: "bg-neutral-300",
  inflight: "bg-[var(--inflight)]",
  recovered: "bg-[var(--recovered)]",
  escalated: "bg-[var(--escalated)]",
  stopped: "bg-[var(--stopped)]",
  lost: "bg-[var(--lost)]",
};

export const TONE_TEXT: Record<Tone, string> = {
  muted: "text-neutral-600",
  inflight: "text-[var(--inflight)]",
  recovered: "text-[var(--recovered)]",
  escalated: "text-[var(--escalated)]",
  stopped: "text-[var(--stopped)]",
  lost: "text-[var(--lost)]",
};

/**
 * Stopping rules in human language (Vision Appendix B).
 * Copy names the rule, the number, and the reason.
 */
export const STOPPING_RULE_COPY: Record<StoppingRule, { en: string; hi: string }> = {
  NO_DOUBLE_CHARGE: {
    en: "The payment settled late; don't charge twice",
    hi: "भुगतान देर से हुआ; दोबारा चार्ज न करें",
  },
  CROSS_DEVICE_COMPLETION: {
    en: "The customer already completed it elsewhere",
    hi: "ग्राहक ने इसे कहीं और पूरा कर लिया",
  },
  RBI_MAX_RETRIES: {
    en: "RBI cap — at most 3 auto-debit retries",
    hi: "RBI सीमा — अधिकतम 3 ऑटो-डेबिट रीट्राई",
  },
  EXPLICIT_CANCEL: {
    en: "The customer asked to cancel the plan",
    hi: "ग्राहक ने प्लान रद्द करने को कहा",
  },
  OPT_OUT: {
    en: "The customer opted out of contact",
    hi: "ग्राहक ने संपर्क से मना कर दिया",
  },
  DISPUTE_FREEZE: {
    en: "A dispute is on file — route to a human",
    hi: "विवाद दर्ज है — किसी व्यक्ति को सौंपें",
  },
  TRAI_QUIET_HOURS: {
    en: "No contact 20:00–09:00 IST",
    hi: "20:00–09:00 IST के बीच कोई संपर्क नहीं",
  },
  VOICE_ATTEMPT_CAP: {
    en: "At most 2 voice calls in 72 hours",
    hi: "72 घंटों में अधिकतम 2 वॉइस कॉल",
  },
};

export function stoppingRuleText(
  rule: string | null | undefined,
  locale: "en" | "hi",
): string | null {
  if (!rule) return null;
  const copy = STOPPING_RULE_COPY[rule as StoppingRule];
  return copy ? copy[locale] : rule;
}
