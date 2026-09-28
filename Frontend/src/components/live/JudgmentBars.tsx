"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { humanizeEnum } from "@/lib/format";
import type { JevAnswer, JevJudgment } from "@/lib/simulation";

/**
 * The probabilities behind a Jev judgment (backend operations/jev_client.py).
 *
 * Jev answers each question with a probability rather than text, and code
 * owns every threshold, so the useful thing to show is the raw number next to
 * the outcome it produced. A noul row is P(yes); a choice row is the picked
 * option and its share of the distribution. Rows at or above 0.5 are drawn in
 * the accent — that is the default gate before a call site's own threshold.
 */
export function JudgmentBars({ judgment }: { judgment: JevJudgment | null | undefined }) {
  const { t } = useI18n();
  if (!judgment) return null;

  const rows = Object.entries(judgment.answers);
  const shortModel = judgment.model.replace(/^typesafe\//, "").replace(/-\d{8}$/, "");

  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
          {judgment.task ? `${t.live.judgmentTitle} · ${humanizeEnum(judgment.task)}` : t.live.judgmentTitle}
        </p>
        <span className="tabular text-[11px] text-[var(--muted)]" title={judgment.model}>
          {fillTemplate(t.live.judgmentMeta, { model: shortModel, ms: Math.round(judgment.latency_ms) })}
        </span>
      </div>

      {judgment.reason ? <p className="text-[12px] text-[var(--ink)]">{judgment.reason}</p> : null}

      <ul className="flex flex-col gap-1.5">
        {rows.map(([key, answer]) => (
          <Row key={key} name={key} answer={answer} />
        ))}
      </ul>

      {judgment.note ? <p className="text-[11px] text-[var(--muted)] italic">{judgment.note}</p> : null}
    </div>
  );
}

function Row({ name, answer }: { name: string; answer: JevAnswer }) {
  const { p, value } = reading(answer);
  const strong = p >= 0.5;
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5">
      <span className="min-w-0 truncate text-[12px] text-[var(--ink)]">{humanizeEnum(name)}</span>
      <span className="tabular text-[11px] text-[var(--muted)]">{value}</span>
      <div
        className="col-span-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]"
        role="meter"
        aria-label={humanizeEnum(name)}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={p}
      >
        <div
          className={`h-full rounded-full ${strong ? "bg-[var(--accent)]" : "bg-neutral-400"}`}
          style={{ width: `${Math.max(2, Math.round(p * 100))}%` }}
        />
      </div>
    </li>
  );
}

function reading(answer: JevAnswer): { p: number; value: string } {
  if (answer.type === "noul") return { p: answer.p, value: answer.p.toFixed(2) };
  if (answer.type === "choice") {
    const p = answer.probabilities[answer.choice] ?? answer.confidence ?? 0;
    return { p, value: `${humanizeEnum(answer.choice)} · ${p.toFixed(2)}` };
  }
  return { p: answer.confidence ?? 0, value: answer.score.toFixed(2) };
}
