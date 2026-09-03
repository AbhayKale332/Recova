import Link from "next/link";

/**
 * The landing page is built last (step 7) — it is the easiest screen and the
 * least load-bearing. For now it exists so `/` resolves and the console is one
 * click away.
 */
export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-[640px] flex-col justify-center gap-4 px-5 py-16">
      <div className="flex items-center gap-2">
        <span className="size-2 rounded-full bg-[var(--accent)]" aria-hidden />
        <span className="text-[15px] font-semibold tracking-tight">Recova</span>
      </div>
      <h1 className="text-[28px] leading-tight font-semibold tracking-tight text-balance">
        Revenue recovery that knows when to stop.
      </h1>
      <p className="text-[14px] text-[var(--muted)]">
        The landing page is built last. The console is the product.
      </p>
      <Link
        href="/console"
        className="w-fit rounded bg-[var(--accent)] px-3.5 py-2 text-[13px] font-semibold text-white transition-colors duration-150 hover:bg-[var(--accent-ink)]"
      >
        Open the console
      </Link>
    </main>
  );
}
