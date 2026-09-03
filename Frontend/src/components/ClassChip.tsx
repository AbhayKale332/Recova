"use client";

import { CLASS_ACCENT_CLASS, CLASS_ACCENT_DOT, failureClass } from "@/lib/failure-classes";
import { useI18n } from "@/lib/i18n";

/**
 * The plain problem name ("Overdue Invoices"), not "Class 4" — Appendix C.
 * The class number stays available as the chip's tooltip for anyone matching
 * this against the backend's `failure_class`.
 */
export function ClassChip({
  failureClass: id,
  className = "",
}: {
  failureClass: number | null | undefined;
  className?: string;
}) {
  const { locale } = useI18n();
  const fc = failureClass(id);
  if (!fc) {
    return <span className={`text-[var(--muted)] ${className}`}>—</span>;
  }
  const copy = fc.copy[locale];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset ${CLASS_ACCENT_CLASS[fc.accent]} ${className}`}
      title={`${copy.tag} — ${copy.problem}`}
    >
      <span className={`size-1.5 rounded-full ${CLASS_ACCENT_DOT[fc.accent]}`} aria-hidden />
      {copy.title}
    </span>
  );
}
