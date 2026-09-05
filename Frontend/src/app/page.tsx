"use client";

import { useEffect, useLayoutEffect } from "react";
import Link from "next/link";

import StoryScene from "@/components/story/StoryScene";
import "@/components/story/story.css";

// Runs before paint on the client (falls back to useEffect on the server so
// SSR doesn't warn), so we can pin scroll to the top before the page is shown.
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * The landing page is Meena's story — the warm, human "why" behind the agent.
 * It bridges into the console (the "how"). The papery light theme is scoped to
 * this route via `.theme-story` on <html> and the wrapper.
 */
export default function LandingPage() {
  // Pin to the top BEFORE the first paint, so the story never flashes a late
  // beat when navigating in from a scrolled-down page.
  useIsomorphicLayoutEffect(() => {
    const prevRestore =
      "scrollRestoration" in history ? history.scrollRestoration : undefined;
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    window.scrollTo(0, 0);
    return () => {
      if (prevRestore !== undefined) history.scrollRestoration = prevRestore;
    };
  }, []);

  useEffect(() => {
    const el = document.documentElement;
    el.classList.add("theme-story");
    return () => el.classList.remove("theme-story");
  }, []);

  return (
    <div className="theme-story min-h-screen">
      <header className="px-6 pt-28 pb-6 text-center">
        <p className="story-kicker">Different scale, same leak</p>
        <h1 className="story-display mx-auto mt-4 max-w-2xl text-[clamp(2.4rem,5.5vw,3.8rem)]">
          Meet Meena and Shashank, and see the money slipping away while they work
        </h1>
        <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.28em] text-muted">
          Scroll to follow the problem
        </p>
      </header>

      <StoryScene />

      <footer className="px-6 py-20 text-center">
        <p className="story-display mx-auto max-w-xl text-2xl">
          They keep running their businesses. Something else keeps the payments
          from leaking.
        </p>
        <Link
          href="/console"
          className="mt-6 inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-medium text-white transition-transform hover:scale-[1.03]"
          style={{ background: "var(--color-clay)" }}
        >
          See what it does
          <span aria-hidden>→</span>
        </Link>
      </footer>
    </div>
  );
}
