"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useScroll,
  useTransform,
} from "framer-motion";
import { STORY, CHARACTER_NAME } from "@/lib/story";
import Meena from "./Meena";
import Shashank from "./Shashank";
import SpeechCloud from "./SpeechCloud";
import StoryClassCard from "./StoryClassCard";

const CHARACTERS = { meena: Meena, shashank: Shashank } as const;

const AMP = 15; // horizontal weave amplitude (vw)

/**
 * Scroll-linked narrative. Meena's horizontal position is a continuous
 * function of scroll progress (a sine weave), so she *glides* along an S-curve
 * as you scroll rather than snapping between a left and a right slot. A row of
 * beat markers on the left fills as you move through the story, and each beat's
 * words ride the side opposite the character.
 */
export default function StoryScene() {
  const sceneRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);
  const activeRef = useRef(0);
  const beat = STORY[active];
  const segments = STORY.length - 1;

  const { scrollYProgress } = useScroll({
    target: sceneRef,
    offset: ["start start", "end end"],
  });

  // Drive the active beat (and thus the pose) straight off scroll progress, so
  // the doodle swaps reliably as you scroll in either direction.
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const idx = Math.max(0, Math.min(segments, Math.round(p * segments)));
    if (idx !== activeRef.current) {
      activeRef.current = idx;
      setActive(idx);
    }
  });

  // Continuous, scroll-linked weave that lands on the side OPPOSITE each beat's
  // text at every beat centre (text alternates even=right / odd=left).
  const doodleX = useTransform(
    scrollYProgress,
    (p) => `${-AMP * Math.cos(Math.PI * p * segments)}vw`,
  );
  const doodleY = useTransform(
    scrollYProgress,
    (p) => `${Math.cos(2 * Math.PI * p * segments) * -1.2}vh`,
  );
  const doodleRot = useTransform(
    scrollYProgress,
    (p) => Math.cos(Math.PI * p * segments) * 3,
  );
  const blobScale = useTransform(
    scrollYProgress,
    (p) => 1 + Math.abs(Math.sin(Math.PI * p * segments)) * 0.05,
  );

  // A soft wash of colour that drifts down behind the scene as you scroll —
  // replaces the old drawn journey curve.
  const washY = useTransform(scrollYProgress, [0, 1], ["-8vh", "16vh"]);
  const washScale = useTransform(scrollYProgress, [0, 0.5, 1], [0.9, 1.08, 0.94]);

  return (
    <section ref={sceneRef} className="relative">
      {/* Drifting background wash */}
      <motion.div
        aria-hidden
        style={{
          y: washY,
          scale: washScale,
          background:
            "radial-gradient(circle at 50% 40%, var(--color-clay-soft) 0%, rgba(229,237,255,0.35) 45%, transparent 72%)",
        }}
        className="pointer-events-none absolute left-1/2 top-1/3 -z-10 h-[70vh] w-[70vh] -translate-x-1/2 rounded-full blur-2xl"
      />

      {/* Story progress — one marker per beat, fills as you move through */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 z-30 hidden w-16 md:block"
      >
        <div className="sticky top-0 flex h-screen flex-col items-center justify-center gap-3">
          {STORY.map((b, i) => (
            <span
              key={b.id}
              className="relative flex h-2.5 w-2.5 items-center justify-center"
            >
              {i === active ? (
                <span
                  className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
                  style={{ background: "var(--color-clay)" }}
                />
              ) : null}
              <span
                className="h-2.5 w-2.5 rounded-full transition-transform duration-300"
                style={{
                  background: i <= active ? "var(--color-clay)" : "transparent",
                  border:
                    i <= active
                      ? "none"
                      : "1.5px solid color-mix(in srgb, var(--color-clay) 40%, transparent)",
                  transform: i === active ? "scale(1.6)" : "scale(1)",
                }}
              />
            </span>
          ))}
        </div>
      </div>

      {/* Sticky doodle — pinned centre, weaves with scroll. */}
      <div className="pointer-events-none sticky top-0 z-10 flex h-screen items-center justify-center pb-[12vh]">
        <motion.div
          style={{ x: doodleX, y: doodleY, rotate: doodleRot }}
          className="relative h-[52vh] w-[40vw] max-w-[380px] md:h-[60vh]"
        >
          <motion.div
            style={{ scale: blobScale }}
            className="doodle-blob absolute inset-0 rounded-[45%]"
          />
          <AnimatePresence mode="wait">
            {(() => {
              const Character = CHARACTERS[beat.character];
              return (
                <motion.div
                  key={`${beat.character}-${beat.pose}`}
                  initial={{ opacity: 0, y: 16, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -16 }}
                  transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  className="absolute inset-0 flex items-end justify-center"
                >
                  <Character pose={beat.pose} />
                </motion.div>
              );
            })()}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Beats scroll over the same vertical space as the sticky doodle */}
      <div className="relative z-20 -mt-[100vh]">
        {STORY.map((b, i) => {
          const textOnRight = i % 2 === 0;
          const isLast = i === segments;
          const showSpeaker = i === 0 || STORY[i - 1].character !== b.character;
          return (
            <div key={b.id} className="flex min-h-screen items-center pb-[12vh]">
              <div
                className={
                  textOnRight
                    ? "w-full max-w-md px-6 md:ml-[58%] md:max-w-sm md:px-0 md:pr-[3vw]"
                    : "w-full max-w-md px-6 md:mr-[58%] md:ml-auto md:max-w-sm md:px-0 md:pl-[3vw] md:text-right"
                }
              >
                <SpeechCloud
                  lines={b.lines}
                  speaker={showSpeaker ? CHARACTER_NAME[b.character] : undefined}
                />
                {b.classId ? <StoryClassCard classId={b.classId} /> : null}

                {isLast ? (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.3 }}
                    className="mt-8 flex flex-wrap items-center gap-4 md:justify-end"
                  >
                    <Link
                      href="/console"
                      className="inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-medium text-white transition-transform hover:scale-[1.03]"
                      style={{ background: "var(--color-clay)" }}
                    >
                      See it working
                      <span aria-hidden>→</span>
                    </Link>
                    <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
                      Watching quietly, right now
                    </span>
                  </motion.div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
