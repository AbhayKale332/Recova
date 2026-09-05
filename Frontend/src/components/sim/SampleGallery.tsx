"use client";

import { SAMPLE_CASES, type SampleCase } from "@/lib/sample-cases";
import type { CustomCase } from "@/lib/simulation";

/**
 * The console's launch screen: pick one sample to drop a single case into the
 * editor, or start a blank custom case. Deliberately plain and large-type —
 * no gradients, no icons, one clear choice per card.
 */
export function SampleGallery({
  onPick,
  onCustom,
  disabled,
}: {
  onPick: (built: CustomCase) => void;
  onCustom: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Start from a sample</h2>
        <p className="mt-1 text-[15px] text-[var(--muted)]">
          Pick a case to load it into the editor, or add your own.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {SAMPLE_CASES.map((sample: SampleCase) => (
          <button
            key={sample.key}
            type="button"
            disabled={disabled}
            onClick={() => onPick(sample.build())}
            className="flex flex-col gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-left transition-colors duration-150 hover:border-[var(--accent)] disabled:opacity-50"
          >
            <span className="text-[16px] font-semibold tracking-tight">{sample.title}</span>
            <span className="text-[13px] leading-snug text-[var(--muted)]">{sample.blurb}</span>
          </button>
        ))}

        <button
          type="button"
          disabled={disabled}
          onClick={onCustom}
          className="flex flex-col justify-center gap-1.5 rounded-lg border border-dashed border-[var(--border)] p-4 text-left transition-colors duration-150 hover:border-[var(--accent)] disabled:opacity-50"
        >
          <span className="text-[16px] font-semibold tracking-tight">+ Add a custom case</span>
          <span className="text-[13px] leading-snug text-[var(--muted)]">
            Start with a blank case and fill in the details yourself.
          </span>
        </button>
      </div>
    </div>
  );
}
