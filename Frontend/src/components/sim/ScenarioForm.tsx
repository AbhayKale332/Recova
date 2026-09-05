"use client";

import { useState } from "react";

import { ClassChip } from "@/components/ClassChip";
import { CaseBuilder, EMPTY_CASE } from "@/components/sim/CaseBuilder";
import { SampleGallery } from "@/components/sim/SampleGallery";
import { Field, Group, NumberInput } from "@/components/sim/FormPrimitives";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatCount } from "@/lib/format";
import { FAILURE_CLASSES } from "@/lib/failure-classes";
import {
  REPLY_KINDS,
  armsQuietHours,
  scenarioHour,
  withScenarioHour,
  type ReplyKind,
  type Scenario,
  type SavedScenario,
  encodeScenario,
} from "@/lib/simulation";

/**
 * The scenario inputs.
 *
 * Three collapsed groups so the first screen stays calm — a judge should see one
 * row of samples and a Run button, not a form. Every preset fills the fields
 * visibly rather than running something opaque, so what is being asked is on
 * screen before it runs.
 */
export function ScenarioForm({
  scenario,
  onChange,
  savedScenarios = [],
  onSavedScenario,
  onSaveScenario,
  onDeleteScenario,
  disabled,
}: {
  scenario: Scenario;
  onChange: (next: Scenario) => void;
  savedScenarios?: SavedScenario[];
  onSavedScenario?: (saved: SavedScenario) => void;
  onSaveScenario?: () => void;
  onDeleteScenario?: (slug: string) => void;
  disabled: boolean;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const setCases = (patch: Partial<Scenario["cases"]>) =>
    onChange({ ...scenario, cases: { ...scenario.cases, ...patch } });
  const setEdges = (patch: Partial<Scenario["edge_cases"]>) =>
    onChange({ ...scenario, edge_cases: { ...scenario.edge_cases, ...patch } });
  const setPolicy = (patch: Partial<Scenario["policy"]>) =>
    onChange({ ...scenario, policy: { ...scenario.policy, ...patch } });
  const setCustomCases = (custom_cases: Scenario["custom_cases"]) =>
    onChange({ ...scenario, custom_cases });

  const copyShareLink = async () => {
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("s", encodeScenario(scenario));
    await navigator.clipboard.writeText(url.toString());
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const hour = scenarioHour(scenario);

  return (
    <div className="flex flex-col gap-4">
      <SampleGallery
        onPick={(built) => setCustomCases([...scenario.custom_cases, built])}
        onCustom={() => setCustomCases([...scenario.custom_cases, EMPTY_CASE(scenario.custom_cases.length + 1)])}
        disabled={disabled}
      />

      <Group title={t.sim.groupCustom} defaultOpen>
        <CaseBuilder cases={scenario.custom_cases} onChange={setCustomCases} disabled={disabled} />

        <Field label={t.sim.amountBounds} hint={t.sim.amountBoundsHint}>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-[12px]">
              <input
                type="checkbox"
                checked={scenario.cases.amount_min_inr !== null}
                disabled={disabled}
                onChange={(event) => setCases({ amount_min_inr: event.target.checked ? 1000 : null })}
              />
              {t.sim.amountMin}
            </label>
            {scenario.cases.amount_min_inr !== null ? (
              <NumberInput value={scenario.cases.amount_min_inr} min={1} max={100000000} step={100} suffix="₹" disabled={disabled} onChange={(amount_min_inr) => setCases({ amount_min_inr })} />
            ) : null}
            <label className="flex items-center gap-1.5 text-[12px]">
              <input
                type="checkbox"
                checked={scenario.cases.amount_max_inr !== null}
                disabled={disabled}
                onChange={(event) => setCases({ amount_max_inr: event.target.checked ? 100000 : null })}
              />
              {t.sim.amountMax}
            </label>
            {scenario.cases.amount_max_inr !== null ? (
              <NumberInput value={scenario.cases.amount_max_inr} min={1} max={100000000} step={100} suffix="₹" disabled={disabled} onChange={(amount_max_inr) => setCases({ amount_max_inr })} />
            ) : null}
          </div>
        </Field>

        <label className="flex items-start gap-2 rounded-md bg-[var(--accent-wash)] px-3 py-2 text-[12px]">
          <input
            type="checkbox"
            checked={scenario.live_diagnosis}
            disabled={disabled}
            onChange={(event) => onChange({ ...scenario, live_diagnosis: event.target.checked })}
            className="mt-0.5"
          />
          <span>
            <span className="block font-medium">{t.sim.liveDiagnosis}</span>
            <span className="block text-[11px] text-[var(--muted)]">{t.sim.liveDiagnosisHint}</span>
          </span>
        </label>

        <div className="flex flex-col gap-2 border-t border-[var(--border)] pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={onSaveScenario} disabled={disabled || !onSaveScenario} className="rounded-md bg-[var(--accent)] px-2.5 py-1.5 text-[12px] font-semibold text-white disabled:opacity-50">
              {t.sim.saveScenario}
            </button>
            <button type="button" onClick={copyShareLink} disabled={disabled} className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[12px] font-medium disabled:opacity-50">
              {copied ? t.sim.linkCopied : t.sim.copyLink}
            </button>
            <span className="text-[11px] text-[var(--muted)]">{t.sim.shareHint}</span>
          </div>
          {savedScenarios.length ? (
            <div className="flex flex-wrap items-center gap-2">
              <select
                defaultValue=""
                disabled={disabled}
                onChange={(event) => {
                  const saved = savedScenarios.find((item) => item.slug === event.target.value);
                  if (saved) onSavedScenario?.(saved);
                  event.target.value = "";
                }}
                className="min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[12px]"
              >
                <option value="">{t.sim.savedScenarios}</option>
                {savedScenarios.map((saved) => <option key={saved.slug} value={saved.slug}>{saved.name}</option>)}
              </select>
              {savedScenarios.map((saved) => (
                <button key={saved.slug} type="button" onClick={() => onDeleteScenario?.(saved.slug)} disabled={disabled} aria-label={`${t.sim.delete} ${saved.name}`} className="rounded border border-[var(--border)] px-2 py-1 text-[11px] text-[var(--lost)] disabled:opacity-50">× {saved.name}</button>
              ))}
            </div>
          ) : null}
        </div>
      </Group>

      <Group title={t.sim.groupPolicy} defaultOpen>
        <Field label={t.sim.maxDiscount} hint={t.sim.maxDiscountHint}>
          <div className="flex items-center gap-2">
            <NumberInput
              value={scenario.policy.max_discount_pct ?? 0}
              min={0}
              max={100}
              suffix="%"
              disabled={disabled || scenario.policy.max_discount_pct === null}
              onChange={(max_discount_pct) => setPolicy({ max_discount_pct })}
            />
            <label className="flex shrink-0 items-center gap-1.5 text-[12px] text-[var(--muted)]">
              <input
                type="checkbox"
                checked={scenario.policy.max_discount_pct === null}
                disabled={disabled}
                onChange={(event) =>
                  setPolicy({ max_discount_pct: event.target.checked ? null : 0 })
                }
              />
              {t.sim.policyDefault}
            </label>
          </div>
        </Field>

        <Field label={t.sim.allowedChannels} hint="">
          <div className="flex flex-wrap gap-2">
            {(["WHATSAPP", "VOICE", "PAYMENT_LINK"] as const).map((channel) => {
              const current = scenario.policy.allowed_channels;
              const on = current === null || current.includes(channel);
              return (
                <label key={channel} className="flex items-center gap-1.5 text-[12px]">
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={disabled}
                    onChange={() => {
                      const base = current ?? ["WHATSAPP", "VOICE", "PAYMENT_LINK"];
                      const next = on
                        ? base.filter((c) => c !== channel)
                        : [...base, channel];
                      setPolicy({ allowed_channels: next });
                    }}
                  />
                  {channel.replace("_", " ").toLowerCase()}
                </label>
              );
            })}
          </div>
        </Field>

        <Field label={t.sim.allowPartialPayment} hint={t.sim.allowPartialPaymentHint}>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-[12px]">
              <input
                type="checkbox"
                checked={scenario.policy.allow_partial_payment !== false}
                disabled={disabled}
                onChange={(event) =>
                  setPolicy({ allow_partial_payment: event.target.checked ? null : false })
                }
              />
              {scenario.policy.allow_partial_payment !== false ? t.sim.policyDefault + " (Yes)" : "No"}
            </label>
          </div>
        </Field>

        <Field label={t.sim.minPartialPaymentPct} hint={t.sim.minPartialPaymentPctHint}>
          <div className="flex items-center gap-2">
            <NumberInput
              value={scenario.policy.min_partial_payment_pct ?? 50}
              min={1}
              max={100}
              suffix="%"
              disabled={disabled || scenario.policy.min_partial_payment_pct === null}
              onChange={(min_partial_payment_pct) => setPolicy({ min_partial_payment_pct })}
            />
            <label className="flex shrink-0 items-center gap-1.5 text-[12px] text-[var(--muted)]">
              <input
                type="checkbox"
                checked={scenario.policy.min_partial_payment_pct === null}
                disabled={disabled}
                onChange={(event) =>
                  setPolicy({ min_partial_payment_pct: event.target.checked ? null : 50 })
                }
              />
              {t.sim.policyDefault}
            </label>
          </div>
        </Field>
      </Group>

      <Group title={t.sim.groupCases}>
        <Field label={t.sim.scenarioName} hint="">
          <input
            value={scenario.name}
            maxLength={80}
            disabled={disabled}
            onChange={(event) => onChange({ ...scenario, name: event.target.value })}
            className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[13px]"
          />
        </Field>
        <Field label={t.sim.scenarioDescription} hint="">
          <textarea
            value={scenario.description}
            maxLength={240}
            disabled={disabled}
            onChange={(event) => onChange({ ...scenario, description: event.target.value })}
            className="min-h-14 w-full resize-y rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[13px]"
          />
        </Field>
        <Field label={t.sim.count} hint={t.sim.countHint}>
          <NumberInput
            value={scenario.cases.count}
            min={0}
            max={500}
            disabled={disabled}
            onChange={(count) => setCases({ count })}
          />
        </Field>

        <Field label={t.sim.classMix} hint={t.sim.classMixHint}>
          <div className="flex flex-col gap-1.5">
            {FAILURE_CLASSES.map((fc) => (
              <div key={fc.id} className="flex items-center gap-2">
                <span className="min-w-0 flex-1">
                  <ClassChip failureClass={fc.id} />
                </span>
                <NumberInput
                  value={scenario.cases.class_mix[String(fc.id)] ?? 0}
                  min={0}
                  max={10}
                  disabled={disabled}
                  onChange={(weight) =>
                    setCases({
                      class_mix: { ...scenario.cases.class_mix, [String(fc.id)]: weight },
                    })
                  }
                />
              </div>
            ))}
          </div>
        </Field>

        <Field label={t.sim.amountScale} hint={t.sim.amountScaleHint}>
          <NumberInput
            value={scenario.cases.amount_scale}
            min={0.1}
            max={20}
            step={0.1}
            disabled={disabled}
            onChange={(amount_scale) => setCases({ amount_scale })}
          />
        </Field>
      </Group>

      <Group title={t.sim.groupEdges}>
        <Field label={t.sim.replyMix} hint={t.sim.replyMixHint}>
          <div className="flex flex-col gap-1.5">
            {REPLY_KINDS.map((kind) => (
              <div key={kind} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[12px]">{replyLabel(kind, t)}</span>
                <NumberInput
                  value={scenario.edge_cases.reply_mix[kind] ?? 0}
                  min={0}
                  max={10}
                  disabled={disabled}
                  onChange={(weight) =>
                    setEdges({
                      reply_mix: { ...scenario.edge_cases.reply_mix, [kind]: weight },
                    })
                  }
                />
              </div>
            ))}
          </div>
        </Field>

        <Field label={t.sim.clock} hint={t.sim.clockHint}>
          <div className="flex flex-col gap-1.5">
            <select
              value={hour ?? ""}
              disabled={disabled}
              onChange={(event) =>
                setEdges({
                  clock_ist: event.target.value
                    ? withScenarioHour(scenario, Number(event.target.value))
                    : null,
                })
              }
              className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-[13px]"
            >
              <option value="">{t.sim.clockNow}</option>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00 IST
                </option>
              ))}
            </select>
            {/* Naming the consequence before the run is what turns a time picker
                into a demonstration of the rule. */}
            {armsQuietHours(scenario) ? (
              <p className="text-[11px] font-medium text-[var(--inflight)]">{t.sim.quietArmed}</p>
            ) : null}
          </div>
        </Field>

        <Field label={t.sim.retriesUsed} hint={t.sim.retriesHint}>
          <NumberInput
            value={scenario.edge_cases.retries_already_used}
            min={0}
            max={5}
            disabled={disabled}
            onChange={(retries_already_used) => setEdges({ retries_already_used })}
          />
        </Field>

        <Field label={t.sim.voiceUsed} hint={t.sim.voiceHint}>
          <NumberInput
            value={scenario.edge_cases.voice_attempts_used}
            min={0}
            max={5}
            disabled={disabled}
            onChange={(voice_attempts_used) => setEdges({ voice_attempts_used })}
          />
        </Field>

        <Field label={t.sim.lateSettlement} hint={t.sim.lateSettlementHint}>
          <NumberInput
            value={scenario.edge_cases.late_settlement_pct}
            min={0}
            max={100}
            suffix="%"
            disabled={disabled}
            onChange={(late_settlement_pct) => setEdges({ late_settlement_pct })}
          />
        </Field>

        <Field label={t.sim.crossDevice} hint={t.sim.crossDeviceHint}>
          <NumberInput
            value={scenario.edge_cases.cross_device_pct}
            min={0}
            max={100}
            suffix="%"
            disabled={disabled}
            onChange={(cross_device_pct) => setEdges({ cross_device_pct })}
          />
        </Field>

        <Field label={t.sim.daysOverdue} hint="">
          <NumberInput
            value={scenario.edge_cases.days_overdue}
            min={0}
            max={365}
            suffix={t.sim.days}
            disabled={disabled}
            onChange={(days_overdue) => setEdges({ days_overdue })}
          />
        </Field>
      </Group>

      <p className="tabular text-[12px] text-[var(--muted)]">
        {fillTemplate(t.console.caseCount, {
          shown: formatCount(scenario.cases.count + scenario.custom_cases.length),
          total: formatCount(scenario.cases.count + scenario.custom_cases.length),
        })}
      </p>
    </div>
  );
}

function replyLabel(kind: ReplyKind, t: ReturnType<typeof useI18n>["t"]): string {
  switch (kind) {
    case "cooperative":
      return t.sim.reply_cooperative;
    case "opt_out":
      return t.sim.reply_opt_out;
    case "dispute":
      return t.sim.reply_dispute;
    case "p2p":
      return t.sim.reply_p2p;
    case "silent":
      return t.sim.reply_silent;
  }
}
