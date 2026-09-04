"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { FAILURE_CLASSES, classTitle } from "@/lib/failure-classes";
import { statusLabel } from "@/lib/status";
import { LIFECYCLE_STATUSES, type LifecycleStatus } from "@/lib/types";

/**
 * Filters over the cases a run produced.
 *
 * Applied on the client rather than refetching: the whole run is already in
 * memory from the stream, so a round trip would be slower and would show a
 * different set than the one just watched.
 */
export interface CaseFilterState {
  q: string;
  failureClass: number | null;
  status: LifecycleStatus | null;
}

export const EMPTY_FILTERS: CaseFilterState = { q: "", failureClass: null, status: null };

export function activeFilterCount(filters: CaseFilterState): number {
  return [filters.q.trim(), filters.failureClass, filters.status].filter(Boolean).length;
}

export function CaseFilters({
  filters,
  shown,
  total,
  onChange,
}: {
  filters: CaseFilterState;
  shown: number;
  total: number;
  onChange: (next: CaseFilterState) => void;
}) {
  const { t, locale } = useI18n();
  const active = activeFilterCount(filters);

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex min-w-[180px] flex-1 flex-col gap-1">
        <span className="text-[11px] font-medium text-[var(--muted)]">{t.filters.search}</span>
        <input
          type="search"
          value={filters.q}
          placeholder={t.filters.searchPlaceholder}
          onChange={(event) => onChange({ ...filters, q: event.target.value })}
          className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-[13px]"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-medium text-[var(--muted)]">{t.filters.failureClass}</span>
        <select
          value={filters.failureClass ?? ""}
          onChange={(event) =>
            onChange({
              ...filters,
              failureClass: event.target.value ? Number(event.target.value) : null,
            })
          }
          className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-[13px]"
        >
          <option value="">{t.filters.all}</option>
          {/* The plain problem name, never "Class 4" (Vision Appendix C). */}
          {FAILURE_CLASSES.map((fc) => (
            <option key={fc.id} value={fc.id}>
              {classTitle(fc.id, locale)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-medium text-[var(--muted)]">{t.filters.status}</span>
        <select
          value={filters.status ?? ""}
          onChange={(event) =>
            onChange({
              ...filters,
              status: (event.target.value || null) as LifecycleStatus | null,
            })
          }
          className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-[13px]"
        >
          <option value="">{t.filters.all}</option>
          {LIFECYCLE_STATUSES.map((status) => (
            <option key={status} value={status}>
              {statusLabel(status, t)}
            </option>
          ))}
        </select>
      </label>

      <div className="ml-auto flex items-center gap-3">
        <p className="tabular text-[12px] text-[var(--muted)]">
          {fillTemplate(t.console.caseCount, { shown: String(shown), total: String(total) })}
        </p>
        {active > 0 ? (
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="text-[12px] font-medium text-[var(--accent-ink)] underline-offset-2 hover:underline"
          >
            {t.actions.clearFilters}
          </button>
        ) : null}
      </div>
    </div>
  );
}
