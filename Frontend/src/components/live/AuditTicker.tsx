"use client";

import { useI18n } from "@/lib/i18n";
import { humanizeEnum } from "@/lib/format";
import type { LiveTurnEvent } from "@/hooks/useLiveSession";

/**
 * A live projection of the audit rows this session is writing, in arrival
 * order. Every line here corresponds to a `record_audit()` call the backend
 * already made — this renders the receipt, it does not narrate over it.
 */
export function AuditTicker({ events }: { events: LiveTurnEvent[] }) {
  const { t, locale } = useI18n();
  const rows = events.filter((event) => event.kind !== "start");

  if (!rows.length) {
    return <p className="text-[12px] text-[var(--muted)]">{t.live.auditEmpty}</p>;
  }

  return (
    <ol className="flex flex-col gap-1.5 text-[12px]">
      {rows.map((event, index) => (
        <li key={index} className="flex items-baseline gap-2">
          <time className="tabular shrink-0 text-[11px] text-[var(--muted)]">
            {new Date(event.at).toLocaleTimeString(locale === "hi" ? "hi-IN" : "en-IN", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </time>
          <span className="min-w-0 flex-1">{describe(event)}</span>
        </li>
      ))}
    </ol>
  );
}

function describe(event: LiveTurnEvent): string {
  switch (event.kind) {
    case "start":
      return "";
    case "step":
      return event.data.label ?? event.data.rule ?? humanizeEnum(event.data.phase);
    case "diagnosis":
      return `${event.data.root_cause} → ${humanizeEnum(event.data.playbook)}`;
    case "route":
      return event.data.provider === "deterministic"
        ? `${event.data.task}: seeded, no model call`
        : `${event.data.task} routed to ${event.data.provider} · ${event.data.model}`;
    case "decision":
      return event.data.requested_tool && event.data.requested_tool !== event.data.tool
        ? `${humanizeEnum(event.data.requested_tool)} refused → ${humanizeEnum(event.data.tool)}`
        : `Decision: ${humanizeEnum(event.data.tool)}`;
    case "message":
      return `${humanizeEnum(event.data.sender)}: "${truncate(event.data.body)}"`;
    case "dispatch":
      return `Dispatched via ${humanizeEnum(event.data.channel)}${event.data.simulated ? " (simulated)" : ""}`;
    case "reminder":
      return `Reminder added to calendar · ${event.data.label} (${event.data.date})`;
    case "artifact":
      return `${humanizeEnum(event.data.kind)} minted · ${event.data.detail}`;
    case "call_offer":
      return "Call offered";
    case "status":
      return `Status → ${humanizeEnum(event.data.final_state)}`;
    case "complete":
      return `Session complete → ${humanizeEnum(event.data.final_state)}`;
  }
}

function truncate(text: string, max = 60): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
