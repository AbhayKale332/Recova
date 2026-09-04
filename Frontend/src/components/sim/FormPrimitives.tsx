"use client";

import { useId, type ReactNode } from "react";

export function Group({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details open={defaultOpen} className="rounded-md border border-[var(--border)]">
      <summary className="cursor-pointer px-3 py-2 text-[12px] font-medium tracking-wide text-[var(--muted)] uppercase">
        {title}
      </summary>
      <div className="flex flex-col gap-3 border-t border-[var(--border)] px-3 py-3">
        {children}
      </div>
    </details>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[12px] font-medium">
        {label}
      </label>
      <div id={id}>{children}</div>
      {hint ? <p className="text-[11px] text-[var(--muted)]">{hint}</p> : null}
    </div>
  );
}

export function NumberInput({
  value,
  min,
  max,
  step = 1,
  suffix,
  disabled,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
        }}
        className="tabular w-20 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-[13px] disabled:opacity-50"
      />
      {suffix ? <span className="text-[11px] text-[var(--muted)]">{suffix}</span> : null}
    </span>
  );
}
