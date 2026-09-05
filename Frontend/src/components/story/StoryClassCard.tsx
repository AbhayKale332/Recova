"use client";

import { motion } from "framer-motion";
import { getFailureClass } from "@/lib/story-classes";

// One blue family — soft shade per class so the four cards still read apart.
const ACCENT: Record<number, string> = {
  1: "#1a56db",
  2: "#2563eb",
  3: "#3b82f6",
  4: "#60a5fa",
};

/**
 * The reassurance card that slides in once a beat's problem has been read.
 * Reuses the plain-language story copy and links into the live console.
 */
export default function StoryClassCard({ classId }: { classId: 1 | 2 | 3 | 4 }) {
  const copy = getFailureClass(classId);
  const accent = ACCENT[classId];

  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: "-15% 0px -15% 0px" }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="mt-8 max-w-md rounded-2xl border border-black/5 bg-white/80 p-6 text-left shadow-[0_20px_50px_-24px_rgba(20,40,80,0.35)] backdrop-blur"
    >
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: accent }} />
        <span
          className="font-mono text-[11px] uppercase tracking-[0.22em]"
          style={{ color: accent }}
        >
          {copy.tag}
        </span>
      </div>

      <h3 className="story-display mt-3 text-2xl">{copy.title}</h3>

      <p className="mt-3 text-sm leading-relaxed text-muted">{copy.problem}</p>
      <div className="mt-4 rounded-xl p-4" style={{ background: "var(--color-clay-soft)" }}>
        <p
          className="font-mono text-[10px] uppercase tracking-[0.2em]"
          style={{ color: "var(--color-clay)" }}
        >
          What the agent does
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-fg">{copy.rescue}</p>
      </div>
    </motion.div>
  );
}
