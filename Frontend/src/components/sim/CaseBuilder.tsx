"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ClassChip } from "@/components/ClassChip";
import { Money } from "@/components/Money";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { FAILURE_CLASSES } from "@/lib/failure-classes";
import { Field, NumberInput } from "@/components/sim/FormPrimitives";
import type { CustomCase } from "@/lib/simulation";

export const EMPTY_CASE = (number: number): CustomCase => ({
  customer_name: `Customer ${number}`,
  amount_inr: 5000,
  failure_class: 1,
  reply_text: null,
  reply: null,
  retries_used: 0,
  voice_attempts: 0,
  whatsapp_nudges_used: 0,
  days_overdue: null,
  outcome_event: null,
  playbook: null,
  clock_ist: null,
});

export function CaseBuilder({
  cases,
  onChange,
  disabled,
}: {
  cases: CustomCase[];
  onChange: (cases: CustomCase[]) => void;
  disabled: boolean;
}) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const toast = useToast();
  const [launching, setLaunching] = useState<number | null>(null);

  const update = (index: number, patch: Partial<CustomCase>) => {
    onChange(cases.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  };

  const add = () => onChange([...cases, EMPTY_CASE(cases.length + 1)]);
  const duplicate = (index: number) =>
    onChange([...cases.slice(0, index + 1), { ...cases[index] }, ...cases.slice(index + 1)]);
  const remove = (index: number) => onChange(cases.filter((_, itemIndex) => itemIndex !== index));

  const runLive = async (index: number, item: CustomCase) => {
    setLaunching(index);
    try {
      const { session_id } = await api.createLiveSession({ custom_case: item, locale });
      router.push(`/live?case=${encodeURIComponent(session_id)}`);
    } catch (error) {
      toast.failure(t.sim.runLiveFailed, error instanceof Error ? error.message : String(error));
      setLaunching(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-[var(--muted)]">{t.sim.authoredHint}</p>
        <button
          type="button"
          onClick={add}
          disabled={disabled}
          className="rounded-md border border-[var(--accent)] px-2.5 py-1.5 text-[12px] font-semibold text-[var(--accent-ink)] hover:bg-[var(--accent-wash)] disabled:opacity-50"
        >
          + {t.sim.addCase}
        </button>
      </div>

      {cases.length ? (
        <>
          <div className="hidden overflow-x-auto rounded-md border border-[var(--border)] sm:block">
            <table className="w-full min-w-[1040px] border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--bg)] text-left text-[11px] text-[var(--muted)]">
                  <th className="px-2 py-2 font-medium">{t.sim.customerName}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.amountInr}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.failureClass}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.replyText}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.retriesUsed}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.messagesSent}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.voiceUsed}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.daysOverdue}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.clockTime}</th>
                  <th className="px-2 py-2 font-medium">{t.sim.actions}</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item, index) => (
                  <tr key={index} className="border-b border-[var(--border)] last:border-0">
                    <td className="p-2 align-top">
                      <input
                        value={item.customer_name}
                        maxLength={80}
                        disabled={disabled}
                        onChange={(event) => update(index, { customer_name: event.target.value })}
                        className="w-36 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
                      />
                    </td>
                    <td className="p-2 align-top">
                      <div className="flex flex-col gap-1">
                        <NumberInput
                          value={item.amount_inr}
                          min={1}
                          max={100000000}
                          step={100}
                          suffix="₹"
                          disabled={disabled}
                          onChange={(amount_inr) => update(index, { amount_inr })}
                        />
                        <Money value={item.amount_inr} className="text-[11px] text-[var(--muted)]" />
                      </div>
                    </td>
                    <td className="p-2 align-top">
                      <select
                        value={item.failure_class}
                        disabled={disabled}
                        onChange={(event) => update(index, { failure_class: Number(event.target.value) })}
                        className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
                      >
                        {FAILURE_CLASSES.map((fc) => (
                          <option key={fc.id} value={fc.id}>{fc.copy.en.title}</option>
                        ))}
                      </select>
                    </td>
                    <td className="p-2 align-top">
                      <textarea
                        value={item.reply_text ?? ""}
                        maxLength={280}
                        disabled={disabled}
                        placeholder={t.sim.replyPlaceholder}
                        onChange={(event) => update(index, { reply_text: event.target.value || null })}
                        className="h-16 w-56 resize-y rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
                      />
                    </td>
                    <td className="p-2 align-top"><NumberInput value={item.retries_used} min={0} max={5} disabled={disabled} onChange={(retries_used) => update(index, { retries_used })} /></td>
                    <td className="p-2 align-top"><NumberInput value={item.whatsapp_nudges_used ?? 0} min={0} max={5} disabled={disabled} onChange={(whatsapp_nudges_used) => update(index, { whatsapp_nudges_used })} /></td>
                    <td className="p-2 align-top"><NumberInput value={item.voice_attempts} min={0} max={5} disabled={disabled} onChange={(voice_attempts) => update(index, { voice_attempts })} /></td>
                    <td className="p-2 align-top"><NumberInput value={item.days_overdue ?? 0} min={0} max={365} suffix={t.sim.days} disabled={disabled} onChange={(days_overdue) => update(index, { days_overdue })} /></td>
                    <td className="p-2 align-top">
                      <input
                        type="time"
                        value={item.clock_ist ?? ""}
                        disabled={disabled}
                        title={t.sim.clockTimeHint}
                        onChange={(event) => update(index, { clock_ist: event.target.value || null })}
                        className="w-28 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
                      />
                    </td>
                    <td className="p-2 align-top">
                      <div className="flex gap-1">
                        <button type="button" onClick={() => runLive(index, item)} disabled={disabled || launching !== null} className="rounded border border-[var(--accent)] px-2 py-1 font-semibold text-[var(--accent-ink)] hover:bg-[var(--accent-wash)] disabled:opacity-50">
                          {launching === index ? "…" : t.sim.runLive}
                        </button>
                        <button type="button" onClick={() => duplicate(index)} disabled={disabled} className="rounded border border-[var(--border)] px-2 py-1 hover:border-[var(--accent)] disabled:opacity-50">{t.sim.duplicate}</button>
                        <button type="button" onClick={() => remove(index)} disabled={disabled} className="rounded border border-[var(--border)] px-2 py-1 text-[var(--lost)] hover:border-[var(--lost)] disabled:opacity-50">{t.sim.delete}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 sm:hidden">
            {cases.map((item, index) => (
              <article key={index} className="flex flex-col gap-3 rounded-md border border-[var(--border)] p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <label className="text-[11px] text-[var(--muted)]">{t.sim.customerName}</label>
                    <input value={item.customer_name} maxLength={80} disabled={disabled} onChange={(event) => update(index, { customer_name: event.target.value })} className="mt-1 w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[13px]" />
                  </div>
                  <Money value={item.amount_inr} className="shrink-0 pt-5 font-medium" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Field label={t.sim.amountInr} hint="">
                    <NumberInput value={item.amount_inr} min={1} max={100000000} step={100} suffix="₹" disabled={disabled} onChange={(amount_inr) => update(index, { amount_inr })} />
                  </Field>
                  <Field label={t.sim.failureClass} hint="">
                    <div className="flex items-center gap-2">
                      <select value={item.failure_class} disabled={disabled} onChange={(event) => update(index, { failure_class: Number(event.target.value) })} className="min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[12px]">
                        {FAILURE_CLASSES.map((fc) => <option key={fc.id} value={fc.id}>{fc.copy.en.title}</option>)}
                      </select>
                      <ClassChip failureClass={item.failure_class} />
                    </div>
                  </Field>
                </div>
                <Field label={t.sim.replyText} hint={t.sim.replyHint}>
                  <textarea value={item.reply_text ?? ""} maxLength={280} disabled={disabled} placeholder={t.sim.replyPlaceholder} onChange={(event) => update(index, { reply_text: event.target.value || null })} className="min-h-20 w-full resize-y rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[13px]" />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label={t.sim.retriesUsed} hint=""><NumberInput value={item.retries_used} min={0} max={5} disabled={disabled} onChange={(retries_used) => update(index, { retries_used })} /></Field>
                  <Field label={t.sim.messagesSent} hint=""><NumberInput value={item.whatsapp_nudges_used ?? 0} min={0} max={5} disabled={disabled} onChange={(whatsapp_nudges_used) => update(index, { whatsapp_nudges_used })} /></Field>
                  <Field label={t.sim.voiceUsed} hint=""><NumberInput value={item.voice_attempts} min={0} max={5} disabled={disabled} onChange={(voice_attempts) => update(index, { voice_attempts })} /></Field>
                  <Field label={t.sim.daysOverdue} hint=""><NumberInput value={item.days_overdue ?? 0} min={0} max={365} disabled={disabled} onChange={(days_overdue) => update(index, { days_overdue })} /></Field>
                </div>
                <Field label={t.sim.clockTime} hint={t.sim.clockTimeHint}>
                  <input
                    type="time"
                    value={item.clock_ist ?? ""}
                    disabled={disabled}
                    onChange={(event) => update(index, { clock_ist: event.target.value || null })}
                    className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[13px]"
                  />
                </Field>
                <div className="flex justify-end gap-1">
                  <button type="button" onClick={() => runLive(index, item)} disabled={disabled || launching !== null} className="rounded border border-[var(--accent)] px-2 py-1 text-[12px] font-semibold text-[var(--accent-ink)] hover:bg-[var(--accent-wash)] disabled:opacity-50">
                    {launching === index ? "…" : t.sim.runLive}
                  </button>
                  <button type="button" onClick={() => duplicate(index)} disabled={disabled} className="rounded border border-[var(--border)] px-2 py-1 text-[12px] hover:border-[var(--accent)] disabled:opacity-50">{t.sim.duplicate}</button>
                  <button type="button" onClick={() => remove(index)} disabled={disabled} className="rounded border border-[var(--border)] px-2 py-1 text-[12px] text-[var(--lost)] hover:border-[var(--lost)] disabled:opacity-50">{t.sim.delete}</button>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : (
        <p className="rounded-md border border-dashed border-[var(--border)] px-3 py-4 text-center text-[12px] text-[var(--muted)]">{t.sim.noAuthoredCases}</p>
      )}
    </div>
  );
}
