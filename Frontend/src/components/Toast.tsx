"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useI18n } from "@/lib/i18n";

/**
 * Every mutation reports success *and* failure, with a specific reason.
 * There is no silent-failure path in this app: `toast.failure` always takes a
 * reason string, and callers build it from the ApiError.
 */

export type ToastTone = "success" | "failure" | "info";

export interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  body?: string;
}

interface ToastApi {
  success: (title: string, body?: string) => void;
  failure: (title: string, reason: string) => void;
  info: (title: string, body?: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const AUTO_DISMISS_MS: Record<ToastTone, number | null> = {
  success: 6000,
  info: 6000,
  // A failure names a reason the operator may need to act on; it waits to be read.
  failure: null,
};

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (tone: ToastTone, title: string, body?: string) => {
      const id = nextId++;
      setItems((prev) => [...prev, { id, tone, title, body }]);
      const ttl = AUTO_DISMISS_MS[tone];
      if (ttl !== null) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), ttl),
        );
      }
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (title, body) => push("success", title, body),
      failure: (title, reason) => push("failure", title, reason),
      info: (title, body) => push("info", title, body),
      dismiss,
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}

const TONE_STYLE: Record<ToastTone, { ring: string; dot: string; label: string }> = {
  success: { ring: "ring-green-300", dot: "bg-[var(--recovered)]", label: "Success" },
  failure: { ring: "ring-rose-300", dot: "bg-[var(--lost)]", label: "Failed" },
  info: { ring: "ring-neutral-300", dot: "bg-[var(--stopped)]", label: "Notice" },
};

function ToastViewport({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  const { t } = useI18n();

  return (
    <div
      aria-live="polite"
      aria-label={t.toast.notifications}
      className="pointer-events-none fixed inset-x-3 bottom-3 z-[60] flex flex-col gap-2 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-[380px]"
    >
      {items.map((item) => {
        const style = TONE_STYLE[item.tone];
        return (
          <div
            key={item.id}
            role={item.tone === "failure" ? "alert" : "status"}
            className={`pointer-events-auto flex gap-2.5 rounded-md bg-[var(--surface)] p-3 shadow-lg ring-1 ${style.ring}`}
          >
            <span className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`} aria-hidden />
            <div className="min-w-0 flex-1">
              {/* Tone is carried by text as well as colour. */}
              <span className="sr-only">{style.label}: </span>
              <p className="text-[13px] font-semibold text-[var(--ink)]">{item.title}</p>
              {item.body ? (
                <p className="mt-0.5 text-[12px] leading-snug break-words text-[var(--muted)]">
                  {item.body}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(item.id)}
              className="-m-1 h-7 w-7 shrink-0 rounded text-[var(--muted)] transition-colors duration-150 hover:bg-neutral-100 hover:text-[var(--ink)]"
              aria-label={t.toast.dismiss}
            >
              <span aria-hidden>×</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
