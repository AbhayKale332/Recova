"use client";

import { motion } from "framer-motion";

/** A hand-drawn speech cloud holding one beat's dialogue lines. */
export default function SpeechCloud({
  lines,
  speaker,
}: {
  lines: string[];
  speaker?: string;
}) {
  return (
    <div className="space-y-4">
      {speaker ? (
        <motion.p
          key={`${speaker}-name`}
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-20% 0px -20% 0px" }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="story-kicker"
        >
          {speaker}
        </motion.p>
      ) : null}
      {lines.map((line, i) => (
        <motion.p
          key={i}
          initial={{ opacity: 0, y: 14, scale: 0.98 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-20% 0px -20% 0px" }}
          transition={{ duration: 0.5, delay: i * 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="speech-cloud story-display max-w-xl px-6 py-4 text-2xl leading-snug md:text-[1.7rem]"
        >
          {line}
        </motion.p>
      ))}
    </div>
  );
}
