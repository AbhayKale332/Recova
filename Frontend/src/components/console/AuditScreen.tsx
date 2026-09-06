"use client";

import { useCallback, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatAbsolute, humanizeEnum } from "@/lib/format";
import { fillTemplate, useI18n } from "@/lib/i18n";
import type { AuditEntry, AuditList } from "@/lib/types";

const PAGE = 100;

/**
 * /console/audit — every row the engine wrote, grouped by the node that wrote
 * it. This is the receipt: the audit trail is written by `record_audit()`
 * calls the engine already made, and this only renders them.
 */
export function AuditScreen() {
  const { t, locale } = useI18n();

  const [txn, setTxn] = useState("");
  const [pending, setPending] = useState("");
  const [limit, setLimit] = useState(PAGE);

  const load = useCallback(
    (signal: AbortSignal) =>
      api.audit({ transaction_id: txn || null, limit, offset: 0 }, signal),
    [txn, limit],
  );
  const { data, error, isInitialLoad, isRefreshing, refresh } = useApi<AuditList>(load);

  const applyFilter = useCallback(() => {
    setLimit(PAGE);
    setTxn(pending.trim());
  }, [pending]);

  const clearFilter = useCallback(() => {
    setPending("");
    setLimit(PAGE);
    setTxn("");
  }, []);

  const groups = useMemo(() => groupByNode(data?.items ?? []), [data]);

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-[17px] font-semibold tracking-tight">{t.audit.title}</h1>
        <p className="mt-0.5 max-w-[68ch] text-[13px] text-[var(--muted)]">{t.audit.subtitle}</p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          applyFilter();
        }}
        className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3"
      >
        <label className="sr-only" htmlFor="audit-filter">
          {t.audit.filterLabel}
        </label>
        <input
          id="audit-filter"
          value={pending}
          onChange={(e) => setPending(e.target.value)}
          placeholder={t.audit.filterPlaceholder}
          className="font-mono min-w-0 flex-1 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-[13px] outline-none"
        />
        <button
          type="submit"
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white"
        >
          {t.audit.apply}
        </button>
        {txn ? (
          <button
            type="button"
            onClick={clearFilter}
            className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[13px] font-medium"
          >
            {t.audit.clear}
          </button>
        ) : null}
      </form>

      {isInitialLoad ? (
        <LoadingState rows={8} />
      ) : error && !data ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={t.audit.empty} body={t.audit.emptyBody} />
      ) : (
        <>
          <p className="text-[12px] text-[var(--muted)]" aria-live="polite">
            {fillTemplate(t.audit.showing, { shown: data.items.length, total: data.total })}
            {isRefreshing ? " · …" : ""}
          </p>

          <div className="flex flex-col gap-4">
            {groups.map((group) => (
              <NodeGroup key={group.node} node={group.node} entries={group.entries} locale={locale} />
            ))}
          </div>

          {data.items.length < data.total ? (
            <div>
              <button
                type="button"
                onClick={() => setLimit((n) => n + PAGE)}
                disabled={isRefreshing}
                className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[13px] font-medium disabled:opacity-60"
              >
                {t.audit.loadMore}
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

interface Group {
  node: string;
  entries: AuditEntry[];
}

/** Groups rows by node, preserving the newest-first order the API returns. */
function groupByNode(items: AuditEntry[]): Group[] {
  const order: string[] = [];
  const map = new Map<string, AuditEntry[]>();
  for (const entry of items) {
    if (!map.has(entry.node_name)) {
      map.set(entry.node_name, []);
      order.push(entry.node_name);
    }
    map.get(entry.node_name)!.push(entry);
  }
  return order.map((node) => ({ node, entries: map.get(node)! }));
}

function NodeGroup({
  node,
  entries,
  locale,
}: {
  node: string;
  entries: AuditEntry[];
  locale: "en" | "hi";
}) {
  const { t } = useI18n();
  return (
    <section className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]">
      <header className="flex items-baseline justify-between gap-3 border-b border-[var(--border)] bg-[var(--bg)] px-4 py-2">
        <h2 className="text-[13px] font-semibold tracking-wide">{humanizeEnum(node)}</h2>
        <span className="tabular text-[11px] text-[var(--muted)]">
          {entries.length === 1
            ? t.audit.oneEntry
            : fillTemplate(t.audit.entries, { count: entries.length })}
        </span>
      </header>
      <ul className="divide-y divide-[var(--border)]">
        {entries.map((entry) => (
          <Row key={entry.id} entry={entry} locale={locale} />
        ))}
      </ul>
    </section>
  );
}

function Row({ entry, locale }: { entry: AuditEntry; locale: "en" | "hi" }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const hasPayload = entry.payload && Object.keys(entry.payload).length > 0;

  return (
    <li className="px-4 py-2.5 text-[12px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <time className="tabular shrink-0 text-[11px] text-[var(--muted)]">
          {formatAbsolute(entry.timestamp, locale)}
        </time>
        <span className="font-medium">{humanizeEnum(entry.action_type)}</span>
        <OutcomeChip outcome={entry.outcome} />
        <span className="font-mono text-[11px] text-[var(--muted)]">{entry.transaction_id}</span>
        {hasPayload ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="ml-auto rounded border border-[var(--border)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--muted)]"
          >
            {open ? "−" : "+"} {t.audit.showPayload}
          </button>
        ) : null}
      </div>
      {open && hasPayload ? (
        <pre className="tabular mt-2 overflow-x-auto rounded-md bg-[var(--bg)] p-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      ) : null}
    </li>
  );
}

const OUTCOME_CLASS: Record<string, string> = {
  SUCCESS: "bg-green-50 text-green-800 ring-green-300",
  FAILURE: "bg-rose-50 text-rose-800 ring-rose-300",
  ESCALATED: "bg-blue-50 text-blue-800 ring-blue-300",
};

function OutcomeChip({ outcome }: { outcome: string }) {
  const cls = OUTCOME_CLASS[outcome] ?? "bg-neutral-100 text-neutral-700 ring-neutral-300";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide ring-1 ring-inset ${cls}`}
    >
      {humanizeEnum(outcome)}
    </span>
  );
}
