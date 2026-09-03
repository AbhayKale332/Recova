/**
 * Typed fetch client for the Recova backend (Vision Appendix A).
 *
 * Reads take an AbortSignal and `cache: "no-store"`. Every non-2xx throws an
 * ApiError carrying the status, method and path so a Toast can say something
 * specific instead of "something went wrong".
 */

import type {
  AssistantReply,
  AuditList,
  CallData,
  Conversation,
  ConversationMessage,
  EscalationTicket,
  InvoiceItem,
  LifecycleStatus,
  Metrics,
  PaymentLinkResult,
  PaymentLinkStatus,
  PolicyResponse,
  PolicyVerdict,
  RecoverBatchResult,
  ScreenVerdict,
  SeedResult,
  SubscriptionItem,
  TransactionDetail,
  TransactionList,
  TransactionRow,
} from "@/lib/types";
import type { Locale } from "@/lib/i18n/dictionaries/en";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ?? "http://localhost:8000";

const ROOT = `${API_BASE}/api/v1`;

/** A non-2xx response. Carries what a human needs to act on it. */
export class ApiError extends Error {
  readonly status: number;
  readonly path: string;
  readonly method: string;
  readonly detail: string | null;

  constructor(opts: { status: number; path: string; method: string; detail: string | null }) {
    super(
      opts.detail
        ? `${opts.method} ${opts.path} → ${opts.status}: ${opts.detail}`
        : `${opts.method} ${opts.path} → ${opts.status}`,
    );
    this.name = "ApiError";
    this.status = opts.status;
    this.path = opts.path;
    this.method = opts.method;
    this.detail = opts.detail;
  }
}

/** The backend never answered — wrong base URL, server down, CORS. */
export class NetworkError extends Error {
  readonly path: string;
  readonly base: string;

  constructor(path: string, cause?: unknown) {
    super(`Could not reach ${API_BASE}${path}`);
    this.name = "NetworkError";
    this.path = path;
    this.base = API_BASE;
    this.cause = cause;
  }
}

export function isAbort(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const text = await response.text();
    if (!text) return null;
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        const detail = (parsed as { detail: unknown }).detail;
        return typeof detail === "string" ? detail : JSON.stringify(detail);
      }
    } catch {
      // Not JSON — fall through to the raw body.
    }
    return text.slice(0, 300);
  } catch {
    return null;
  }
}

async function request<T>(
  method: string,
  path: string,
  opts: { query?: Query; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const url = `${ROOT}${withQuery(path, opts.query)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      cache: "no-store",
      signal: opts.signal,
      headers: opts.body === undefined ? undefined : { "content-type": "application/json" },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new NetworkError(path, error);
  }

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      path: withQuery(path, opts.query),
      method,
      detail: await readDetail(response),
    });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T,>(path: string, query?: Query, signal?: AbortSignal) =>
  request<T>("GET", path, { query, signal });

const post = <T,>(path: string, body?: unknown, query?: Query, signal?: AbortSignal) =>
  request<T>("POST", path, { body: body ?? {}, query, signal });

/* ── Reads ─────────────────────────────────────────────────────────────── */

export interface TransactionQuery {
  failure_class?: number | null;
  status?: LifecycleStatus | null;
  archetype?: string | null;
  q?: string | null;
  limit?: number;
  offset?: number;
}

export const api = {
  health: (signal?: AbortSignal) =>
    get<{ status: string; service: string }>("/health", undefined, signal),

  metrics: (signal?: AbortSignal) => get<Metrics>("/metrics", undefined, signal),

  transactions: (query: TransactionQuery = {}, signal?: AbortSignal) =>
    get<TransactionList>("/transactions", query as Query, signal),

  transaction: (id: string, signal?: AbortSignal) =>
    get<TransactionDetail>(`/transactions/${encodeURIComponent(id)}`, undefined, signal),

  conversation: (id: string, signal?: AbortSignal) =>
    get<Conversation>(`/transactions/${encodeURIComponent(id)}/conversation`, undefined, signal),

  calls: (id: string, signal?: AbortSignal) =>
    get<{ calls: CallData[] }>(`/transactions/${encodeURIComponent(id)}/calls`, undefined, signal),

  paymentLinkStatus: (id: string, signal?: AbortSignal) =>
    get<PaymentLinkStatus>(
      `/transactions/${encodeURIComponent(id)}/payment-link/status`,
      undefined,
      signal,
    ),

  audit: (
    query: { transaction_id?: string | null; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) => get<AuditList>("/audit", query as Query, signal),

  escalations: (signal?: AbortSignal) =>
    get<EscalationTicket[]>("/escalations", undefined, signal),

  policy: (signal?: AbortSignal) => get<PolicyResponse>("/policy", undefined, signal),

  subscriptions: (signal?: AbortSignal) =>
    get<SubscriptionItem[]>("/subscriptions", undefined, signal),

  invoices: (signal?: AbortSignal) => get<InvoiceItem[]>("/invoices", undefined, signal),

  /* ── Mutations ───────────────────────────────────────────────────────── */

  setStatus: (id: string, body: { status: LifecycleStatus; note?: string | null }) =>
    post<TransactionRow>(`/transactions/${encodeURIComponent(id)}/status`, body),

  addNote: (id: string, note: string) =>
    post<{ id: number; note: string; timestamp: string }>(
      `/transactions/${encodeURIComponent(id)}/note`,
      { note },
    ),

  sendMessage: (id: string, body: { body: string; ai_drafted?: boolean }) =>
    post<ConversationMessage>(`/transactions/${encodeURIComponent(id)}/messages`, body),

  draftMessage: (id: string, prompt: string) =>
    post<{ draft: string }>(`/transactions/${encodeURIComponent(id)}/messages/draft`, { prompt }),

  createPaymentLink: (id: string) =>
    post<PaymentLinkResult>(`/transactions/${encodeURIComponent(id)}/payment-link`),

  startCall: (id: string) => post<CallData>(`/transactions/${encodeURIComponent(id)}/call/start`),

  /** The backend caps a batch at 50 transaction ids. */
  recoverBatch: (transaction_ids: string[], locale: Locale) =>
    post<RecoverBatchResult>("/transactions/recover-batch", { transaction_ids, locale }),

  simulate: (failure_class?: number) =>
    post<TransactionRow>("/transactions/simulate", {}, { failure_class }),

  resolveEscalation: (ticketId: number) =>
    post<{ id: number; transaction_id: string; status: string }>(
      `/escalations/${ticketId}/resolve`,
    ),

  updatePolicy: (patch: {
    max_discount_pct?: number;
    max_intervention_amount_minor?: number;
    allowed_actions?: string[];
    allowed_channels?: string[];
  }) => request<PolicyResponse>("PATCH", "/policy", { body: patch }),

  validateAction: (body: {
    action: string;
    channel?: string | null;
    discount_pct?: number | null;
    amount_inr?: number | null;
  }) => post<PolicyVerdict>("/policy/validate", body),

  screenMessage: (message: string) => post<ScreenVerdict>("/policy/screen", { message }),

  createSubscription: (body: {
    customer_name: string;
    plan: string;
    amount_inr: number;
    next_debit_date: string;
    salary_day?: number;
  }) => post<SubscriptionItem>("/subscriptions", body),

  createInvoice: (body: {
    buyer_name: string;
    amount_inr: number;
    issue_date: string;
    due_date: string;
    terms?: string;
  }) => post<InvoiceItem>("/invoices", body),

  assistantChat: (body: {
    message: string;
    locale: Locale;
    context?: { route?: string; focused_transaction_id?: string; class_filter?: number };
  }) => post<AssistantReply>("/assistant/chat", body),

  seed: () => post<SeedResult>("/admin/seed"),
};

/** The SSE URL for a single case's live run. Consumed by useRecoveryRun. */
export function runStreamUrl(id: string, locale: Locale): string {
  return `${ROOT}/transactions/${encodeURIComponent(id)}/run?locale=${locale}`;
}

/** The most a single recover-batch call accepts (backend Field max_length). */
export const BATCH_LIMIT = 50;
