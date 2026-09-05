"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { humanizeEnum } from "@/lib/format";
import { stoppingRuleText } from "@/lib/status";
import type { LiveDecision } from "@/lib/simulation";

/**
 * The chosen tool and why. When the sandbox refused the model's ask — a
 * different `tool` than `requested_tool`, or the same tool but `allowed:
 * false` — this renders the theatre's central claim: the ask, the sandbox's
 * verbatim refusal, and the handoff that actually happened. Never only the
 * outcome.
 */
export function DecisionCard({ decision }: { decision: LiveDecision | null }) {
  const { t, locale } = useI18n();

  if (!decision) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border)] px-3 py-2.5 text-[12px] text-[var(--muted)]">
        {t.live.decisionEmpty}
      </div>
    );
  }

  const tool = humanizeEnum(decision.tool);
  const requested = decision.requested_tool ? humanizeEnum(decision.requested_tool) : null;
  const refused = requested !== null && (decision.requested_tool !== decision.tool || !decision.allowed);
  const rule = stoppingRuleText(decision.stopping_rule, locale);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <p className="text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
        {t.live.decisionTitle}
      </p>

      {refused ? (
        <div className="flex flex-col gap-1 text-[13px]">
          <p>
            <span className="text-[var(--muted)]">{t.live.askedFor}</span>{" "}
            <span className="font-medium text-[var(--muted)] line-through">{requested}</span>
          </p>
          {decision.sandbox_reason ? (
            <p className="text-[12px] font-medium text-[var(--lost)]">
              {t.live.sandboxRefused}:{" "}
              <span className="font-normal">{decision.sandbox_reason}</span>
            </p>
          ) : null}
          <p>
            <span className="text-[var(--muted)]">{t.live.handedOffTo}</span>{" "}
            <span className="font-semibold text-[var(--accent-ink)]">{tool}</span>
          </p>
        </div>
      ) : (
        <p className="text-[14px] font-semibold">{tool}</p>
      )}

      {decision.model_reason ? (
        <p className="text-[12px] text-[var(--muted)]">{decision.model_reason}</p>
      ) : null}

      {decision.repayment_probability != null ? (
        <RepaymentOdds
          probability={decision.repayment_probability}
          band={decision.repayment_band}
        />
      ) : null}

      {decision.discount_pct != null ? (
        <p className="tabular text-[12px]">
          {fillTemplate(t.live.discountLabel, { pct: decision.discount_pct })}
        </p>
      ) : null}

      {decision.scheduled_for ? (
        <p className="tabular text-[12px]">
          {fillTemplate(t.live.scheduledFor, { when: decision.scheduled_for })}
        </p>
      ) : null}

      {rule ? <p className="text-[12px] font-medium text-[var(--stopped)]">{rule}</p> : null}
    </div>
  );
}

/**
 * The demo repayment model's estimate for this customer. This exact number is
 * put into the DECIDE prompt, so the model reasons over it — the bar shows the
 * operator what the agent saw.
 */
function RepaymentOdds({ probability, band }: { probability: number; band: string | null }) {
  const pct = Math.round(probability * 100);
  const color =
    band === "high"
      ? "var(--recovered, #16a34a)"
      : band === "low"
        ? "var(--lost, #dc2626)"
        : "var(--stopped, #d97706)";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-[11px] text-[var(--muted)]">
        <span className="tracking-wide uppercase">Repayment probability</span>
        <span className="tabular font-semibold text-[var(--accent-ink)]">
          {pct}%{band ? ` · ${band}` : ""}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <p className="text-[11px] text-[var(--muted)]">Demo model · advisory input to the decision</p>
    </div>
  );
}
