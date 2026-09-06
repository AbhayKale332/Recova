/**
 * Wire types and helpers for the what-if simulator.
 *
 * Mirrors backend/application/simulation/{scenario,probability,runner,trace}.py.
 * The console's first screen is built on these: the user describes a book of
 * failures, the backend runs it through the real recovery engine, and every
 * figure on screen is the output of that run.
 *
 * Three money figures come back and they are **not** additive:
 *   recovered_inr  measured — the engine drove these cases to RECOVERED
 *   deferred_inr   at risk, held by a stopping rule that defers (quiet hours)
 *   projected_inr  modelled — expected eventual recovery, with a band
 * Never sum them, and never present the projection as money that moved.
 */

import type { LifecycleStatus, StoppingRule } from "@/lib/types";
import type { Locale } from "@/lib/i18n/dictionaries/en";

export type ReplyKind = "cooperative" | "opt_out" | "dispute" | "p2p" | "silent";

export const REPLY_KINDS = [
  "cooperative",
  "p2p",
  "silent",
  "opt_out",
  "dispute",
] as const satisfies readonly ReplyKind[];

export interface CustomCase {
  customer_name: string;
  amount_inr: number;
  failure_class: number;
  reply_text: string | null;
  reply: ReplyKind | null;
  retries_used: number;
  voice_attempts: number;
  /** WhatsApp nudges already sent before the run — seeded as prior dispatches
   * so a live run can start at the nudge cap, where the agent's next move is a call. */
  whatsapp_nudges_used: number;
  days_overdue: number | null;
  outcome_event: string | null;
  playbook: string | null;
  // Time of day (IST, "HH:MM") to run this case at - lets an authored case
  // demo a time-dependent guardrail (TRAI quiet hours) deliberately. The date
  // is always "today"; null runs at the real current time.
  clock_ist: string | null;
}

export interface SavedScenario {
  slug: string;
  name: string;
  description: string;
  payload: Scenario;
  created_at: string;
  updated_at: string;
}

export interface CaseShape {
  count: number;
  /** Relative weights over failure classes 1–4; normalised by the backend. */
  class_mix: Record<string, number>;
  amount_scale: number;
  amount_spread: number;
  amount_min_inr: number | null;
  amount_max_inr: number | null;
}

export interface EdgeCases {
  reply_mix: Partial<Record<ReplyKind, number>>;
  reply_texts: Partial<Record<ReplyKind, string>>;
  retries_already_used: number;
  voice_attempts_used: number;
  /** ISO string with an IST offset. Sets the wall clock the gates are read at. */
  clock_ist: string | null;
  late_settlement_pct: number;
  cross_device_pct: number;
  days_overdue: number;
}

export interface PolicyOverrides {
  max_discount_pct: number | null;
  max_intervention_amount_minor: number | null;
  allow_partial_payment: boolean | null;
  min_partial_payment_pct: number | null;
  allowed_channels: string[] | null;
  allowed_actions: string[] | null;
}

export interface Scenario {
  name: string;
  description: string;
  cases: CaseShape;
  edge_cases: EdgeCases;
  policy: PolicyOverrides;
  locale: Locale;
  custom_cases: CustomCase[];
  live_diagnosis: boolean;
}

export interface ScenarioPreset {
  key: string;
  name: string;
  description: string;
  scenario: Scenario;
}

/* ── Stream events (backend/application/simulation/runner.py) ───────────── */

export interface SimStart {
  run_id: string;
  total: number;
  at_risk_inr: number;
  concurrency: number;
  clock_ist: string;
  scenario: string;
  projected_inr: number;
  projected_band: [number, number];
}

export interface SimProgress {
  done: number;
  total: number;
  /** Cases per second, measured over the run so far. */
  rate: number;
  p50_ms: number;
  p95_ms: number;
  workers_busy: number;
  peak_workers: number;
  elapsed_s: number;
}

/** One feature's effect on a case's probability, in percentage points. */
export interface Contribution {
  feature: string;
  detail: string;
  delta_pp: number;
}

/** Which outcome lane a finished case landed in (backend simulation/triage.py). */
export type TriageLane = "closed" | "human" | "postponed" | "in_flight";

export interface SimCase {
  transaction_id: string;
  failure_class: number;
  amount_inr: number;
  customer_name: string;
  final_state: LifecycleStatus;
  stopped_by: StoppingRule | null;
  p: number;
  base_rate: number;
  contributions: Contribution[];
  elapsed_ms: number;
  /** Would production spend an advisory model call on this case? */
  needs_model: boolean;
  triage_lane: TriageLane;
  triage_reasons: string[];
}

/**
 * Deterministic explanation of the model route shown in a case panel.
 * `provider: "deterministic"` marks a seeded route that never called a model
 * — used by the live theatre to distinguish a planned opening from a taken one.
 */
export interface RouteDecision {
  task: string;
  tier: "nano" | "mini" | "full";
  provider: "openai" | "gemini" | "deterministic";
  model: string;
  reason: string;
  raised_by: string[];
  escalated_from: string | null;
  latency_ms: number;
  tokens: number | null;
}

/* ── Live theatre (backend/application/operations/live_session.py) ──────── */

export interface LiveStart {
  transaction_id: string;
  failure_class: number;
  amount_inr: number;
  customer_name: string;
}

export interface LiveDiagnosis {
  root_cause: string;
  playbook: string;
  confidence: number;
}

/** `phase` is "flagged" on open and "stopped" | "escalated" when a screened
 * reply (opt-out / dispute) ends the session before any model is consulted. */
export interface LiveStep {
  phase: string;
  label?: string;
  rule?: string;
}

/**
 * Wire shape of `AgentDecision.as_dict()` (backend/application/operations/agent_tools.py).
 * `requested_tool` differing from `tool` is the sandbox's refusal made visible:
 * the model asked for `requested_tool`, the sandbox said no via `sandbox_reason`
 * (verbatim, user-facing copy), and `tool` is what actually happened instead.
 */
export interface LiveDecision {
  tool: string;
  action: string | null;
  channel: string | null;
  terminal_state: string | null;
  allowed: boolean;
  reason: string;
  stopping_rule: string | null;
  route_decision: RouteDecision;
  model_reason: string;
  sandbox_reason: string | null;
  message: string | null;
  discount_pct: number | null;
  requested_tool: string | null;
  scheduled_for: string | null;
  /** The amount actually being requested by this turn's tool, in paise — the
   * case's full amount for most tools, the first payment for a partial plan.
   * Null when the decision named no payment tool (e.g. a WhatsApp nudge). */
  request_amount_minor: number | null;
  /** Set only by `OFFER_PARTIAL_PLAN`: how many days until the booked balance is due. */
  deadline_days: number | null;
  /** Advisory score (0–1) from the demo repayment model, fed into the DECIDE
   * prompt. Null when the model was not consulted for this turn. */
  repayment_probability: number | null;
  /** "high" | "medium" | "low" — the band that goes with `repayment_probability`. */
  repayment_band: string | null;
}

/**
 * `reminder` — emitted when the customer commits to a pay date in the live
 * chat, or the agent books a partial-payment plan. The backend has written the
 * date onto the case (so the calendar picks it up on its next load); the
 * client shows `message` as a toast.
 */
export interface LiveReminder {
  date: string;
  kind: "promise_to_pay" | "partial_payment";
  label: string;
  amount_inr: number;
  message: string;
}

export interface LiveCallOffer {
  assistant: unknown;
  public_key: string | null;
  call_session_id: number | null;
}

/**
 * `dispatch` — the non-payment-card half of a channel dispatch (WhatsApp,
 * voice, fee waiver). A payment action's card comes from the richer
 * `artifact` event instead (`PaymentArtifact` in lib/types.ts), emitted
 * alongside this one for the same turn.
 */
export interface LiveDispatchEvent {
  channel: string;
  delivered: boolean;
  simulated: boolean;
  reference: string | null;
  detail: string | null;
}

/**
 * Wire shape of `live_session._bounds()`. Matches `Bounds` in lib/bounds.ts
 * field for field except `nextActionAt`, which travels as an ISO string —
 * parsed once, in useLiveSession, at the boundary.
 */
export interface LiveBoundsWire {
  retries: { used: number; cap: number; exhausted: boolean };
  voice: { used: number; cap: number; exhausted: boolean };
  totalDispatches: number;
  channelsAllowed: string[];
  channelsUsed: string[];
  channelsRemaining: string[];
  armedRule: string | null;
  firedRule: string | null;
  nextActionAt: string | null;
  inQuietHours: boolean;
  closed: boolean;
}

/** POST /live/sessions/{id}/call/web — gated Vapi config, reserved for Part 6. */
export interface LiveCallWebConfig {
  allowed: boolean;
  provider: string;
  gated: boolean;
  assistant: unknown;
  public_key: string | null;
  call_session_id: number | null;
  reason: string;
}

export interface Throughput {
  elapsed_s: number;
  cases_per_sec: number;
  p50_ms: number;
  p95_ms: number;
  concurrency: number;
  peak_workers: number;
}

export interface SimComplete {
  run_id: string;
  scenario: string;
  /** Measured. */
  recovered_inr: number;
  at_risk_inr: number;
  grrr: number;
  /** Modelled. */
  projected_inr: number;
  projected_band: [number, number];
  projected_cases: number;
  /** Held by a deferring stopping rule — neither recovered nor lost. */
  deferred_inr: number;
  counts: {
    total: number;
    recovered: number;
    escalated: number;
    stopped: number;
    waiting: number;
    rules_fired: number;
  };
  /**
   * How the book split by who made the call. `closed + human + postponed +
   * in_flight` sums to `total`; `llm` overlaps them all — a case can consult the
   * model and still close without a human. The batch keeps diagnosis offline, so
   * `model_calls_saved` is what this run avoided against production.
   */
  routing: {
    total: number;
    llm: number;
    llm_share: number;
    deterministic_only: number;
    closed: number;
    human: number;
    postponed: number;
    in_flight: number;
    model_calls_made: number;
    model_calls_saved: number;
    llm_reasons: Record<string, number>;
  };
  stopping_rules_by_name: Record<string, number>;
  by_class: Record<string, unknown>;
  funnel: Record<string, number>;
  throughput: Throughput;
  /** Metrics-shaped and scoped to this run, so the existing zone-1 components read it directly. */
  metrics: import("@/lib/types").Metrics;
}

/* ── Decision trace (backend/application/simulation/trace.py) ───────────── */

export interface Budgets {
  retries_used: number;
  retries_cap: number;
  voice_used: number;
  voice_cap: number;
  channels_used: string[];
  dispatches: number;
}

export interface TraceStep {
  step: number;
  node: string;
  decision: string;
  reason: string;
  rule: StoppingRule | null;
  outcome: string;
  at: string;
  /** What the agent still had left when this step ran. */
  allowed_at_this_moment: Budgets;
}

/* ── Defaults ──────────────────────────────────────────────────────────── */

/**
 * A neutral starting scenario, used before the presets have loaded and as the
 * base for "Custom". Mid-morning IST so no gate is armed until the user arms one.
 */
export function defaultScenario(locale: Locale = "en"): Scenario {
  return {
    name: "Custom scenario",
    description: "",
    cases: {
      count: 200,
      class_mix: { "1": 1, "2": 1, "3": 1, "4": 1 },
      amount_scale: 1,
      amount_spread: 0.35,
      amount_min_inr: null,
      amount_max_inr: null,
    },
    edge_cases: {
      reply_mix: { cooperative: 6, p2p: 2, silent: 1, opt_out: 1, dispute: 1 },
      reply_texts: {},
      retries_already_used: 0,
      voice_attempts_used: 0,
      clock_ist: null,
      late_settlement_pct: 0,
      cross_device_pct: 0,
      days_overdue: 35,
    },
    policy: {
      max_discount_pct: null,
      max_intervention_amount_minor: null,
      allow_partial_payment: null,
      min_partial_payment_pct: null,
      allowed_channels: null,
      allowed_actions: null,
    },
    locale,
    custom_cases: [],
    live_diagnosis: false,
  };
}

/** The IST hour a scenario's clock is set to, or null when it follows real time. */
export function scenarioHour(scenario: Scenario): number | null {
  const iso = scenario.edge_cases.clock_ist;
  if (!iso) return null;
  const match = /T(\d{2}):/.exec(iso);
  return match ? Number(match[1]) : null;
}

/** Build an IST-offset ISO string for an hour of the scenario's reference day. */
export function withScenarioHour(scenario: Scenario, hour: number): string {
  const iso = scenario.edge_cases.clock_ist;
  const day = iso ? iso.slice(0, 10) : "2026-03-04";
  return `${day}T${String(hour).padStart(2, "0")}:00:00+05:30`;
}

/** TRAI quiet hours are 20:00–09:00 IST — mirrors lib/bounds.ts. */
export function armsQuietHours(scenario: Scenario): boolean {
  const hour = scenarioHour(scenario);
  if (hour === null) return false;
  return hour >= 20 || hour < 9;
}

/** Total weight in a mix, so a UI can render each entry as a share. */
export function mixTotal(mix: Record<string, number>): number {
  return Object.values(mix).reduce((sum, weight) => sum + (weight > 0 ? weight : 0), 0);
}

export function mixShare(mix: Record<string, number>, key: string): number {
  const total = mixTotal(mix);
  return total > 0 ? (mix[key] ?? 0) / total : 0;
}


const SCENARIO_SHARE_VERSION = 1;

/** Encode a scenario as compact, versioned base64url for a shareable query string. */
export function encodeScenario(scenario: Scenario): string {
  const json = JSON.stringify({ v: SCENARIO_SHARE_VERSION, s: scenario });
  const bytes = new TextEncoder().encode(json);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Decode a shareable scenario without allowing malformed query data to reach the form. */
export function decodeScenario(encoded: string): Scenario | null {
  try {
    const padded = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (!parsed || typeof parsed !== "object" || !("v" in parsed) || !("s" in parsed)) return null;
    const version = (parsed as { v: unknown }).v;
    const scenario = (parsed as { s: unknown }).s;
    if (version !== SCENARIO_SHARE_VERSION || !scenario || typeof scenario !== "object") return null;
    if (!isScenarioShape(scenario)) return null;
    return scenario;
  } catch {
    return null;
  }
}


function isScenarioShape(value: object): value is Scenario {
  const candidate = value as Partial<Scenario>;
  return (
    typeof candidate.name === "string" &&
    typeof candidate.description === "string" &&
    typeof candidate.locale === "string" &&
    typeof candidate.live_diagnosis === "boolean" &&
    Array.isArray(candidate.custom_cases) &&
    Boolean(candidate.cases && candidate.edge_cases && candidate.policy)
  );
}
