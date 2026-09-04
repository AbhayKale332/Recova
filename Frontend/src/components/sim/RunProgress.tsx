"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { formatCount } from "@/lib/format";
import type { SimProgress, SimStart, Throughput } from "@/lib/simulation";

/**
 * The scalability readout: how fast the engine is clearing the book, and how
 * many workers are doing it.
 *
 * Every number here is measured, not asserted — rate is cases completed over
 * elapsed wall time, and the percentiles come from per-case timings. The pool is
 * in-process; this is real concurrency, not a distributed system.
 */
export function RunProgress({
  start,
  progress,
  throughput,
  running,
}: {
  start: SimStart;
  progress: SimProgress | null;
  /** Present once the run finishes; its figures supersede the live ones. */
  throughput?: Throughput | null;
  running: boolean;
}) {
  const { t } = useI18n();

  const done = throughput ? start.total : (progress?.done ?? 0);
  const rate = throughput?.cases_per_sec ?? progress?.rate ?? 0;
  const p50 = throughput?.p50_ms ?? progress?.p50_ms ?? 0;
  const p95 = throughput?.p95_ms ?? progress?.p95_ms ?? 0;
  const elapsed = throughput?.elapsed_s ?? progress?.elapsed_s ?? 0;
  const busy = running ? (progress?.workers_busy ?? 0) : 0;
  const pct = start.total ? Math.round((done / start.total) * 100) : 0;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="flex items-center gap-2 text-[13px] font-medium">
          {running ? (
            <span
              aria-hidden
              className="inline-block size-2 animate-pulse rounded-full bg-[var(--accent)]"
            />
          ) : null}
          <span className="tabular">
            {fillTemplate(t.sim.doneOf, {
              done: formatCount(done),
              total: formatCount(start.total),
            })}
          </span>
        </p>

        <dl className="tabular flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-[var(--muted)]">
          <Figure label={t.sim.throughput} value={fillTemplate(t.sim.perSecond, { rate: rate.toFixed(1) })} />
          <Figure
            label={t.sim.latency.split(" ")[0]}
            value={fillTemplate(t.sim.latency, { p50: `${Math.round(p50)}ms`, p95: `${Math.round(p95)}ms` })}
            bare
          />
          <Figure
            label={t.sim.concurrency}
            value={fillTemplate(t.sim.workers, {
              busy: formatCount(busy),
              total: formatCount(start.concurrency),
            })}
          />
          <Figure label="" value={fillTemplate(t.sim.elapsed, { seconds: elapsed.toFixed(1) })} bare />
        </dl>
      </div>

      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t.sim.throughput}
        className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]"
      >
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-150"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Figure({ label, value, bare = false }: { label: string; value: string; bare?: boolean }) {
  if (bare) return <dd>{value}</dd>;
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="sr-only">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
