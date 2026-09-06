"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useToast } from "@/components/Toast";
import { useApi, useMutation, describeError } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatAbsolute, humanizeEnum, paiseToRupees, rupeesToPaise } from "@/lib/format";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { ACTIONS, CHANNELS, type PolicyResponse, type PolicyVerdict, type ScreenVerdict } from "@/lib/types";

/**
 * /console/guardrails — the limits the engine works inside.
 *
 * Three surfaces, all reading the real book:
 *  1. the editable policy (PATCH /policy) and the fixed stopping rules,
 *  2. the policy sandbox — the same gate every recovery step clears,
 *  3. the escalation queue the engine hands to a human.
 */
export function GuardrailsScreen() {
  const { t } = useI18n();

  const loadPolicy = useCallback((signal: AbortSignal) => api.policy(signal), []);
  const policyState = useApi<PolicyResponse>(loadPolicy);

  if (policyState.isInitialLoad) return <LoadingState rows={6} />;
  if (policyState.error && !policyState.data) {
    return <ErrorState error={policyState.error} onRetry={policyState.refresh} />;
  }
  if (!policyState.data) {
    return <EmptyState title={t.states.emptyTitle} />;
  }

  const data = policyState.data;

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-[17px] font-semibold tracking-tight">{t.guardrails.title}</h1>
        <p className="mt-0.5 max-w-[68ch] text-[13px] text-[var(--muted)]">{t.guardrails.subtitle}</p>
      </header>

      <PolicyPanel data={data} onSaved={() => policyState.refresh()} />
      <StoppingRules rules={data.stopping_rules} />
      <Sandbox data={data} />
      <EscalationQueue />
    </div>
  );
}

function Section({
  title,
  desc,
  children,
  aside,
}: {
  title: string;
  desc?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {desc ? <p className="mt-0.5 max-w-[64ch] text-[13px] text-[var(--muted)]">{desc}</p> : null}
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

/* ── Policy ─────────────────────────────────────────────────────────────── */

interface PolicyDraft {
  max_discount_pct: number;
  max_intervention_rupees: number;
  allow_partial_payment: boolean;
  min_partial_payment_pct: number;
  allowed_channels: string[];
  allowed_actions: string[];
}

function toDraft(p: PolicyResponse["policy"]): PolicyDraft {
  return {
    max_discount_pct: p.max_discount_pct,
    max_intervention_rupees: paiseToRupees(p.max_intervention_amount_minor),
    allow_partial_payment: p.allow_partial_payment,
    min_partial_payment_pct: p.min_partial_payment_pct,
    allowed_channels: [...p.allowed_channels],
    allowed_actions: [...p.allowed_actions],
  };
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join();
}

function PolicyPanel({ data, onSaved }: { data: PolicyResponse; onSaved: (next: PolicyResponse) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [draft, setDraft] = useState<PolicyDraft>(() => toDraft(data.policy));

  // A refetch after a save (or an edit from elsewhere) hands us a new policy
  // object — reseed the form during render, the way useApi adjusts state on a
  // new request identity rather than in an effect.
  const [seenPolicy, setSeenPolicy] = useState(data.policy);
  if (seenPolicy !== data.policy) {
    setSeenPolicy(data.policy);
    setDraft(toDraft(data.policy));
  }

  const dirty = useMemo(() => {
    const base = toDraft(data.policy);
    return (
      base.max_discount_pct !== draft.max_discount_pct ||
      base.max_intervention_rupees !== draft.max_intervention_rupees ||
      base.allow_partial_payment !== draft.allow_partial_payment ||
      base.min_partial_payment_pct !== draft.min_partial_payment_pct ||
      !sameSet(base.allowed_channels, draft.allowed_channels) ||
      !sameSet(base.allowed_actions, draft.allowed_actions)
    );
  }, [data.policy, draft]);

  const save = useMutation(api.updatePolicy);

  const onSave = useCallback(async () => {
    const result = await save.run({
      max_discount_pct: draft.max_discount_pct,
      max_intervention_amount_minor: rupeesToPaise(draft.max_intervention_rupees),
      allow_partial_payment: draft.allow_partial_payment,
      min_partial_payment_pct: draft.min_partial_payment_pct,
      allowed_actions: draft.allowed_actions,
      allowed_channels: draft.allowed_channels,
    });
    if (result.ok) {
      onSaved(result.data);
      toast.success(t.guardrails.policySaved);
    } else {
      toast.failure(t.guardrails.policySaveFailed, describeError(result.error));
    }
  }, [draft, onSaved, save, t.guardrails, toast]);

  const num = "tabular w-24 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[13px] outline-none";

  return (
    <Section
      title={t.guardrails.policyTitle}
      desc={t.guardrails.policyDesc}
      aside={
        <div className="flex items-center gap-2">
          {dirty ? (
            <button
              type="button"
              onClick={() => setDraft(toDraft(data.policy))}
              className="rounded border border-[var(--border)] px-2.5 py-1 text-[12px] font-medium"
            >
              {t.guardrails.discardChanges}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || save.pending}
            className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white transition-opacity duration-150 disabled:opacity-50"
          >
            {save.pending ? t.guardrails.savingPolicy : t.guardrails.savePolicy}
          </button>
        </div>
      }
    >
      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-[13px] font-medium">{t.guardrails.maxDiscount}</dt>
          <dd className="flex items-center gap-1.5">
            <input
              type="number"
              min={0}
              max={100}
              value={draft.max_discount_pct}
              onChange={(e) =>
                setDraft({ ...draft, max_discount_pct: clamp(Number(e.target.value), 0, 100) })
              }
              className={num}
            />
            <span className="text-[13px] text-[var(--muted)]">%</span>
          </dd>
        </div>

        <div className="flex items-center justify-between gap-3">
          <dt className="text-[13px] font-medium">{t.guardrails.maxIntervention}</dt>
          <dd className="flex items-center gap-1.5">
            <span className="text-[13px] text-[var(--muted)]">₹</span>
            <input
              type="number"
              min={0}
              step={100}
              value={draft.max_intervention_rupees}
              onChange={(e) =>
                setDraft({ ...draft, max_intervention_rupees: Math.max(0, Number(e.target.value)) })
              }
              className={`${num} w-32`}
            />
          </dd>
        </div>

        <div className="flex items-center justify-between gap-3">
          <dt className="text-[13px] font-medium">{t.guardrails.allowPartial}</dt>
          <dd>
            <button
              type="button"
              role="switch"
              aria-checked={draft.allow_partial_payment}
              onClick={() =>
                setDraft({ ...draft, allow_partial_payment: !draft.allow_partial_payment })
              }
              className={`relative h-6 w-11 rounded-full transition-colors duration-150 ${
                draft.allow_partial_payment ? "bg-[var(--accent)]" : "bg-neutral-300"
              }`}
            >
              <span
                className={`absolute top-0.5 size-5 rounded-full bg-white transition-transform duration-150 ${
                  draft.allow_partial_payment ? "translate-x-[22px]" : "translate-x-0.5"
                }`}
              />
            </button>
          </dd>
        </div>

        <div className="flex items-center justify-between gap-3">
          <dt className="text-[13px] font-medium">{t.guardrails.minPartial}</dt>
          <dd className="flex items-center gap-1.5">
            <input
              type="number"
              min={0}
              max={100}
              value={draft.min_partial_payment_pct}
              disabled={!draft.allow_partial_payment}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  min_partial_payment_pct: clamp(Number(e.target.value), 0, 100),
                })
              }
              className={`${num} disabled:opacity-50`}
            />
            <span className="text-[13px] text-[var(--muted)]">%</span>
          </dd>
        </div>
      </dl>

      <ToggleRow
        label={t.guardrails.channels}
        options={CHANNELS as unknown as string[]}
        selected={draft.allowed_channels}
        onChange={(next) => setDraft({ ...draft, allowed_channels: next })}
      />
      <ToggleRow
        label={t.guardrails.allowedActions}
        options={ACTIONS as unknown as string[]}
        selected={draft.allowed_actions}
        moneyMoving={data.money_moving_actions}
        moneyMovingLabel={t.guardrails.moneyMoving}
        onChange={(next) => setDraft({ ...draft, allowed_actions: next })}
      />
    </Section>
  );
}

function ToggleRow({
  label,
  options,
  selected,
  onChange,
  moneyMoving = [],
  moneyMovingLabel,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  moneyMoving?: string[];
  moneyMovingLabel?: string;
}) {
  const toggle = (opt: string) =>
    onChange(selected.includes(opt) ? selected.filter((x) => x !== opt) : [...selected, opt]);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] font-medium">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => {
          const on = selected.includes(opt);
          const money = moneyMoving.includes(opt);
          return (
            <button
              key={opt}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(opt)}
              title={money ? moneyMovingLabel : undefined}
              className={`rounded-full border px-2.5 py-1 text-[12px] font-medium transition-colors duration-150 ${
                on
                  ? "border-[var(--accent)] bg-[var(--accent-wash)] text-[var(--accent-ink)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--ink)]"
              }`}
            >
              {money ? "₹ " : ""}
              {humanizeEnum(opt)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Stopping rules ─────────────────────────────────────────────────────── */

function StoppingRules({ rules }: { rules: PolicyResponse["stopping_rules"] }) {
  const { t } = useI18n();
  return (
    <Section title={t.guardrails.rulesTitle} desc={t.guardrails.rulesDesc}>
      <ul className="grid gap-2 sm:grid-cols-2">
        {rules.map((rule) => (
          <li
            key={rule.name}
            className="rounded-md border border-[var(--border)] bg-[var(--bg)] p-3"
          >
            <p className="text-[12px] font-semibold tracking-wide text-[var(--ink)]">
              {humanizeEnum(rule.name)}
            </p>
            <p className="mt-0.5 text-[12px] text-[var(--muted)]">{rule.description}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/* ── Sandbox ────────────────────────────────────────────────────────────── */

function Sandbox({ data }: { data: PolicyResponse }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"action" | "message">("action");

  return (
    <Section title={t.guardrails.sandboxTitle} desc={t.guardrails.sandboxDesc}>
      <div className="flex gap-1 rounded-md bg-[var(--bg)] p-1 text-[13px] font-medium">
        {(["action", "message"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`flex-1 rounded px-3 py-1.5 transition-colors duration-150 ${
              tab === key ? "bg-[var(--surface)] text-[var(--ink)] shadow-sm" : "text-[var(--muted)]"
            }`}
          >
            {key === "action" ? t.guardrails.tabAction : t.guardrails.tabMessage}
          </button>
        ))}
      </div>

      {tab === "action" ? <ActionSandbox data={data} /> : <MessageSandbox />}
    </Section>
  );
}

function ActionSandbox({ data }: { data: PolicyResponse }) {
  const { t } = useI18n();
  const [action, setAction] = useState<string>(data.policy.allowed_actions[0] ?? ACTIONS[0]);
  const [channel, setChannel] = useState<string>("");
  const [discount, setDiscount] = useState<string>("");
  const [amount, setAmount] = useState<string>("");
  const [verdict, setVerdict] = useState<PolicyVerdict | null>(null);

  const check = useMutation(api.validateAction);

  const run = useCallback(async () => {
    setVerdict(null);
    const result = await check.run({
      action,
      channel: channel || null,
      discount_pct: discount === "" ? null : Number(discount),
      amount_inr: amount === "" ? null : Number(amount),
    });
    if (result.ok) setVerdict(result.data);
  }, [action, amount, channel, check, discount]);

  const field = "rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-[13px] outline-none";

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-[12px] font-medium text-[var(--muted)]">
          {t.guardrails.fAction}
          <select value={action} onChange={(e) => setAction(e.target.value)} className={field}>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {humanizeEnum(a)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-[var(--muted)]">
          {t.guardrails.fChannel}
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className={field}>
            <option value="">{t.guardrails.anyChannel}</option>
            {CHANNELS.map((c) => (
              <option key={c} value={c}>
                {humanizeEnum(c)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-[var(--muted)]">
          {t.guardrails.fDiscount}
          <input
            type="number"
            min={0}
            max={100}
            value={discount}
            onChange={(e) => setDiscount(e.target.value)}
            className={`tabular ${field}`}
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-[var(--muted)]">
          {t.guardrails.fAmount}
          <input
            type="number"
            min={0}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className={`tabular ${field}`}
          />
        </label>
      </div>

      <div>
        <button
          type="button"
          onClick={run}
          disabled={check.pending}
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white disabled:opacity-60"
        >
          {check.pending ? t.guardrails.checking : t.guardrails.checkAction}
        </button>
      </div>

      {verdict ? <Verdict ok={verdict.approved} reason={verdict.reason} /> : null}
    </div>
  );
}

function MessageSandbox() {
  const { t } = useI18n();
  const [message, setMessage] = useState("");
  const [verdict, setVerdict] = useState<ScreenVerdict | null>(null);
  const screen = useMutation(api.screenMessage);

  const run = useCallback(async () => {
    setVerdict(null);
    const result = await screen.run(message);
    if (result.ok) setVerdict(result.data);
  }, [message, screen]);

  return (
    <div className="flex flex-col gap-3">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={3}
        placeholder={t.guardrails.messagePlaceholder}
        className="w-full resize-y rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-2 text-[13px] outline-none"
      />
      <div>
        <button
          type="button"
          onClick={run}
          disabled={screen.pending || !message.trim()}
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white disabled:opacity-60"
        >
          {screen.pending ? t.guardrails.checking : t.guardrails.screenMessage}
        </button>
      </div>

      {verdict ? (
        <Verdict
          ok={verdict.disposition === "CONTINUE"}
          reason={verdict.reason}
          badge={t.guardrails.disposition[verdict.disposition]}
          note={
            verdict.rule
              ? fillTemplate(t.guardrails.matchedRule, { rule: humanizeEnum(verdict.rule) })
              : undefined
          }
        />
      ) : null}
    </div>
  );
}

function Verdict({
  ok,
  reason,
  badge,
  note,
}: {
  ok: boolean;
  reason: string;
  badge?: string;
  note?: string;
}) {
  const { t } = useI18n();
  return (
    <div
      className={`flex flex-col gap-1 rounded-md border p-3 text-[13px] ${
        ok
          ? "border-green-300 bg-green-50/60 text-green-900"
          : "border-rose-300 bg-rose-50/60 text-rose-900"
      }`}
    >
      <p className="font-semibold">{badge ?? (ok ? t.guardrails.approved : t.guardrails.rejected)}</p>
      <p className="text-[12px] opacity-90">{reason}</p>
      {note ? <p className="text-[12px] font-medium opacity-90">{note}</p> : null}
    </div>
  );
}

/* ── Escalation queue ───────────────────────────────────────────────────── */

function EscalationQueue() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const load = useCallback((signal: AbortSignal) => api.escalations(signal), []);
  const { data, error, isInitialLoad, refresh } = useApi(load);

  const resolve = useMutation(api.resolveEscalation);

  const onResolve = useCallback(
    async (id: number) => {
      const result = await resolve.run(id);
      if (result.ok) {
        toast.success(t.guardrails.ticketResolved);
        refresh();
      } else {
        toast.failure(t.guardrails.ticketResolveFailed, describeError(result.error));
      }
    },
    [refresh, resolve, t.guardrails, toast],
  );

  const tickets = data ?? [];
  const open = tickets.filter((ticket) => ticket.status === "OPEN");

  return (
    <Section
      title={t.guardrails.queueTitle}
      desc={t.guardrails.queueDesc}
      aside={
        open.length ? (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[12px] font-medium text-blue-800 ring-1 ring-blue-300 ring-inset">
            {fillTemplate(t.guardrails.openTickets, { count: open.length })}
          </span>
        ) : null
      }
    >
      {isInitialLoad ? (
        <LoadingState rows={3} />
      ) : error && !data ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : tickets.length === 0 ? (
        <p className="text-[13px] text-[var(--muted)]">{t.guardrails.queueEmpty}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border)]">
          {tickets.map((ticket) => (
            <li key={ticket.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <span className="tabular text-[12px] font-medium text-[var(--muted)]">
                {fillTemplate(t.guardrails.ticket, { id: ticket.id })}
              </span>
              <span className="font-mono text-[12px]">{ticket.transaction_id}</span>
              {ticket.rule ? (
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] font-medium text-neutral-700">
                  {humanizeEnum(ticket.rule)}
                </span>
              ) : null}
              <span className="min-w-0 flex-1 text-[12px] text-[var(--muted)]">{ticket.reason}</span>
              <time className="tabular text-[11px] text-[var(--muted)]">
                {formatAbsolute(ticket.created_at, locale)}
              </time>
              {ticket.status === "OPEN" ? (
                <button
                  type="button"
                  onClick={() => onResolve(ticket.id)}
                  disabled={resolve.pending}
                  className="rounded border border-[var(--border)] px-2.5 py-1 text-[12px] font-medium disabled:opacity-60"
                >
                  {resolve.pending ? t.guardrails.resolving : t.guardrails.resolveTicket}
                </button>
              ) : (
                <span className="rounded bg-green-50 px-1.5 py-0.5 text-[11px] font-medium text-green-800 ring-1 ring-green-300 ring-inset">
                  {t.guardrails.ticketResolved}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function clamp(value: number, lo: number, hi: number): number {
  if (!Number.isFinite(value)) return lo;
  return Math.min(hi, Math.max(lo, value));
}
