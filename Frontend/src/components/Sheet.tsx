"use client";

import { useCallback, useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/lib/i18n";

/**
 * The one overlay primitive. Every overlay in the app uses it.
 *
 * Traps focus, closes on Escape, restores focus to whatever opened it, and
 * locks background scroll. `side="right"` is the desktop case panel;
 * `side="bottom"` is the mobile full sheet; `side="center"` is a confirmation.
 */

export type SheetSide = "right" | "bottom" | "center";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Rendered under the title, e.g. the case id. */
  subtitle?: ReactNode;
  side?: SheetSide;
  /** Pinned to the bottom of the panel, outside the scroll area. */
  footer?: ReactNode;
  children: ReactNode;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';

export function Sheet({
  open,
  onClose,
  title,
  subtitle,
  side = "right",
  footer,
  children,
}: SheetProps) {
  const { t } = useI18n();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  // Remember what had focus before the sheet opened, and give it back on close.
  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    return () => {
      const target = restoreRef.current;
      // Deferred: the trigger may be re-rendering as the sheet unmounts.
      if (target?.isConnected) requestAnimationFrame(() => target.focus());
    };
  }, [open]);

  // Move focus into the panel once it exists.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const first = panel.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel).focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, [open]);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  if (!open || typeof document === "undefined") return null;

  const panelClass =
    side === "right"
      ? "ml-auto h-full w-full max-w-[560px] border-l border-[var(--border)]"
      : side === "bottom"
        ? "mt-auto h-[92vh] w-full rounded-t-xl border-t border-[var(--border)]"
        : "m-auto w-full max-w-[480px] rounded-lg border border-[var(--border)] shadow-xl";

  return createPortal(
    <div className="fixed inset-0 z-50 flex" onKeyDown={onKeyDown}>
      <button
        type="button"
        aria-label={t.actions.close}
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-neutral-900/25"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`relative flex flex-col bg-[var(--surface)] shadow-xl outline-none ${panelClass}`}
      >
        <header className="flex items-start gap-3 border-b border-[var(--border)] px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="truncate text-[15px] font-semibold text-[var(--ink)]">
              {title}
            </h2>
            {subtitle ? (
              <div className="mt-0.5 text-[12px] text-[var(--muted)]">{subtitle}</div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded text-[var(--muted)] transition-colors duration-150 hover:bg-neutral-100 hover:text-[var(--ink)]"
          >
            <span aria-hidden className="text-lg leading-none">
              ×
            </span>
            <span className="sr-only">{t.actions.close}</span>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>

        {footer ? (
          <footer className="border-t border-[var(--border)] px-4 py-3">{footer}</footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
