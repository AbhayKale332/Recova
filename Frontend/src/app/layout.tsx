import type { Metadata, Viewport } from "next";

import { I18nProvider } from "@/lib/i18n";
import { ToastProvider } from "@/components/Toast";

import "./globals.css";

export const metadata: Metadata = {
  title: "Recova — revenue recovery that knows when to stop",
  description:
    "An AI revenue-recovery agent for Razorpay: it detects revenue at risk, diagnoses the cause, runs a bounded intervention, escalates when needed, and stops when policy says stop.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#fafafa",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  // `lang` is corrected on the client by I18nProvider when the stored locale is Hindi.
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full">
        <I18nProvider>
          <ToastProvider>{children}</ToastProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
