"use client";

import { formatMoney, formatMoneyCompact, formatMoneyFromPaise } from "@/lib/format";

/**
 * Money renders only through format.ts, always with tabular figures.
 *
 * `amount_inr` is rupees; `max_intervention_amount_minor` is paise. Pass
 * `unit="paise"` for the latter — never convert at a call site.
 */
export function Money({
  value,
  unit = "rupees",
  compact = false,
  className = "",
  title,
}: {
  value: number | null | undefined;
  unit?: "rupees" | "paise";
  /** Hero and summary figures abbreviate Indian-style: ₹4.2L, ₹1.3Cr. */
  compact?: boolean;
  className?: string;
  title?: string;
}) {
  const rupees = value == null ? null : unit === "paise" ? value / 100 : value;
  const text = compact ? formatMoneyCompact(rupees) : formatMoney(rupees);
  // A compact hero still gets the exact figure on hover and for screen readers.
  const exact = unit === "paise" ? formatMoneyFromPaise(value) : formatMoney(rupees);

  return (
    <span className={`tabular ${className}`} title={title ?? (compact ? exact : undefined)}>
      {text}
      {compact && exact !== text ? <span className="sr-only"> ({exact})</span> : null}
    </span>
  );
}
