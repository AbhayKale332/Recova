"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatRelative } from "@/lib/format";
import { stoppingRuleText } from "@/lib/status";
import type { Bounds } from "@/lib/bounds";
import { CHANNELS, type Channel } from "@/lib/types";

/**
 * Attempts used against their cap, channels still available, which rule is
 * armed, and when the agent may act again.
 *
 * Restraint is the feature (Vision §4, pillar 3): any system can send more
 * messages, and this is the one that shows what stopped it. The maths is
 * lib/bounds.ts; this only renders it, so the caps shown are the same constants
 * the engine enforces in compliance_rules.py.
 *
 * Appears in the case panel and inside each streamed run step, which is why it
 * takes a `dense` variant rather than being written twice.
 */
export function BoundsGauge({
  bounds,
  dense = false,
}: {
  bounds: Bounds;
  dense?: boolean;
}) {
  const { t, locale } = useI18n();

  const firedText = stoppingRuleText(bounds.firedRule, locale);
  const armedText = stoppingRuleText(bounds.armedRule, locale);

  return (
    <section className={dense ? "flex flex-col gap-2" : "flex flex-col gap-3"}>
      {dense ? null : (
        <h3 className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
          {t.sim.boundsTitle}
        </h3>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Budget
          label={t.sim.retriesBudget}
          used={bounds.retries.used}
          cap={bounds.retries.cap}
          exhausted={bounds.retries.exhausted}
        />
        <Budget
          label={t.sim.voiceBudget}
          used={bounds.voice.used}
          cap={bounds.voice.cap}
          exhausted={bounds.voice.exhausted}
        />
      </div>

      <div className="flex flex-col gap-1.5 text-[12px]">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[var(--muted)]">{t.sim.channelsRemaining}</span>
          {bounds.channelsRemaining.length === 0 ? (
            <span className="text-[var(--stopped)]">{t.sim.channelsNone}</span>
          ) : (
            CHANNELS.filter((c) => bounds.channelsRemaining.includes(c)).map((channel) => (
              <ChannelPill key={channel} channel={channel} />
            ))
          )}
        </div>

        {/* A rule that already fired is the reason this case is closed; an armed
            rule is what would stop it next. They must never read the same. */}
        {firedText ? (
          <p className="font-medium text-[var(--stopped)]">
            {fillTemplate(t.sim.fired, { rule: firedText })}
          </p>
        ) : armedText ? (
          <p className="text-[var(--inflight)]">
            {fillTemplate(t.sim.armed, { rule: armedText })}
          </p>
        ) : (
          <p className="text-[var(--muted)]">{t.sim.noneArmed}</p>
        )}

        {bounds.nextActionAt ? (
          <p className="tabular text-[var(--muted)]">
            {fillTemplate(t.sim.nextAction, {
              when: formatRelative(bounds.nextActionAt.toISOString(), locale),
            })}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function Budget({
  label,
  used,
  cap,
  exhausted,
}: {
  label: string;
  used: number;
  cap: number;
  exhausted: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2 text-[12px]">
        <span className="text-[var(--muted)]">{label}</span>
        <span
          className={`tabular font-medium ${exhausted ? "text-[var(--stopped)]" : "text-[var(--ink)]"}`}
        >
          {used} / {cap}
        </span>
      </div>
      {/* One pip per permitted attempt: a cap of 3 should be countable at a
          glance, not inferred from a bar's width. */}
      <div className="flex gap-1" aria-hidden>
        {Array.from({ length: cap }, (_, index) => (
          <span
            key={index}
            className={`h-1.5 flex-1 rounded-full ${
              index < used
                ? exhausted
                  ? "bg-[var(--stopped)]"
                  : "bg-[var(--inflight)]"
                : "bg-[var(--border)]"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function ChannelPill({ channel }: { channel: Channel }) {
  return (
    <span className="rounded bg-[var(--accent-wash)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--accent-ink)] ring-1 ring-inset ring-[var(--accent)]/20">
      {channel.replace("_", " ").toLowerCase()}
    </span>
  );
}
