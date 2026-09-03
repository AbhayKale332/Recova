/**
 * The only place money, dates, durations and percentages are formatted.
 * Vision §8. Nothing formats a number inline.
 */

import type { Locale } from "@/lib/i18n/dictionaries/en";

const PAISE_PER_RUPEE = 100;

/** `max_intervention_amount_minor` and friends are paise. `amount_inr` is rupees. */
export function paiseToRupees(paise: number): number {
  return paise / PAISE_PER_RUPEE;
}

export function rupeesToPaise(rupees: number): number {
  return Math.round(rupees * PAISE_PER_RUPEE);
}

const inrExact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** Table and detail figures: ₹4,20,000. Input is **rupees**. */
export function formatMoney(rupees: number | null | undefined): string {
  if (rupees == null || !Number.isFinite(rupees)) return "—";
  return inrExact.format(rupees);
}

/** Table and detail figures from a paise value. */
export function formatMoneyFromPaise(paise: number | null | undefined): string {
  if (paise == null || !Number.isFinite(paise)) return "—";
  return inrExact.format(paiseToRupees(paise));
}

const CRORE = 1e7;
const LAKH = 1e5;

/**
 * Hero and summary-sentence figures, abbreviated Indian-style: ₹4.2L, ₹1.3Cr.
 * Input is **rupees**.
 */
export function formatMoneyCompact(rupees: number | null | undefined): string {
  if (rupees == null || !Number.isFinite(rupees)) return "—";
  const sign = rupees < 0 ? "-" : "";
  const n = Math.abs(rupees);
  if (n >= CRORE) return `${sign}₹${trimZero(n / CRORE)}Cr`;
  if (n >= LAKH) return `${sign}₹${trimZero(n / LAKH)}L`;
  if (n >= 1000) return `${sign}₹${trimZero(n / 1000)}K`;
  return `${sign}₹${Math.round(n)}`;
}

function trimZero(value: number): string {
  const fixed = value.toFixed(1);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed;
}

/** `grrr` and `recovery_rate` are ratios (0–1). One decimal, per Vision §8. */
export function formatRatio(ratio: number | null | undefined): string {
  if (ratio == null || !Number.isFinite(ratio)) return "—";
  return `${(ratio * 100).toFixed(1)}%`;
}

/** A confidence, also a 0–1 ratio, but read as a whole number. */
export function formatConfidence(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return "—";
  return `${Math.round(confidence * 100)}%`;
}

export function formatCount(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN").format(n);
}

/** `avg_time_to_recovery_seconds` / `duration_sec` → "4m 12s", "2h 06m". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes}m ${String(total % 60).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
  return `${Math.floor(hours / 24)}d ${String(hours % 24).padStart(2, "0")}h`;
}

/**
 * The backend serializes UTC timestamps without an offset (SQLite drops the
 * tzinfo), so `new Date("2026-09-03T18:02:30.107346")` would be read as *local*
 * time and land hours off. Treat a bare timestamp as UTC. Date-only strings
 * ("2026-09-06") are left alone — they are calendar dates, not instants.
 */
export function parseApiDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const date = new Date(hasZone || dateOnly ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** Feeds: "6 min ago". */
export function formatRelative(iso: string | null | undefined, locale: Locale = "en"): string {
  const date = parseApiDate(iso);
  if (!date) return "—";
  const rtf = new Intl.RelativeTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    numeric: "auto",
    style: "short",
  });
  const elapsed = (date.getTime() - Date.now()) / 1000;
  for (const [unit, seconds] of RELATIVE_UNITS) {
    if (Math.abs(elapsed) >= seconds) {
      return rtf.format(Math.round(elapsed / seconds), unit);
    }
  }
  return rtf.format(Math.round(elapsed), "second");
}

/** Audit trail: absolute, with the timezone named. */
export function formatAbsolute(iso: string | null | undefined, locale: Locale = "en"): string {
  const date = parseApiDate(iso);
  if (!date) return "—";
  // Explicit components, not dateStyle/timeStyle: Intl throws if `timeZoneName`
  // is combined with either of those, and the audit trail must name the zone.
  return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Kolkata",
    timeZoneName: "short",
  }).format(date);
}

/** Audit trail rows, where the date is a column header and the time is the row. */
export function formatClock(iso: string | null | undefined, locale: Locale = "en"): string {
  const date = parseApiDate(iso);
  if (!date) return "—";
  return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(date);
}

/** Calendar dates from the trackers ("2026-09-06"). */
export function formatDate(iso: string | null | undefined, locale: Locale = "en"): string {
  const date = parseApiDate(iso);
  if (!date) return "—";
  return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    dateStyle: "medium",
    timeZone: /^\d{4}-\d{2}-\d{2}$/.test(iso!) ? "UTC" : "Asia/Kolkata",
  }).format(date);
}

/** SCREAMING_SNAKE enum → "Screaming snake", for playbooks and actions. */
export function humanizeEnum(value: string | null | undefined): string {
  if (!value) return "—";
  const words = value.toLowerCase().split("_");
  return words.map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(" ");
}

/** A customer or buyer name that the backend may not have. */
export function displayName(name: string | null | undefined): string {
  return name?.trim() || "Unknown customer";
}
