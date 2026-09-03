"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { en, type Dictionary, type Locale } from "@/lib/i18n/dictionaries/en";
import { hi } from "@/lib/i18n/dictionaries/hi";

const DICTIONARIES: Record<Locale, Dictionary> = { en, hi };
const STORAGE_KEY = "recova.locale";

export const LOCALES: Locale[] = ["en", "hi"];

/** The language the backend drafts outreach in, named in the reader's own language. */
export const LOCALE_NAMES: Record<Locale, Record<Locale, string>> = {
  en: { en: "English", hi: "Hindi" },
  hi: { en: "अंग्रेज़ी", hi: "हिन्दी" },
};

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "hi";
}

/**
 * The stored locale is external state, so it is read through
 * `useSyncExternalStore`: the server snapshot is "en", the client snapshot
 * comes from localStorage, and React handles the hydration handoff without a
 * mismatch or a setState-in-effect.
 */
const listeners = new Set<() => void>();
let cached: Locale | null = null;

function readStoredLocale(): Locale {
  if (cached !== null) return cached;
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private mode or blocked storage — English is a fine default.
  }
  cached = isLocale(stored) ? stored : "en";
  return cached;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  // Another tab changing the locale should move this one too.
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      cached = null;
      onChange();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function writeStoredLocale(next: Locale): void {
  cached = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Non-fatal: the choice just won't survive a reload.
  }
  listeners.forEach((listener) => listener());
}

interface I18nValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dictionary;
  /** Fills {placeholders} in a dictionary string. */
  fill: (template: string, values: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function fillTemplate(
  template: string,
  values: Record<string, string | number>,
): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, readStoredLocale, () => "en" as Locale);

  // Keeping <html lang> in step is exactly what an effect is for: pushing React
  // state out to the DOM.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => writeStoredLocale(next), []);

  const value = useMemo<I18nValue>(
    () => ({ locale, setLocale, t: DICTIONARIES[locale], fill: fillTemplate }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside <I18nProvider>");
  return value;
}

export type { Dictionary, Locale };
