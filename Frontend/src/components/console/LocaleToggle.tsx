"use client";

import { LOCALES, useI18n } from "@/lib/i18n";

/**
 * The locale toggle is not cosmetic: `locale` is passed to the live run and the
 * batch recovery, and the backend drafts customer-facing messages in that
 * language. Switching it demonstrably changes agent behaviour.
 */
export function LocaleToggle() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div
      role="group"
      aria-label={t.locale.switchLabel}
      className="flex shrink-0 rounded border border-[var(--border)] bg-[var(--surface)] p-0.5"
    >
      {LOCALES.map((code) => {
        const active = code === locale;
        return (
          <button
            key={code}
            type="button"
            onClick={() => setLocale(code)}
            aria-pressed={active}
            className={`rounded px-2 py-1 text-[12px] font-medium transition-colors duration-150 ${
              active
                ? "bg-[var(--accent-wash)] text-[var(--accent-ink)]"
                : "text-[var(--muted)] hover:text-[var(--ink)]"
            }`}
          >
            {t.locale[code]}
          </button>
        );
      })}
    </div>
  );
}
