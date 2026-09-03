/**
 * The bounds model behind the bounds gauge: attempts used vs. cap, channels
 * remaining, which stopping rule is armed, and when the agent may act next.
 *
 * Derived from the case's own audit trail plus the live /policy response.
 *
 * The three regulatory caps below are constants in the engine, not tunable
 * policy, and are not exposed as their own fields — they mirror
 * `backend/application/operations/compliance_rules.py`. Everything else here is
 * read from the API.
 */

import type { AuditEntry, Channel, LifecycleStatus, StoppingRule } from "@/lib/types";
import { isTerminal } from "@/lib/status";

/** RBI permits at most 3 auto-debit retries per cycle. */
export const RBI_MAX_RETRIES = 3;
/** At most 2 voice attempts per rolling 72-hour window. */
export const VOICE_ATTEMPT_CAP = 2;
/** TRAI: no outbound contact between 20:00 and 09:00 IST. */
export const QUIET_HOURS_START = 20;
export const QUIET_HOURS_END = 9;

export interface Budget {
  used: number;
  cap: number;
  /** True once `used` has reached `cap` — the rule is no longer armed, it fired. */
  exhausted: boolean;
}

export interface Bounds {
  /** Auto-debit retries against the RBI cap. */
  retries: Budget;
  /** Voice calls against the 72-hour cap. */
  voice: Budget;
  /** Every outbound dispatch this case has made. */
  totalDispatches: number;
  channelsAllowed: Channel[];
  channelsUsed: Channel[];
  channelsRemaining: Channel[];
  /** The rule that would halt this case next, or null when nothing is close. */
  armedRule: StoppingRule | null;
  /** The rule that already halted it, from the case's own audit trail. */
  firedRule: StoppingRule | null;
  /** Earliest moment the agent may contact this customer, or null for "now". */
  nextActionAt: Date | null;
  /** True when quiet hours are the reason `nextActionAt` is in the future. */
  inQuietHours: boolean;
  /** No further action is possible — the case is closed. */
  closed: boolean;
}

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

/** IST is UTC+5:30 with no DST, so a fixed offset is exact. */
const IST_OFFSET_MINUTES = 330;

export function istHour(now: Date = new Date()): number {
  const shifted = new Date(now.getTime() + IST_OFFSET_MINUTES * 60_000);
  return shifted.getUTCHours();
}

export function isQuietHours(now: Date = new Date()): boolean {
  const hour = istHour(now);
  return hour >= QUIET_HOURS_START || hour < QUIET_HOURS_END;
}

/** The next 09:00 IST after `now`, as an instant. */
export function nextQuietHoursEnd(now: Date = new Date()): Date {
  const shifted = new Date(now.getTime() + IST_OFFSET_MINUTES * 60_000);
  const target = new Date(shifted);
  target.setUTCHours(QUIET_HOURS_END, 0, 0, 0);
  if (target <= shifted) target.setUTCDate(target.getUTCDate() + 1);
  return new Date(target.getTime() - IST_OFFSET_MINUTES * 60_000);
}

export function computeBounds(opts: {
  status: LifecycleStatus;
  auditTrail: AuditEntry[];
  stoppingRule: string | null;
  allowedChannels: string[];
  failureClass: number;
  now?: Date;
}): Bounds {
  const now = opts.now ?? new Date();
  const closed = isTerminal(opts.status);

  let totalDispatches = 0;
  let voiceUsed = 0;
  let retriesUsed = 0;
  const used = new Set<Channel>();

  for (const entry of opts.auditTrail) {
    const payload = entry.payload ?? {};
    const action = payloadString(payload, "action");
    const channel = payloadString(payload, "channel");

    if (entry.action_type === "INTERVENTION_DISPATCH") {
      totalDispatches += 1;
      if (channel) used.add(channel as Channel);
      if (channel === "VOICE" || action === "VOICE_CALL") voiceUsed += 1;
      if (action === "RETRY_CHARGE") retriesUsed += 1;
    }

    if (entry.action_type === "RETRY_SCHEDULED") retriesUsed += 1;
  }

  const channelsAllowed = opts.allowedChannels as Channel[];
  const channelsUsed = channelsAllowed.filter((c) => used.has(c));
  const channelsRemaining = channelsAllowed.filter((c) => !used.has(c));

  const retries: Budget = {
    used: Math.min(retriesUsed, RBI_MAX_RETRIES),
    cap: RBI_MAX_RETRIES,
    exhausted: retriesUsed >= RBI_MAX_RETRIES,
  };
  const voice: Budget = {
    used: Math.min(voiceUsed, VOICE_ATTEMPT_CAP),
    cap: VOICE_ATTEMPT_CAP,
    exhausted: voiceUsed >= VOICE_ATTEMPT_CAP,
  };

  const quiet = !closed && isQuietHours(now);

  return {
    retries,
    voice,
    totalDispatches,
    channelsAllowed,
    channelsUsed,
    channelsRemaining,
    armedRule: closed ? null : armedRule({ retries, voice, quiet, failureClass: opts.failureClass }),
    firedRule: (opts.stoppingRule as StoppingRule | null) ?? null,
    nextActionAt: quiet ? nextQuietHoursEnd(now) : null,
    inQuietHours: quiet,
    closed,
  };
}

/**
 * Which named rule halts this case next. Quiet hours bind first because they
 * gate every outbound channel; then whichever numeric budget is closest to its cap.
 */
function armedRule(opts: {
  retries: Budget;
  voice: Budget;
  quiet: boolean;
  failureClass: number;
}): StoppingRule | null {
  if (opts.quiet) return "TRAI_QUIET_HOURS";
  if (opts.retries.exhausted) return "RBI_MAX_RETRIES";
  if (opts.voice.exhausted) return "VOICE_ATTEMPT_CAP";
  // Subscription mandates are the only class that auto-debits, so the RBI cap
  // is the live constraint there; elsewhere the voice cap binds first.
  if (opts.failureClass === 3 && opts.retries.used > 0) return "RBI_MAX_RETRIES";
  if (opts.voice.used > 0) return "VOICE_ATTEMPT_CAP";
  return null;
}
