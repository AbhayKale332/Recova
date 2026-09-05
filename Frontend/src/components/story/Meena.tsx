"use client";

import { useState } from "react";
import type { Pose } from "@/lib/story";

/**
 * Meena's doodle. Renders /public/meena/meena-<pose>.png (one consistent
 * character across poses). Until the assets are dropped in, a friendly
 * placeholder figure stands in so the whole scroll works and the real art
 * slots in with no code change.
 */

const FILE: Record<Pose, string> = {
  wave: "meena-wave.png",
  worried: "meena-worried.png",
  confused: "meena-confused.png",
  facepalm: "meena-facepalm.png",
  hips: "meena-hips.png",
  tired: "meena-tired.png",
  hopeful: "meena-hopeful.png",
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
      aria-label={`Meena — ${pose}`}
    >
      {/* hair */}
      <path
        d="M92 60c0-24 56-24 56 0 6 20 4 40-4 52-14-6-34-6-48 0-8-12-10-32-4-52z"
        fill="#4a2c22"
      />
      {/* head */}
      <circle cx="120" cy="86" r="30" fill="#f0c9a8" />
      {/* body — kurta in clay */}
      <path
        d="M86 150c0-18 68-18 68 0l10 120c-30 10-58 10-88 0z"
        fill="var(--color-clay)"
      />
      {/* static arm */}
      <rect x="150" y="152" width="16" height="86" rx="8" fill="#f0c9a8" />
      {/* gesturing arm (rotates per pose) */}
      <g transform={`rotate(${angle} 82 158)`}>
        <rect x="66" y="150" width="16" height="86" rx="8" fill="#f0c9a8" />
      </g>
      {/* legs */}
      <rect x="98" y="268" width="18" height="76" rx="9" fill="#2f3a4a" />
      <rect x="124" y="268" width="18" height="76" rx="9" fill="#2f3a4a" />
    </svg>
  );
}

export default function Meena({ pose }: { pose: Pose }) {
  const [broken, setBroken] = useState(false);

  if (broken) return <Placeholder pose={pose} />;

  return (
    // Plain <img> (not next/image) so a missing asset degrades to the
    // placeholder via onError instead of throwing.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/meena/${FILE[pose]}`}
      alt={`Meena — ${pose}`}
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
