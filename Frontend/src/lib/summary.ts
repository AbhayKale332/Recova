/**
 * The batch summary sentence (Vision §4, pillar 2):
 *
 *   "Recova recovered ₹4.2L of ₹9.8L at risk across 214 cases —
 *    12 escalated to a human, 31 stopped by policy."
 *
 * If a judge reads only this sentence, they have received the whole submission.
 * Every number comes from /metrics; nothing here is hardcoded.
 */

import { fillTemplate } from "@/lib/i18n";
import { formatCount, formatMoneyCompact } from "@/lib/format";
import type { Dictionary } from "@/lib/i18n/dictionaries/en";
import type { Metrics } from "@/lib/types";

export interface SummaryParts extends Record<string, string> {
  recovered: string;
  atRisk: string;
  cases: string;
  escalated: string;
  stopped: string;
}

export function summaryParts(metrics: Metrics): SummaryParts {
  return {
    recovered: formatMoneyCompact(metrics.recovered_inr),
    atRisk: formatMoneyCompact(metrics.at_risk_inr),
    cases: formatCount(metrics.funnel.at_risk),
    escalated: formatCount(metrics.funnel.escalated),
    stopped: formatCount(metrics.funnel.cancelled),
  };
}

export function summarySentence(metrics: Metrics | null, t: Dictionary): string {
  if (!metrics || metrics.funnel.at_risk === 0) return t.summary.sentenceNoCases;
  return fillTemplate(t.summary.sentence, { ...summaryParts(metrics) });
}
