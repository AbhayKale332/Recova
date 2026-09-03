/**
 * The four failure classes, EN + HI.
 *
 * Content asset transcribed verbatim from Frontend/.Agents/Frontend-Vision.md
 * Appendix C. Do not re-translate.
 */

export interface FailureClass {
  id: 1 | 2 | 3 | 4;
  accent: "cyan" | "blue" | "amber" | "violet";
  microViz: "reroute" | "otp" | "calendar" | "invoice";
  /** The backend's FailureClass enum name for this id. */
  backendName:
    | "REALTIME_DEGRADATION"
    | "CHECKOUT_ABANDONMENT"
    | "SUBSCRIPTION_MANDATE"
    | "B2B_RECEIVABLES";
  copy: Record<"en" | "hi", { tag: string; title: string; problem: string; rescue: string }>;
}

export const FAILURE_CLASSES: FailureClass[] = [
  {
    id: 1,
    accent: "cyan",
    microViz: "reroute",
    backendName: "REALTIME_DEGRADATION",
    copy: {
      en: {
        tag: "Class 1 · Infrastructure Triage",
        title: "Failed Payments",
        problem: "UPI switch timeouts and gateway drops.",
        rescue:
          "Detects latency and dynamically re-routes to healthy fallback rails, instantly.",
      },
      hi: {
        tag: "श्रेणी 1 · इंफ्रास्ट्रक्चर ट्राइएज",
        title: "असफल भुगतान",
        problem: "UPI स्विच टाइमआउट और गेटवे ड्रॉप।",
        rescue: "लेटेंसी का पता लगाकर तुरंत स्वस्थ फॉलबैक रेल्स पर री-रूट करता है।",
      },
    },
  },
  {
    id: 2,
    accent: "blue",
    microViz: "otp",
    backendName: "CHECKOUT_ABANDONMENT",
    copy: {
      en: {
        tag: "Class 2 · Friction Rescue",
        title: "Abandoned Checkouts",
        problem: "Users dropping at the OTP / 3DS step.",
        rescue:
          "Dispatches a 1-tap UPI Autopay link via WhatsApp, bypassing card friction.",
      },
      hi: {
        tag: "श्रेणी 2 · फ्रिक्शन रेस्क्यू",
        title: "छोड़े गए चेकआउट",
        problem: "OTP / 3DS चरण पर उपयोगकर्ता छोड़ रहे हैं।",
        rescue: "WhatsApp के ज़रिए 1-टैप UPI ऑटोपे लिंक भेजता है, कार्ड फ्रिक्शन से बचते हुए।",
      },
    },
  },
  {
    id: 3,
    accent: "amber",
    microViz: "calendar",
    backendName: "SUBSCRIPTION_MANDATE",
    copy: {
      en: {
        tag: "Class 3 · Smart Sequencer",
        title: "Failed Subscriptions",
        problem: "Auto-debits failing on month-end low balance.",
        rescue: "Defers the retry to align with the user's salary-credit window.",
      },
      hi: {
        tag: "श्रेणी 3 · स्मार्ट सीक्वेंसर",
        title: "असफल सब्सक्रिप्शन",
        problem: "महीने के अंत में कम बैलेंस से ऑटो-डेबिट विफल।",
        rescue:
          "रीट्राई को उपयोगकर्ता की सैलरी-क्रेडिट विंडो के साथ संरेखित करने के लिए स्थगित करता है।",
      },
    },
  },
  {
    id: 4,
    accent: "violet",
    microViz: "invoice",
    backendName: "B2B_RECEIVABLES",
    copy: {
      en: {
        tag: "Class 4 · P2P Tracker",
        title: "Overdue Invoices",
        problem: "Overdue Net-30 invoices awaiting manual follow-up.",
        rescue: "Negotiates and extracts a hard Promise-to-Pay (P2P) date.",
      },
      hi: {
        tag: "श्रेणी 4 · P2P ट्रैकर",
        title: "बकाया इनवॉइस",
        problem: "मैन्युअल फॉलो-अप की प्रतीक्षा में अतिदेय Net-30 चालान।",
        rescue: "बातचीत करके एक ठोस Promise-to-Pay (P2P) तिथि प्राप्त करता है।",
      },
    },
  },
];

const BY_ID = new Map(FAILURE_CLASSES.map((fc) => [fc.id, fc]));

export function failureClass(id: number | null | undefined): FailureClass | null {
  return id == null ? null : (BY_ID.get(id as 1 | 2 | 3 | 4) ?? null);
}

/**
 * In navigation and filters, show the plain problem name ("Overdue Invoices"),
 * not "Class 4" (Appendix C).
 */
export function classTitle(id: number | null | undefined, locale: "en" | "hi"): string {
  return failureClass(id)?.copy[locale].title ?? "—";
}

/** Tailwind classes per class accent. Chips only — never a page-wide theme. */
export const CLASS_ACCENT_CLASS: Record<FailureClass["accent"], string> = {
  cyan: "bg-cyan-50 text-cyan-800 ring-cyan-300",
  blue: "bg-blue-50 text-blue-800 ring-blue-300",
  amber: "bg-amber-50 text-amber-800 ring-amber-300",
  violet: "bg-violet-50 text-violet-800 ring-violet-300",
};

export const CLASS_ACCENT_DOT: Record<FailureClass["accent"], string> = {
  cyan: "bg-cyan-500",
  blue: "bg-blue-500",
  amber: "bg-amber-500",
  violet: "bg-violet-500",
};
