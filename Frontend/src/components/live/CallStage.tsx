"use client";

import { fillTemplate, useI18n } from "@/lib/i18n";
import type { LiveCallOffer } from "@/lib/simulation";

/**
 * Placeholder stage for a voice tool. Renders the `call_offer` event only —
 * no `@vapi-ai/web` here, that arrives in Part 6. Nothing on this screen
 * talks to a live service, so nothing here can fail live on camera.
 */
export function CallStage({ offer }: { offer: LiveCallOffer | null }) {
  const { t } = useI18n();
  if (!offer) return null;

  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-[var(--border)] bg-[var(--bg)] px-4 py-6 text-center">
      <p className="text-[13px] font-semibold">{t.live.callOffered}</p>
      {offer.call_session_id != null ? (
        <p className="tabular text-[12px] text-[var(--muted)]">
          {fillTemplate(t.live.callSessionId, { id: offer.call_session_id })}
        </p>
      ) : null}
      <p className="max-w-[36ch] text-[12px] text-[var(--muted)]">{t.live.callComingSoon}</p>
    </div>
  );
}
