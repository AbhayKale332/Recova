"use client";

import type { ReactNode } from "react";

/** A phone bezel. Purely decorative chrome around WhatsAppThread. */
export function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[380px] flex-col overflow-hidden rounded-[28px] border border-neutral-300 bg-neutral-900 p-2 shadow-xl">
      <div className="flex items-center justify-center py-1" aria-hidden>
        <div className="h-1.5 w-16 rounded-full bg-neutral-700" />
      </div>
      <div className="flex min-h-[480px] flex-1 flex-col overflow-hidden rounded-[20px] bg-[#e5ddd5]">
        {children}
      </div>
    </div>
  );
}
