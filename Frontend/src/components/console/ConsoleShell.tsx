"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { LocaleToggle } from "@/components/console/LocaleToggle";
import { useConsole } from "@/components/console/ConsoleContext";
import { Money } from "@/components/Money";
import { useI18n } from "@/lib/i18n";
import { formatRatio } from "@/lib/format";

/**
 * The /console/* shell: a summary top bar plus three nav destinations.
 * Below `md` the nav becomes a bottom bar — three items fit natively.
 */

const DESTINATIONS = [
  { href: "/console", key: "console" as const, exact: true },
  { href: "/console/subscriptions", key: "subscriptions" as const, exact: false },
  { href: "/console/guardrails", key: "guardrails" as const, exact: false },
  { href: "/console/audit", key: "audit" as const, exact: false },
];

export function ConsoleShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const { run, seed, seeding } = useConsole();
  // The top bar reports the run in progress, not a stored total — there is no
  // standing figure to show until the user has run something.
  const complete = run.complete;

  const isActive = (href: string, exact: boolean) =>
    exact ? pathname === href : pathname.startsWith(href);

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg)]">
      <a
        href="#console-main"
        className="sr-only-focusable focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:h-auto focus:w-auto focus:rounded focus:bg-[var(--surface)] focus:px-3 focus:py-2 focus:ring-1 focus:ring-[var(--accent)]"
      >
        {t.nav.skipToContent}
      </a>

      <header className="sticky top-0 z-30 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2 sm:px-4">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <span className="size-2 rounded-full bg-[var(--accent)]" aria-hidden />
            <span className="text-[15px] font-semibold tracking-tight">{t.brand.name}</span>
          </Link>

          {/* The current run's totals, so the money stays on screen across routes. */}
          {complete ? (
            <dl className="order-3 flex min-w-0 items-center gap-x-4 gap-y-1 overflow-x-auto text-[12px] sm:order-none">
              <div className="flex shrink-0 items-baseline gap-1.5">
                <dt className="text-[var(--muted)]">{t.sim.measured}</dt>
                <dd className="font-semibold text-[var(--recovered)]">
                  <Money value={complete.recovered_inr} compact />
                </dd>
              </div>
              <div className="flex shrink-0 items-baseline gap-1.5">
                <dt className="text-[var(--muted)]">{t.console.grrrShort}</dt>
                <dd className="tabular font-semibold">{formatRatio(complete.grrr)}</dd>
              </div>
              <div className="hidden shrink-0 items-baseline gap-1.5 lg:flex">
                <dt className="text-[var(--muted)]">{t.console.atRisk}</dt>
                <dd className="font-semibold">
                  <Money value={complete.at_risk_inr} compact />
                </dd>
              </div>
            </dl>
          ) : null}

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <LocaleToggle />
            <button
              type="button"
              onClick={seed}
              disabled={seeding}
              className="hidden rounded border border-[var(--border)] px-2 py-1 text-[12px] font-medium transition-colors duration-150 hover:border-neutral-400 disabled:opacity-60 sm:block"
            >
              {seeding ? t.actions.reseeding : t.actions.reseed}
            </button>
          </div>
        </div>

        {/* Desktop nav sits under the summary; on mobile it moves to the bottom bar. */}
        <nav
          aria-label={t.nav.primary}
          className="mx-auto hidden max-w-[1400px] gap-1 px-3 sm:px-4 md:flex"
        >
          {DESTINATIONS.map((d) => {
            const active = isActive(d.href, d.exact);
            return (
              <Link
                key={d.href}
                href={d.href}
                aria-current={active ? "page" : undefined}
                className={`-mb-px border-b-2 px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150 ${
                  active
                    ? "border-[var(--accent)] text-[var(--accent-ink)]"
                    : "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"
                }`}
              >
                {t.nav[d.key]}
              </Link>
            );
          })}
        </nav>
      </header>

      <main
        id="console-main"
        className="mx-auto w-full max-w-[1400px] flex-1 px-3 pt-3 pb-24 sm:px-4 md:pb-8"
      >
        {children}
      </main>

      <nav
        aria-label={t.nav.primary}
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-[var(--border)] bg-[var(--surface)] pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {DESTINATIONS.map((d) => {
          const active = isActive(d.href, d.exact);
          return (
            <Link
              key={d.href}
              href={d.href}
              aria-current={active ? "page" : undefined}
              className={`flex flex-col items-center gap-0.5 py-2.5 text-[12px] font-medium transition-colors duration-150 ${
                active ? "text-[var(--accent-ink)]" : "text-[var(--muted)]"
              }`}
            >
              <span
                className={`h-0.5 w-6 rounded-full ${active ? "bg-[var(--accent)]" : "bg-transparent"}`}
                aria-hidden
              />
              {t.nav[d.key]}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
