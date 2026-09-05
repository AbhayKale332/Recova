"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuditTicker } from "@/components/live/AuditTicker";
import { CallStage } from "@/components/live/CallStage";
import { DecisionCard } from "@/components/live/DecisionCard";
import { PhoneFrame } from "@/components/live/PhoneFrame";
import { RouterChip } from "@/components/live/RouterChip";
import { WhatsAppThread } from "@/components/live/WhatsAppThread";
import { BoundsGauge } from "@/components/sim/BoundsGauge";
import { ClassChip } from "@/components/ClassChip";
import { LocaleToggle } from "@/components/console/LocaleToggle";
import { Money } from "@/components/Money";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState, LoadingState } from "@/components/States";
import { useToast } from "@/components/Toast";
import { useLiveSession } from "@/hooks/useLiveSession";
import { fillTemplate, useI18n } from "@/lib/i18n";
import { paiseToRupees } from "@/lib/format";
import { statusLabel } from "@/lib/status";

/**
 * The `/live` theatre. Two columns: left is the agent (router, decision,
 * bounds, audit), right is the stage (the WhatsApp phone mockup, later the
 * call stage). At mobile width they stack, stage first — the conversation is
 * the thing to watch, the "why" is secondary on a small screen.
 */
export function LiveScreen() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const sessionId = params.get("case");
  const toast = useToast();

  const session = useLiveSession(sessionId);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (session.error) toast.failure(t.states.errorTitle, session.error);
  }, [session.error, toast, t]);

  const exit = async () => {
    setExiting(true);
    await session.exit();
    router.push("/console");
  };

  if (!sessionId) {
    return (
      <div className="mx-auto max-w-[560px] px-4 py-10">
        <EmptyState
          title={t.live.notFoundTitle}
          body={t.live.notFoundBody}
          action={
            <button
              type="button"
              onClick={() => router.push("/console")}
              className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white"
            >
              {t.live.backToConsole}
            </button>
          }
        />
      </div>
    );
  }

  if (session.phase === "error" && !session.start) {
    return (
      <div className="mx-auto max-w-[560px] px-4 py-10">
        <EmptyState
          title={t.live.notFoundTitle}
          body={t.live.notFoundBody}
          action={
            <button
              type="button"
              onClick={() => router.push("/console")}
              className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[13px] font-semibold text-white"
            >
              {t.live.backToConsole}
            </button>
          }
        />
      </div>
    );
  }

  if (!session.start) {
    return (
      <div className="mx-auto max-w-[560px] px-4 py-10">
        <LoadingState label={t.live.connecting} rows={4} />
      </div>
    );
  }

  const terminal = session.finalState != null && ["RECOVERED", "ESCALATED", "CANCELLED", "FAILED"].includes(session.finalState);
  const composerDisabled = session.sending || session.typing === "agent" || terminal;

  // The artifact carries only what's being asked for *now*; the case's own
  // amount (session.start) is what turns that into a remaining balance.
  const balanceDue =
    session.artifact?.accept_partial && session.artifact.deadline
      ? {
          amountInr: Math.max(
            session.start.amount_inr - paiseToRupees(session.artifact.amount_minor),
            0,
          ),
          deadline: session.artifact.deadline,
        }
      : null;

  return (
    <div className="mx-auto flex min-h-dvh max-w-[1200px] flex-col gap-4 px-3 py-3 sm:px-4 sm:py-4">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="size-2 rounded-full bg-[var(--accent)]" aria-hidden />
          <h1 className="truncate text-[15px] font-semibold tracking-tight">{t.live.title}</h1>
          {session.start ? (
            <>
              <ClassChip failureClass={session.start.failure_class} />
              <Money value={session.start.amount_inr} className="text-[13px] font-medium" />
            </>
          ) : null}
          {terminal && session.finalState ? (
            <span className="flex items-center gap-1.5 text-[12px] text-[var(--muted)]">
              <StatusChip status={session.finalState} />
              {fillTemplate(t.live.sessionEnded, { status: statusLabel(session.finalState, t) })}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <LocaleToggle />
          <button
            type="button"
            onClick={exit}
            disabled={exiting}
            className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[12px] font-medium disabled:opacity-60"
          >
            {t.live.exit}
          </button>
        </div>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* Stage first on mobile: the conversation is what's being watched. */}
        <section
          aria-label={t.live.stageColumn}
          className="order-1 flex flex-col gap-3 lg:order-2"
        >
          <PhoneFrame>
            <WhatsAppThread
              sessionId={sessionId}
              customerName={session.start.customer_name}
              caseAmountInr={session.start.amount_inr}
              messages={session.messages}
              typing={session.typing}
              disabled={composerDisabled}
              onSend={session.reply}
            />
          </PhoneFrame>
          <CallStage offer={session.callOffer} sessionId={sessionId} />
        </section>

        <section aria-label={t.live.agentColumn} className="order-2 flex flex-col gap-3 lg:order-1">
          <RouterChip route={session.route} />
          <DecisionCard decision={session.decision} />
          {session.bounds ? (
            <div className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
              <BoundsGauge bounds={session.bounds} balanceDue={balanceDue} />
            </div>
          ) : null}
          <div className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
            <p className="mb-1.5 text-[11px] font-medium tracking-wide text-[var(--muted)] uppercase">
              {t.live.auditTitle}
            </p>
            <AuditTicker events={session.events} />
          </div>
        </section>
      </div>
    </div>
  );
}
