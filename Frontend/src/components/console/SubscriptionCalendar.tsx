"use client";

import { useCallback, useMemo, useState } from "react";

import { Money } from "@/components/Money";
import { Sheet } from "@/components/Sheet";
import { api } from "@/lib/api";
import type { SubscriptionItem } from "@/lib/types";
import { formatDate, humanizeEnum } from "@/lib/format";
import { useApi, useMutation } from "@/hooks/useApi";
import { useI18n } from "@/lib/i18n";

import CalendarGrid, { type CalEvent, type EventCategory } from "./CalendarGrid";

function category(status: string): EventCategory {
  if (status === "recovered") return "paid";
  if (["retrying", "deferred", "intervening", "escalated"].includes(status)) return "sent";
  return "pending";
}

export function SubscriptionCalendar() {
  const { t } = useI18n();
  const c = t.calendar;

  const load = useCallback((signal: AbortSignal) => api.subscriptions(signal), []);
  const { data, refresh } = useApi(load);
  const subscriptions = useMemo(() => data ?? [], [data]);

  const { run: createSubscription, pending } = useMutation(api.createSubscription);

  const [adding, setAdding] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState({ customer: "", plan: "", amount: "", next: "", salary: "1" });

  const events: CalEvent[] = useMemo(
    () =>
      subscriptions.map((s: SubscriptionItem) => ({
        id: s.transaction_id,
        date: s.next_debit_date,
        label: s.customer_name,
        amount: s.amount_inr,
        category: category(s.mandate_status),
      })),
    [subscriptions],
  );

  const selected = useMemo(
    () => subscriptions.find((s) => s.transaction_id === selectedId) ?? null,
    [subscriptions, selectedId],
  );

  const save = async () => {
    if (!form.customer.trim() || !form.plan.trim() || !form.amount || !form.next) return;
    const result = await createSubscription({
      customer_name: form.customer.trim(),
      plan: form.plan.trim(),
      amount_inr: Number(form.amount),
      next_debit_date: form.next,
      salary_day: Number(form.salary) || 1,
    });
    if (result.ok) {
      setForm({ customer: "", plan: "", amount: "", next: "", salary: "1" });
      setAdding(false);
      refresh();
    }
  };

  const input = "border-[var(--border)] bg-[var(--bg)] text-[var(--ink)]";

  return (
    <section
      aria-labelledby="subscriptions-heading"
      className="flex flex-col gap-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5"
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0">
          <h2 id="subscriptions-heading" className="text-[15px] font-semibold tracking-tight">
            {c.title}
          </h2>
          <p className="mt-0.5 text-[13px] text-[var(--muted)]">{c.desc}</p>
        </div>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="ml-auto shrink-0 rounded-md bg-[var(--escalated)] px-3 py-1.5 text-[13px] font-semibold text-white transition-opacity duration-150 hover:opacity-90"
        >
          {c.add}
        </button>
      </div>

      {adding ? (
        <div className="grid gap-2 rounded-lg border border-[var(--border)] p-3 sm:grid-cols-6">
          <input
            placeholder={c.customer}
            value={form.customer}
            onChange={(e) => setForm({ ...form, customer: e.target.value })}
            className={`rounded-md border px-2.5 py-1.5 text-[12.5px] outline-none sm:col-span-2 ${input}`}
          />
          <input
            placeholder={c.plan}
            value={form.plan}
            onChange={(e) => setForm({ ...form, plan: e.target.value })}
            className={`rounded-md border px-2.5 py-1.5 text-[12.5px] outline-none ${input}`}
          />
          <input
            type="number"
            placeholder={c.amount}
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            className={`tabular rounded-md border px-2.5 py-1.5 text-[12.5px] outline-none ${input}`}
          />
          <input
            type="date"
            aria-label={c.nextDebit}
            value={form.next}
            onChange={(e) => setForm({ ...form, next: e.target.value })}
            className={`tabular rounded-md border px-2 py-1.5 text-[12px] outline-none ${input}`}
          />
          <input
            type="number"
            min={1}
            max={31}
            aria-label={c.salaryDay}
            value={form.salary}
            onChange={(e) => setForm({ ...form, salary: e.target.value })}
            className={`tabular rounded-md border px-2.5 py-1.5 text-[12.5px] outline-none ${input}`}
          />
          <div className="flex gap-2 sm:col-span-6">
            <button
              type="button"
              onClick={save}
              disabled={pending}
              className="rounded-md bg-[var(--escalated)] px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-50"
            >
              {pending ? c.saving : c.save}
            </button>
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[12px] font-medium text-[var(--muted)]"
            >
              {t.actions.cancel}
            </button>
          </div>
        </div>
      ) : null}

      <CalendarGrid events={events} onEventClick={setSelectedId} />

      <Sheet
        open={selected !== null}
        onClose={() => setSelectedId(null)}
        title={selected?.customer_name ?? ""}
        subtitle={selected?.plan}
      >
        {selected ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-4 text-[13px]">
            <dt className="text-[var(--muted)]">{c.amount}</dt>
            <dd className="text-right font-medium">
              <Money value={selected.amount_inr} />
            </dd>
            <dt className="text-[var(--muted)]">{c.nextDebit}</dt>
            <dd className="text-right font-medium">{formatDate(selected.next_debit_date)}</dd>
            <dt className="text-[var(--muted)]">{c.mandateStatus}</dt>
            <dd className="text-right font-medium">{humanizeEnum(selected.mandate_status)}</dd>
            <dt className="text-[var(--muted)]">{c.retries}</dt>
            <dd className="text-right font-medium">
              {selected.retry_count} / {selected.retry_cap}
            </dd>
            <dt className="text-[var(--muted)]">{c.salaryDay}</dt>
            <dd className="text-right font-medium">{selected.salary_day}</dd>
          </dl>
        ) : null}
      </Sheet>
    </section>
  );
}
