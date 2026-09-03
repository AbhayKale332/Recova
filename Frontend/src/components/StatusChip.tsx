"use client";

import { useI18n } from "@/lib/i18n";
import { STATUS_TONE, TONE_CLASS, statusLabel, statusMeaning } from "@/lib/status";
import type { LifecycleStatus } from "@/lib/types";

/**
 * Status is conveyed by text as well as colour.
 * ESCALATED ("With a human"), CANCELLED ("Stopped") and FAILED ("Lost") read as
 * three different outcomes — never collapse them into "unsuccessful".
 */
export function StatusChip({
  status,
  size = "sm",
  className = "",
}: {
  status: LifecycleStatus;
  size?: "sm" | "md";
  className?: string;
}) {
  const { t } = useI18n();
  const tone = STATUS_TONE[status];
  const pad = size === "md" ? "px-2 py-1 text-[12px]" : "px-1.5 py-0.5 text-[11px]";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-medium whitespace-nowrap ring-1 ring-inset ${TONE_CLASS[tone]} ${pad} ${className}`}
      title={statusMeaning(status, t)}
    >
      {statusLabel(status, t)}
    </span>
  );
}
