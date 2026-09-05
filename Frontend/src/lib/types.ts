/**
 * Wire types for the Recova backend.
 *
 * Transcribed from Frontend/.Agents/Frontend-Vision.md Appendix B and verified
 * against a live server (backend/application/endpoints/*.py). Do not "improve"
 * these shapes — they are the contract.
 */

export interface ClassMetric {
  at_risk_inr: number; recovered_inr: number; count: number;
  recovered_count: number; recovery_rate: number;
  top_playbook: string | null; avg_time_to_recovery_seconds: number;
}

export interface Funnel {
  at_risk: number; intervened: number; recovered: number;
  escalated: number; cancelled: number; failed: number;
}

export interface TimePoint { date: string; recovered_inr: number; cumulative_inr: number; }

export interface Metrics {
  at_risk_inr: number; recovered_inr: number; in_flight_inr: number; lost_inr: number;
  grrr: number;
  by_class: Record<string, ClassMetric>;
  funnel: Funnel;
  channel_breakdown: Record<string, { dispatched: number; recovered: number }>;
  time_series: TimePoint[];
  stopping_rules_by_name: Record<string, number>;
  counts: {
    total: number; interventions: number; escalations: number;
    stopping_rules_fired: number; recovered: number; cancelled: number; failed: number;
  };
  avg_time_to_recovery_seconds: number;
}

export type LifecycleStatus =
  | "PENDING" | "DIAGNOSING" | "WAITING" | "INTERVENING"
  | "RECOVERED" | "ESCALATED" | "CANCELLED" | "FAILED";

export interface TransactionRow {
  serial: number; transaction_id: string; razorpay_payment_id: string;
  failure_class: number; class_label: string | null; archetype: string | null;
  ai_tag: string | null; is_at_risk: boolean; confidence: number | null;
  event_type: string | null; error_code: string | null;
  status: LifecycleStatus; amount_inr: number; currency: string;
  customer_name: string | null; customer_contact_masked: string;
  time_to_recovery_seconds: number | null;
  playbook: string | null; channel: string | null; stopping_rule: string | null;
  created_at: string; updated_at: string;
}

export interface TransactionList { total: number; items: TransactionRow[]; }

export interface AuditEntry {
  id: number; transaction_id: string; node_name: string; action_type: string;
  payload: Record<string, unknown>; outcome: string; timestamp: string;
}

export interface TransactionDetail extends TransactionRow {
  diagnosis: { root_cause?: string; recommended_playbook?: string; confidence?: number };
  audit_trail: AuditEntry[];
}

export interface AuditList { total: number; items: AuditEntry[]; }

export interface EscalationTicket {
  id: number; transaction_id: string; reason: string;
  rule: string | null; status: string; created_at: string;
}

export interface ConversationMessage {
  id: number; channel: string;
  direction: "OUTBOUND" | "INBOUND";
  sender: "AGENT" | "CUSTOMER" | "SYSTEM";
  body: string; status: "SENT" | "DELIVERED" | "READ";
  seq: number; meta: Record<string, unknown> | null; created_at: string;
}

export interface CallData {
  id: number; status: string; duration_sec: number;
  outcome: string | null; provider: string | null; started_at?: string;
  turns: { speaker: "AGENT" | "CUSTOMER"; text: string; seq: number; at_offset_sec: number }[];
}

export interface Conversation { messages: ConversationMessage[]; call: CallData | null; }

export interface PolicyResponse {
  policy: {
    max_discount_pct: number; max_intervention_amount_minor: number;
    allow_partial_payment: boolean; min_partial_payment_pct: number;
    allowed_channels: string[]; allowed_actions: string[];
  };
  money_moving_actions: string[];
  stopping_rules: { name: string; description: string }[];
}

export interface SubscriptionItem {
  transaction_id: string; serial: number; customer_name: string; plan: string;
  amount_inr: number; cycle: string; next_debit_date: string; salary_day: number;
  mandate_status: string; retry_count: number; retry_cap: number;
  predicted_fail: boolean; status: string;
}

export interface InvoiceItem {
  transaction_id: string; serial: number; buyer_name: string; invoice_no: string;
  amount_inr: number; issue_date: string; due_date: string; terms: string;
  days_overdue: number; aging_bucket: string; p2p_date: string | null;
  next_reminder_date: string; status: string; open: boolean;
}

/* ── Backend enumerations (Appendix B; mirrored from application/constants.py) ── */

export const LIFECYCLE_STATUSES = [
  "PENDING", "DIAGNOSING", "WAITING", "INTERVENING",
  "RECOVERED", "ESCALATED", "CANCELLED", "FAILED",
] as const satisfies readonly LifecycleStatus[];

export const NODE_NAMES = [
  "INGEST", "DIAGNOSE", "WAIT", "EXECUTE_INTERVENTION", "RECONCILE", "OPERATOR",
] as const;
export type NodeName = (typeof NODE_NAMES)[number];

export const ACTION_TYPES = [
  "STATE_TRANSITION", "INTERVENTION_DISPATCH", "RETRY_SCHEDULED", "ESCALATION",
] as const;
export type ActionType = (typeof ACTION_TYPES)[number];

export const OUTCOMES = ["SUCCESS", "FAILURE", "ESCALATED"] as const;
export type Outcome = (typeof OUTCOMES)[number];

export const CHANNELS = ["WHATSAPP", "VOICE", "PAYMENT_LINK"] as const;
export type Channel = (typeof CHANNELS)[number];

export const ACTIONS = [
  "SEND_WHATSAPP", "VOICE_CALL", "OFFER_FEE_WAIVER",
  "GENERATE_PAYMENT_LINK", "GENERATE_QR_CODE", "OFFER_PARTIAL_PLAN",
  "RETRY_CHARGE", "CANCEL_SUBSCRIPTION",
] as const;
export type Action = (typeof ACTIONS)[number];

export const PLAYBOOKS = [
  "REROUTE_RAIL", "PREAUTH_LINK", "UPI_AUTOPAY_NUDGE", "NEGOTIATION",
  "SALARY_CYCLE_SEQUENCER", "MANDATE_REFRESH", "P2P_TRACKER",
] as const;
export type Playbook = (typeof PLAYBOOKS)[number];

export const STOPPING_RULES = [
  "NO_DOUBLE_CHARGE", "CROSS_DEVICE_COMPLETION", "RBI_MAX_RETRIES", "EXPLICIT_CANCEL",
  "OPT_OUT", "DISPUTE_FREEZE", "TRAI_QUIET_HOURS", "VOICE_ATTEMPT_CAP",
] as const;
export type StoppingRule = (typeof STOPPING_RULES)[number];

export const ESCALATION_STATUSES = ["OPEN", "RESOLVED"] as const;
export type EscalationStatus = (typeof ESCALATION_STATUSES)[number];

/**
 * Archetypes the seeder writes into transaction metadata. CLASS_n rows are real
 * recovery cases; HEALTHY rows are context volume (never at risk) and
 * NON_RECOVERABLE rows are at risk but outside the engine's reach.
 * Source: backend/application/operations/batch_seed.py.
 */
export const ARCHETYPES = [
  "CLASS_1", "CLASS_2", "CLASS_3", "CLASS_4", "HEALTHY", "NON_RECOVERABLE",
] as const;
export type Archetype = (typeof ARCHETYPES)[number];

/* ── Endpoint response shapes that Appendix B does not name ── */

export interface RecoverBatchResult {
  total: number;
  recovered: number;
  results: { transaction_id: string; final_state: LifecycleStatus | null }[];
}

export interface PaymentLinkResult {
  url: string; razorpay_id: string; simulated: boolean; message: ConversationMessage;
}

export interface PaymentLinkStatus {
  paid: boolean; status: string; current_state: LifecycleStatus;
}

/** Wire shape of `PaymentArtifact.as_dict()` (application/entities/payment_artifact.py). */
export const PAYMENT_ARTIFACT_KINDS = ["LINK", "UPI_LINK", "QR"] as const;
export type PaymentArtifactKind = (typeof PAYMENT_ARTIFACT_KINDS)[number];

export const PAYMENT_ARTIFACT_STATUSES = [
  "created", "paid", "partially_paid", "expired", "closed",
] as const;
export type PaymentArtifactStatus = (typeof PAYMENT_ARTIFACT_STATUSES)[number];

export interface PaymentArtifact {
  id: number;
  transaction_id: string;
  kind: PaymentArtifactKind;
  provider_id: string | null;
  /** short_url for a link; null for a QR. */
  url: string | null;
  /** QR image; null for a link. */
  image_url: string | null;
  /** What this artifact asks for now, in paise. */
  amount_minor: number;
  accept_partial: boolean;
  first_min_partial_minor: number | null;
  deadline: string | null;
  status: PaymentArtifactStatus;
  amount_paid_minor: number;
  /** True when Razorpay never actually minted this — no MCP, no SDK keys. */
  simulated: boolean;
  detail: "mcp" | "sdk" | "simulated";
  created_at: string;
}

export interface PolicyVerdict { approved: boolean; reason: string; }

export interface ScreenVerdict {
  disposition: "CONTINUE" | "TERMINATE" | "ESCALATE";
  rule: StoppingRule | null;
  reason: string;
}

/** POST /admin/seed — the live server also returns a per-state tally. */
export interface SeedResult { seeded: number; by_state: Record<string, number>; }

export interface AssistantReply { reply: string; action: unknown }
