"use client";

import type { ReactNode } from "react";

import { describeError } from "@/hooks/useApi";
import { ApiError, NetworkError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/**
 * Loading / Empty / Error — every data surface in the app has all three.
 *
 * The error state names the status and the path; the empty state says what to
 * do about it rather than leaving a blank page.
 */

function Shell({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "error";
  children: ReactNode;
}) {
  const ring = tone === "error" ? "ring-rose-200 bg-rose-50/40" : "ring-[var(--border)] bg-[var(--surface)]";
  return (
    <div
      className={`flex flex-col items-start gap-2 rounded-md px-4 py-6 ring-1 ring-inset ${ring}`}
    >
      {children}
    </div>
  );
}

export function LoadingState({ label, rows = 3 }: { label?: string; rows?: number }) {
  const { t } = useI18n();
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-md bg-[var(--surface)] p-4 ring-1 ring-[var(--border)] ring-inset"
    >
      <span className="sr-only">{label ?? t.states.loadingTitle}</span>
      <div className="flex flex-col gap-2" aria-hidden>
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="h-4 animate-pulse rounded bg-neutral-200"
            style={{ width: `${88 - i * 14}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title?: string;
  body?: string;
  action?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Shell>
      <p className="text-[14px] font-semibold text-[var(--ink)]">{title ?? t.states.emptyTitle}</p>
      <p className="text-[13px] text-[var(--muted)]">{body ?? t.states.emptyBody}</p>
      {action ? <div className="mt-1">{action}</div> : null}
    </Shell>
  );
}

/**
 * Names what failed. A 503 from a specific path reads very differently from an
 * unreachable server, and the operator needs to know which one they have.
 */
export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error: Error;
  onRetry?: () => void;
  title?: string;
}) {
  const { t } = useI18n();
  const isNetwork = error instanceof NetworkError;

  return (
    <Shell tone="error">
      <p className="text-[14px] font-semibold text-[var(--ink)]">
        {title ?? (isNetwork ? t.states.offlineTitle : t.states.errorTitle)}
      </p>
      <p className="text-[13px] text-[var(--muted)]">
        {isNetwork ? t.states.offlineBody : describeError(error)}
      </p>
      {error instanceof ApiError && error.detail ? (
        <p className="font-mono text-[12px] break-all text-[var(--muted)]">{error.detail}</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[13px] font-medium transition-colors duration-150 hover:border-neutral-400"
        >
          {t.actions.retry}
        </button>
      ) : null}
    </Shell>
  );
}
