"use client";

import { useCallback, useMemo } from "react";

import { ClassChip } from "@/components/ClassChip";
import { Money } from "@/components/Money";
import { Sheet } from "@/components/Sheet";
import { StatusChip } from "@/components/StatusChip";
import { ErrorState, LoadingState } from "@/components/States";
import { BoundsGauge } from "@/components/sim/BoundsGauge";
import { DecisionTrace } from "@/components/sim/DecisionTrace";
import { ProbabilityBreakdown } from "@/components/sim/ProbabilityBreakdown";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { computeBounds } from "@/lib/bounds";
import { formatConfidence, humanizeEnum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { RouteDecision, SimCase, TraceStep } from "@/lib/simulation";
import type { PolicyResponse, TransactionDetail } from "@/lib/types";

/**
 * One case, in the order that answers *what and why* first (Vision §12):
 * payment facts → diagnosis → bounds gauge → why → likelihood → audit trail.
 *
 * The summary row comes from the stream, but the audit trail is fetched: the
 * per-case stream event stays small so 200 of them do not carry 200 traces the
 * viewer will never open.
 */
export function CasePanel({
  simCase,
  policy,
  onClose,
}: {
  simCase: SimCase | null;
  policy: PolicyResponse | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const id = simCase?.transaction_id ?? null;

  const fetchDetail = useCallback(
    (signal: AbortSignal) => (id ? api.transaction(id, signal) : Promise.resolve(null)),
    [id],
  );
  const detail = useApi<TransactionDetail | null>(fetchDetail);

  const fetchRoute = useCallback(
    (signal: AbortSignal) =>
      simCase
        ? api.explainRoute(
            {
              task: "DIAGNOSE",
              amount_inr: simCase.amount_inr,
            },
            signal,
          )
        : Promise.resolve(null),
    [simCase],
  );
  const route = useApi<RouteDecision | null>(fetchRoute);

  const bounds = useMemo(() => {
    if (!detail.data) return null;
    return computeBounds({
      status: detail.data.status,
      auditTrail: detail.data.audit_trail,
      stoppingRule: detail.data.stopping_rule,
      allowedChannels: policy?.policy.allowed_channels ?? [],
      failureClass: detail.data.failure_class,
    });
  }, [detail.data, policy]);

  const steps = useMemo<TraceStep[]>(
    () => (detail.data ? buildSteps(detail.data) : []),
    [detail.data],
  );

  return (
    <Sheet
      open={simCase !== null}
      onClose={onClose}
      title={simCase?.customer_name ?? ""}
      subtitle={
        simCase ? (
          <span className="tabular text-[12px] text-[var(--muted)]">{simCase.transaction_id}</span>
        ) : null
      }
      side="right"
    >
      {simCase ? (
        <div className="flex flex-col gap-5">
          <section className="flex flex-wrap items-center gap-2">
            <Money
              value={simCase.amount_inr}
              className="text-[24px] font-semibold tracking-tight"
            />
            <ClassChip failureClass={simCase.failure_class} />
            <StatusChip status={simCase.final_state} size="md" />
          </section>

          {detail.error ? (
            <ErrorState error={detail.error} onRetry={detail.refresh} />
          ) : detail.isInitialLoad ? (
            <LoadingState rows={4} />
          ) : (
            <>
              {detail.data?.diagnosis?.root_cause ? (
                <section className="flex flex-col gap-1">
                  <h3 className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
                    {t.table.problem}
                  </h3>
                  <p className="text-[13px] font-medium">
                    {humanizeEnum(detail.data.diagnosis.root_cause)}
                  </p>
                  <p className="text-[12px] text-[var(--muted)]">
                    {humanizeEnum(detail.data.diagnosis.recommended_playbook ?? "")}
                    {detail.data.diagnosis.confidence
                      ? ` · ${formatConfidence(detail.data.diagnosis.confidence)}`
                      : ""}
                  </p>
                </section>
              ) : null}

              {bounds ? <BoundsGauge bounds={bounds} /> : null}

              <section className="flex flex-col gap-2">
                <h3 className="text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
                  {t.sim.whyTitle}
                </h3>
                <DecisionTrace steps={steps} />
              </section>
            </>
          )}

          {route.data ? (
            <section
              className="flex items-center justify-between gap-3 rounded-md border border-[var(--border)] bg-[var(--accent-wash)] px-3 py-2"
              title={route.data.reason}
              aria-label={`${t.sim.routeLabel}: ${route.data.reason}`}
            >
              <span className="text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
                {t.sim.routeLabel}
              </span>
              <span className="tabular text-[12px] font-semibold text-[var(--accent-ink)]">
                {route.data.provider} · {route.data.model}
              </span>
            </section>
          ) : null}

          <ProbabilityBreakdown
            p={simCase.p}
            baseRate={simCase.base_rate}
            contributions={simCase.contributions}
          />
        </div>
      ) : null}
    </Sheet>
  );
}

/**
 * Render the fetched audit trail with the same shape the stream uses.
 *
 * The backend already builds this for the stream; rebuilding it here from the
 * fetched trail keeps the panel usable for any case, simulated or real, without
 * a second endpoint. Copy stays thin on purpose — the payload's own `reason`
 * wins wherever the engine wrote one.
 */
function buildSteps(detail: TransactionDetail): TraceStep[] {
  const RETRY_CAP = 3;
  const VOICE_CAP = 2;
  let retries = 0;
  let voice = 0;
  let dispatches = 0;
  const channels: string[] = [];

  return [...detail.audit_trail]
    .sort((a, b) => a.id - b.id)
    .map((entry, index) => {
      const payload = entry.payload ?? {};
      const rule = typeof payload.stopping_rule === "string" ? payload.stopping_rule : null;
      const channel = typeof payload.channel === "string" ? payload.channel : null;

      if (entry.action_type === "INTERVENTION_DISPATCH") {
        dispatches += 1;
        if (channel && !channels.includes(channel)) channels.push(channel);
        if (channel === "VOICE") voice += 1;
        if (payload.action === "RETRY_CHARGE") retries += 1;
      } else if (entry.action_type === "RETRY_SCHEDULED" && !rule) {
        retries += 1;
      }

      return {
        step: index + 1,
        node: entry.node_name,
        decision: decisionOf(entry.action_type, payload, rule),
        reason: typeof payload.reason === "string" ? payload.reason : "",
        rule: rule as TraceStep["rule"],
        outcome: entry.outcome,
        at: entry.timestamp,
        allowed_at_this_moment: {
          retries_used: retries,
          retries_cap: RETRY_CAP,
          voice_used: voice,
          voice_cap: VOICE_CAP,
          channels_used: [...channels],
          dispatches,
        },
      };
    });
}

function decisionOf(
  actionType: string,
  payload: Record<string, unknown>,
  rule: string | null,
): string {
  if (rule === "TRAI_QUIET_HOURS") return "Deferred";
  if (rule) return "Stopped";
  if (payload.policy_block) return "Handed to a human";
  if (actionType === "INTERVENTION_DISPATCH") {
    return `Sent a ${humanizeEnum(String(payload.action ?? "")).toLowerCase()}`;
  }
  if (actionType === "RETRY_SCHEDULED") return "Waiting";
  if (payload.disposition === "RECOVERED") return "Recovered";
  if (payload.root_cause) return "Diagnosed";
  return humanizeEnum(String(payload.event ?? "State change"));
}
