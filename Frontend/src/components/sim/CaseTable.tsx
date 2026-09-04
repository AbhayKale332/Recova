"use client";

import { ClassChip } from "@/components/ClassChip";
import { Money } from "@/components/Money";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/States";
import { useI18n } from "@/lib/i18n";
import { formatRatio } from "@/lib/format";
import { stoppingRuleText } from "@/lib/status";
import type { SimCase } from "@/lib/simulation";

/**
 * The cases a run produced. Dense by design — this is a work surface, ~32px
 * rows (Vision §6).
 *
 * A row names the rule that stopped it, not just its status: "Stopped" alone
 * loses the whole compliance story, which is the strongest part of the product.
 * Table on desktop, stacked cards on mobile.
 */
export function CaseTable({
  cases,
  selectedId,
  onSelect,
}: {
  cases: SimCase[];
  selectedId: string | null;
  onSelect: (transactionId: string) => void;
}) {
  const { t, locale } = useI18n();

  if (!cases.length) {
    return <EmptyState title={t.states.emptyTitle} body={t.filters.label} />;
  }

  return (
    <>
      {/* Desktop */}
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-[11px] font-medium text-[var(--muted)]">
              <th scope="col" className="py-1.5 pr-3 font-medium">{t.table.customer}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t.table.amount}</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t.table.problem}</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t.table.status}</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t.sim.whyTitle}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t.sim.probabilityTitle}</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((row) => (
              <tr
                key={row.transaction_id}
                onClick={() => onSelect(row.transaction_id)}
                aria-selected={selectedId === row.transaction_id}
                className={`cursor-pointer border-b border-[var(--border)] transition-colors duration-150 ${
                  selectedId === row.transaction_id
                    ? "bg-[var(--accent-wash)]"
                    : "hover:bg-[var(--bg)]"
                }`}
              >
                <td className="py-1.5 pr-3">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(row.transaction_id);
                    }}
                    className="truncate text-left font-medium hover:underline"
                  >
                    {row.customer_name}
                  </button>
                </td>
                <td className="py-1.5 pr-3 text-right">
                  <Money value={row.amount_inr} />
                </td>
                <td className="py-1.5 pr-3">
                  <ClassChip failureClass={row.failure_class} />
                </td>
                <td className="py-1.5 pr-3">
                  <StatusChip status={row.final_state} />
                </td>
                <td className="max-w-[280px] truncate py-1.5 pr-3 text-[12px] text-[var(--muted)]">
                  {stoppingRuleText(row.stopped_by, locale) ?? "—"}
                </td>
                <td className="tabular py-1.5 text-right">{formatRatio(row.p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile */}
      <ul className="flex flex-col gap-2 sm:hidden">
        {cases.map((row) => (
          <li key={row.transaction_id}>
            <button
              type="button"
              onClick={() => onSelect(row.transaction_id)}
              className="flex w-full flex-col gap-1 rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 text-left"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium">{row.customer_name}</span>
                <Money value={row.amount_inr} className="shrink-0" />
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <ClassChip failureClass={row.failure_class} />
                <StatusChip status={row.final_state} />
              </div>
              {row.stopped_by ? (
                <p className="text-[12px] text-[var(--muted)]">
                  {stoppingRuleText(row.stopped_by, locale)}
                </p>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
