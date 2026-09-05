"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import { humanizeEnum } from "@/lib/format";
import type { RouteDecision } from "@/lib/simulation";

/**
 * The live route decision: task → provider · model, and the reason sentence.
 * Re-rendered on every `route`/`decision` event, so it visibly changes
 * between steps — that change is most of what makes the router legible.
 *
 * A seeded opening (`provider === "deterministic"`) never claims a model was
 * called: the backend never emits a `route` event for it (see the
 * `_opening()` fix in live_session.py), and the value shown here for that
 * turn comes only from `decision.route_decision`, whose own `reason` says so.
 * That state renders in a visibly different, muted, dashed style so a
 * planned/seeded step can never be mistaken for a taken provider call.
 */
export function RouterChip({ route }: { route: RouteDecision | null }) {
  const { t } = useI18n();

  if (!route) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border)] px-3 py-2.5 text-[12px] text-[var(--muted)]">
        {t.live.connecting}
      </div>
    );
  }

  const seeded = route.provider === "deterministic";
  const raisers = route.raised_by
    .map((raiser) =>
      raiser === "stakes"
        ? t.live.raise_stakes
        : raiser === "guardrail_proximity"
          ? t.live.raise_guardrail_proximity
          : raiser,
    )
    .join(", ");

  return (
    <div
      className={`flex flex-col gap-1.5 rounded-md border px-3 py-2.5 ${
        seeded
          ? "border-dashed border-[var(--border)] bg-[var(--bg)]"
          : "border-[var(--accent)]/30 bg-[var(--accent-wash)]"
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
          {t.live.routeTitle}
        </p>
        {seeded ? (
          <span className="text-[11px] font-medium text-[var(--muted)]">{t.live.routeSeeded}</span>
        ) : null}
      </div>

      <p className="tabular text-[13px] font-semibold">
        {humanizeEnum(route.task)}
        {" → "}
        {seeded ? "—" : `${route.provider} · ${route.model}`}
      </p>

      <p className="text-[12px] text-[var(--muted)]">
        {seeded ? t.live.routeSeededHint : route.reason}
      </p>

      {!seeded && (raisers || route.escalated_from) ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--muted)]">
          {raisers ? <span>{fillTemplate(t.live.raisedBy, { reasons: raisers })}</span> : null}
          {route.escalated_from ? (
            <span>{fillTemplate(t.live.escalatedFrom, { tier: route.escalated_from })}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
