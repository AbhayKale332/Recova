"use client";

import { useState } from "react";
import type { Pose } from "@/lib/story";

/**
 * Shashank's doodle — Act 2 of the story. Renders
 * /public/shashank/shashank-<pose>.png (one consistent character across
 * poses). Until the assets are dropped in, a friendly placeholder figure
 * stands in so the whole scroll works and the real art slots in with no code
 * change. Mirrors Meena.tsx exactly in structure.
 */

const FILE: Record<Pose, string> = {
  wave: "shashank-wave.png",
  worried: "shashank-worried.png",
  confused: "shashank-confused.png",
  facepalm: "shashank-facepalm.png",
  hips: "shashank-hips.png",
  tired: "shashank-tired.png",
  hopeful: "shashank-hopeful.png",
};

// Per-pose scale nudges (the cropped art is already consistent portrait, so
// this is empty — kept as a hook in case a future export needs balancing).
const SCALE: Partial<Record<Pose, number>> = {};

// Rough gesture hint for the placeholder: the raised-arm angle per pose.
const ARM_ANGLE: Record<Pose, number> = {
  wave: -55,
  worried: 20,
  confused: -35,
  facepalm: -120,
  hips: 30,
  tired: 15,
  hopeful: -70,
};

function Placeholder({ pose }: { pose: Pose }) {
  const angle = ARM_ANGLE[pose];
  return (
    <svg
      viewBox="0 0 240 360"
      className="h-full w-auto"
      role="img"
      aria-label={`Shashank — ${pose}`}
    >
      {/* short hair */}
      <path d="M90 74c2-26 58-26 60 0-6-8-16-12-30-12s-24 4-30 12z" fill="#241c17" />
      {/* head */}
      <circle cx="120" cy="88" r="29" fill="#e0ad82" />
      {/* glasses */}
      <g stroke="#241c17" strokeWidth="2" fill="none">
        <circle cx="110" cy="88" r="7" />
        <circle cx="132" cy="88" r="7" />
        <path d="M117 88h8" />
      </g>
      {/* collared shirt in the story's blue */}
      <path
        d="M84 152c0-20 72-20 72 0l10 118c-31 10-61 10-92 0z"
        fill="var(--color-clay)"
      />
      {/* collar */}
      <path d="M112 132l8 12 8-12-8-6z" fill="#ffffff" />
      {/* lanyard + badge */}
      <path d="M112 132c-4 26-4 40-4 46M128 132c4 26 4 40 4 46" stroke="#0f2f6b" strokeWidth="2" fill="none" />
      <rect x="112" y="176" width="16" height="22" rx="3" fill="#ffffff" stroke="#0f2f6b" strokeWidth="1.5" />
      {/* static arm */}
      <rect x="150" y="154" width="16" height="88" rx="8" fill="#e0ad82" />
      {/* gesturing arm (rotates per pose) */}
      <g transform={`rotate(${angle} 82 160)`}>
        <rect x="66" y="152" width="16" height="88" rx="8" fill="#e0ad82" />
      </g>
      {/* trousers */}
      <rect x="98" y="268" width="18" height="78" rx="9" fill="#33415c" />
      <rect x="124" y="268" width="18" height="78" rx="9" fill="#33415c" />
    </svg>
  );
}

export default function Shashank({ pose }: { pose: Pose }) {
  const [broken, setBroken] = useState(false);

  if (broken) return <Placeholder pose={pose} />;

  return (
    // Plain <img> (not next/image) so a missing asset degrades to the
    // placeholder via onError instead of throwing.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/shashank/${FILE[pose]}`}
      alt={`Shashank — ${pose}`}
      className="h-full w-full select-none object-contain object-bottom"
      style={{
        transform: `scale(${SCALE[pose] ?? 1})`,
        transformOrigin: "center bottom",
      }}
      draggable={false}
      onError={() => setBroken(true)}
    />
  );
}
