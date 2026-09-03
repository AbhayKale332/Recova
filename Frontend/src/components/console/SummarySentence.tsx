"use client";

import { Fragment } from "react";

import { useI18n } from "@/lib/i18n";
import { summaryParts } from "@/lib/summary";
import type { Metrics } from "@/lib/types";

/**
 * "Recova recovered ₹4.2L of ₹9.8L at risk across 214 cases — 12 escalated to a
 * human, 31 stopped by policy."
 *
 * The whole pitch in one string. Every number comes from /metrics. The numbers
 * are emphasised in place rather than split into separate nodes, so the
 * sentence still reads as one sentence to a screen reader.
 */
export function SummarySentence({ metrics }: { metrics: Metrics | null }) {
  const { t } = useI18n();

  if (!metrics || metrics.funnel.at_risk === 0) {
    return (
      <p className="text-[15px] leading-relaxed text-balance text-[var(--ink)] sm:text-[17px]">
        {t.summary.sentenceNoCases}
      </p>
    );
  }

  const parts = summaryParts(metrics);

  return (
    <p className="text-[15px] leading-relaxed text-balance text-[var(--ink)] sm:text-[17px]">
      {interpolate(t.summary.sentence, parts)}
    </p>
  );
}

/**
 * Fills {placeholders} while wrapping each value in an emphasised span. Falls
 * back to leaving an unknown placeholder untouched rather than dropping it.
 */
function interpolate(template: string, values: Readonly<Record<string, string>>) {
  const segments = template.split(/(\{\w+\})/g);
  return segments.map((segment, index) => {
    const match = /^\{(\w+)\}$/.exec(segment);
    if (!match) return <Fragment key={index}>{segment}</Fragment>;
    const value = values[match[1]];
    if (value === undefined) return <Fragment key={index}>{segment}</Fragment>;
    return (
      <strong key={index} className="tabular font-semibold text-[var(--ink)]">
        {value}
      </strong>
    );
  });
}
