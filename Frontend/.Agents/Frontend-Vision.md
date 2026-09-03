# Recova Frontend — Vision & Agent Briefing

**Audience:** the agent or developer building the Recova frontend from scratch.

**Assume:** the repo contains **only the backend**. There is no frontend, no `node_modules`,
no design system, no ported code. You are writing every line of the client.

**This document is self-contained.** The product rationale is in §1–§12; the complete backend
contract, wire types, and content assets are in the appendices. You should not need any other
file to start.

---

## 1. Sixty-second brief

Recova is an **AI revenue-recovery agent** built for Razorpay's buildathon (Track 03).

A merchant loses money when payments fail, checkouts are abandoned, subscriptions lapse, or
invoices go unpaid. Recova finds those cases, works out *why*, picks a bounded intervention,
runs it, and stops when policy says stop.

The backend does all of that already and exposes it over HTTP. **Your job is the frontend, and
it has exactly one purpose: make it undeniable that money was actually recovered, and that the
agent stayed inside its bounds while doing it.**

Not "here is a dashboard." Not "here is an AI." *Here is the money, here is what we did to get
it, here is the receipt, and here is where we refused to go.*

---

## 2. Who is looking at this

Two viewers. Picture both.

**The judge.** Has 3–5 minutes, has seen eleven other dashboards today, is checking a rubric:
detect, diagnose, intervene, bound, escalate, stop, audit, *measure*. They will not explore.
Whatever isn't on the first screen, or one obvious click away, does not exist.

**The operator.** A support or finance person who would actually run this. They need to find one
case fast, understand what the agent did and why, and either let it continue or take over. They
are accountable for what the agent sends to real customers, so they need to trust it — and trust
comes from feedback, reversibility, and visible limits.

Design for the judge's *path* and the operator's *depth*. When they conflict, the judge's path
wins on the first screen; the operator's depth wins everywhere below it.

---

## 3. Domain vocabulary

Get these right or the copy reads as generic AI filler. Payments has precise words.

| Term | What it means here |
| --- | --- |
| **Rail** | The underlying payment network (UPI, cards, netbanking). "Re-routing to a healthy rail" = retry over a different network when one is degraded. |
| **UPI** | India's instant payment system. High volume, occasional switch timeouts — failure Class 1. |
| **3DS / OTP step** | The bank verification screen during a card payment. A notorious drop-off point — Class 2. |
| **Mandate / e-mandate** | Standing authorization to auto-debit for a subscription. Breaks, or fails on low balance — Class 3. |
| **Auto-debit retry** | Re-attempting a failed mandate charge. **RBI caps this at 3.** Not a design choice — a regulation. |
| **Salary-credit window** | Retrying right after payday instead of at month-end. The Class 3 insight. |
| **Net-30 / Net-60** | B2B invoice payment terms. Overdue receivables — Class 4. |
| **P2P (Promise-to-Pay)** | A committed payment date extracted from a buyer. The Class 4 outcome. |
| **GRRR** | Gross Revenue Recovery Rate — recovered ÷ at-risk. The headline rate (`grrr`). |
| **TTR** | Time to recovery (`avg_time_to_recovery_seconds`). |
| **Stopping rule** | A named, enumerated condition that halts recovery. Eight exist. This is the product's spine. |
| **Escalation** | Handing a case to a human. A *success* of the guardrails, not a failure. |
| **TRAI quiet hours** | No customer contact 20:00–09:00 IST. Indian telecom regulation. |

**Two distinctions you must never blur:**

- `CANCELLED` (a compliant stop — the guardrails worked) vs. `FAILED` (retries exhausted — we
  genuinely lost it). Different colors, different words, different emotional weight.
- A **failed payment** (the problem we detect) vs. a **failed recovery** (our attempt didn't
  work). Operators confuse these constantly when the copy is lazy.

---

## 4. Experience pillars

**1. The number leads.** `recovered_inr` at display size, above the fold, on the first console
screen. Everything else supports it. The brief's stated outcome is "money recovered," not
"revenue risk identified" — so a percentage must never be the biggest thing on screen.

**2. One sentence does the pitch.** The console opens with a generated plain-language summary:

> *"Recova recovered **₹4.2L of ₹9.8L** at risk across **214 cases** — 12 escalated to a human,
> 31 stopped by policy."*

If a judge reads only that sentence, they have received the entire submission. Build it early;
it is the highest-value string in the product.

**3. Restraint is the feature.** Any system can send more messages. Ours knows when to stop.
Every in-flight case carries a visible budget — attempts used vs. cap, channels left, which rule
is armed. The **bounds gauge** is the single most differentiating component in the build. It
belongs in the case panel *and* inside every live-run step.

**4. Show the work happening.** The SSE live run turns a claim into a demo. Steps stream in human
language, and each one shows what the agent was allowed to do at that moment.

**5. Calm, dense, honest.** This is an operations surface, not a landing page. Small type, tight
rows, real numbers, no decoration that delays reading a value. It should feel like a tool someone
uses on a Tuesday, not a pitch deck.

**6. Four routes, by design.** The temptation is a route per concept — a page for compliance, one
for policy, one for escalations, one per failure class. Resist it. Fewer, denser places means the
proof is found; scattered proof is proof nobody sees. Fewer *places*, never fewer *facts*.

---

## 5. Voice and tone for UI copy

Plain, specific, never breathless. The product does something serious with real customers' money.

| Don't | Do |
| --- | --- |
| "AI-powered intelligent recovery" | "Recovered ₹4.2L across 214 cases" |
| "Action completed successfully!" | "Status set to Recovered. Note saved." |
| "Something went wrong" | "Couldn't send the payment link — the backend returned 503. Retry?" |
| "Blocked" | "Stopped — RBI retry cap reached (3 of 3 attempts used)" |
| "Escalated" | "Handed to a human — dispute on file" |
| "No data" | "No cases match these filters. Clear filters, or seed the demo." |

**Rules:**
- Name the rule, the number, and the reason. "Stopped by policy" is weak; "Stopped — TRAI quiet
  hours, no contact until 09:00 IST" *is* the product.
- Every number in copy comes from the API. Never hardcode a figure — a stale number in a live
  demo is a credibility loss you don't recover from.
- Every string ships in English **and** Hindi (see §9 and Appendix C).
- Money always goes through one shared formatter, always with tabular figures.

---

## 6. Visual direction

**One theme.** Light, neutral, single accent. Do not build a second theme, a dark mode, or
route-scoped theme swaps.

- **Ground:** near-white page, white cards, neutral-200 borders. Space and hierarchy do the work,
  not color.
- **Accent:** a single teal for primary actions and links. If it isn't actionable, it isn't
  accent-colored.
- **Status:** green recovered · amber in-flight · blue escalated · slate stopped · rose lost.
  Slate for `stopped` is deliberate — a compliant stop is neutral-good, not alarming.
- **Type:** system stack for the UI, at most one display face for the landing headline. Tabular
  figures (`font-variant-numeric: tabular-nums`) everywhere money appears.
- **Density:** the console is a work surface — 13–14px body text, ~32px rows. The landing page
  may breathe; the console may not.
- **Motion:** 150ms for state changes, 250ms for panels, nothing that delays reading a number.
  All of it behind `prefers-reduced-motion`.
- **No 3D, no WebGL, no scroll-jacking, no intro gate.** `three`, `@react-three/*`, and
  `postprocessing` must never enter `package.json`. This is not a stylistic preference — a
  particle field proves nothing and costs first paint.

Suggested token set:

```css
--bg: #fafafa;        --surface: #ffffff;   --border: #e5e5e5;
--ink: #171717;       --muted: #737373;     --accent: #0d9488;
--recovered: #16a34a; --inflight: #d97706;  --escalated: #2563eb;
--stopped: #64748b;   --lost: #e11d48;
```

---

## 7. You are writing everything

Nothing is ported. Expect to author, in roughly this order:

```text
lib/api.ts             Typed fetch client — every endpoint in Appendix A, AbortSignal on reads
lib/types.ts           Wire types — copy verbatim from Appendix B
lib/format.ts          Money, dates, durations, percentages (see §8)
lib/status.ts          Lifecycle status → label + tone mapping
lib/failure-classes.ts The four classes, EN + HI — copy verbatim from Appendix C
lib/i18n/              Locale provider, dictionaries, localStorage persistence, <html lang>
hooks/useApi.ts        Abortable fetch hook that discards stale responses after unmount
hooks/useRecoveryRun.ts  EventSource wrapper for the SSE live run
```

Appendices B and C are literal source material — transcribe them rather than inventing your own
shapes or translations. Everything else is yours to design.

---

## 8. Formatting rules

- **`amount_inr` is in rupees. `max_intervention_amount_minor` is in paise (minor units).**
  Do not mix them. Convert once, at the boundary, in `format.ts`.
- Table and detail figures: `Intl.NumberFormat("en-IN", { style: "currency", currency: "INR",
  maximumFractionDigits: 0 })` → `₹4,20,000`.
- Hero and summary-sentence figures: abbreviate Indian-style — `₹4.2L` (lakh, 10⁵),
  `₹1.3Cr` (crore, 10⁷). Both formatters live in `format.ts`; nothing formats money inline.
- `grrr` is a ratio — render as a percentage with one decimal.
- `avg_time_to_recovery_seconds` and `duration_sec` are seconds — render as `4m 12s` / `2h 06m`.
- All timestamps arrive as ISO strings. Render relative ("6 min ago") in feeds, absolute with
  timezone in the audit trail.

---

## 9. Localization

English and Hindi, both first-class. The backend takes `locale=en|hi` on the live run, the batch
recovery, and the assistant, and drafts customer-facing messages in that language — so the locale
toggle demonstrably changes agent behavior, not just labels.

- One dictionary module, typed so a missing Hindi key is a compile error.
- Persist the choice to `localStorage`, set `<html lang>`, and pass it on every locale-aware call.
- Hindi needs a Devanagari-capable font stack; check that numerals and currency still align in
  tables.
- Appendix C gives you the failure-class copy in both languages, already written.

---

## 10. Repo facts an agent will otherwise get wrong

1. **The repo starts with only the backend.** Scaffold the frontend into its own directory
   (`frontend/`) unless the repo layout says otherwise.
2. **Next.js 16.x conventions differ from most training data.** After `npm install`, **read
   `node_modules/next/dist/docs/` before writing any code.** Heed deprecation notices.
3. **`next dev` writes an `AGENTS.md` block** into the frontend directory. Commit it with your
   work — deleting it from a diff only recreates it as an uncommitted change.
4. **Keep `reactStrictMode: true`.** If you find guidance saying to disable it, that advice
   existed only to work around react-three-fiber. There is no 3D here.
5. **The backend is FastAPI**, mounted under `/api/v1`. Endpoints live in
   `backend/application/endpoints/`, the enums in `backend/application/constants.py`. Read those
   two locations if you need to confirm anything in Appendix A.
6. **Point the client at the backend via `NEXT_PUBLIC_API_BASE`**, defaulting to
   `http://localhost:8000`.
7. **The database starts empty.** `POST /api/v1/admin/seed` populates the demo batch. Every
   screen must handle the unseeded state with a real call to action, not a blank page.

---

## 11. The merchant persona

The landing page's story beat needs a named merchant so the loss feels concrete. **Use a
fictional name** — `Nayantara` works well and is already used in the product's copy history.

Do **not** name the character after a real Razorpay founder or employee. The beat puts invented
dialogue in the character's mouth, the judges may know that person, and it buys nothing a
fictional persona doesn't already provide. If you want to acknowledge Razorpay, do it plainly in
a footer.

---

## 12. What success looks like

A judge opens `/console`, reads one sentence, and knows the batch result. They click one funnel
segment, open one case, press **Run it live**, and watch the agent diagnose, act, and then *stop
itself* — with the reason named on screen. They open the audit trail and see the receipt. Total
elapsed: under two minutes, no narration required.

If it does that on a laptop and on a phone, it's done.

---
---

# Appendix A — HTTP contract

Base URL: `${NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/api/v1`

```text
GET   /metrics                                  → Metrics
GET   /transactions?failure_class&status&archetype&q&limit&offset
                                                → TransactionList
GET   /transactions/{id}                        → TransactionDetail
GET   /transactions/{id}/run?locale=en|hi       → SSE stream (EventSource)
POST  /transactions/{id}/status                 {status, note}          → TransactionRow
POST  /transactions/{id}/note                   {note}                  → {id}
POST  /transactions/{id}/messages               {body, ai_drafted}      → ConversationMessage
POST  /transactions/{id}/messages/draft         {prompt}                → {draft}
POST  /transactions/{id}/payment-link           {}                      → {url, razorpay_id, simulated, message}
GET   /transactions/{id}/payment-link/status    → {paid, status, current_state}
POST  /transactions/{id}/call/start             {}                      → CallData
GET   /transactions/{id}/calls                  → {calls: CallData[]}
GET   /transactions/{id}/conversation           → Conversation
POST  /transactions/recover-batch               {transaction_ids, locale}
                                                → {total, recovered, results[{transaction_id, final_state}]}
POST  /transactions/simulate?failure_class=1..4 {}                      → TransactionRow
GET   /audit?transaction_id&limit&offset        → AuditList
GET   /escalations                              → EscalationTicket[]
POST  /escalations/{id}/resolve                 {}                      → {status}
GET   /policy                                   → PolicyResponse
PATCH /policy                                   {max_discount_pct, max_intervention_amount_minor,
                                                 allowed_actions, allowed_channels} → PolicyResponse
POST  /policy/validate                          {action, channel, discount_pct, amount_inr}
                                                → {approved, reason}
POST  /policy/screen                            {message}               → {disposition, rule, reason}
GET   /subscriptions                            → SubscriptionItem[]
POST  /subscriptions                            {customer_name, plan, amount_inr, next_debit_date, salary_day}
GET   /invoices                                 → InvoiceItem[]
POST  /invoices                                 {buyer_name, amount_inr, issue_date, due_date, terms?}
POST  /assistant/chat                           {message, locale, context} → {reply, action}
POST  /admin/seed                               {}                      → {seeded}
GET   /health
```

Reads take an `AbortSignal` and `cache: "no-store"`. Non-2xx responses should throw with the
status and path so `Toast` can show something specific.

---

# Appendix B — Wire types

Transcribe verbatim. These match the backend exactly.

```ts
export interface ClassMetric {
  at_risk_inr: number; recovered_inr: number; count: number;
  recovered_count: number; recovery_rate: number;
  top_playbook: string | null; avg_time_to_recovery_seconds: number;
}

export interface Funnel {
  at_risk: number; intervened: number; recovered: number;
  escalated: number; cancelled: number; failed: number;
}

export interface TimePoint { date: string; recovered_inr: number; cumulative_inr: number; }

export interface Metrics {
  at_risk_inr: number; recovered_inr: number; in_flight_inr: number; lost_inr: number;
  grrr: number;
  by_class: Record<string, ClassMetric>;
  funnel: Funnel;
  channel_breakdown: Record<string, { dispatched: number; recovered: number }>;
  time_series: TimePoint[];
  stopping_rules_by_name: Record<string, number>;
  counts: {
    total: number; interventions: number; escalations: number;
    stopping_rules_fired: number; recovered: number; cancelled: number; failed: number;
  };
  avg_time_to_recovery_seconds: number;
}

export type LifecycleStatus =
  | "PENDING" | "DIAGNOSING" | "WAITING" | "INTERVENING"
  | "RECOVERED" | "ESCALATED" | "CANCELLED" | "FAILED";

export interface TransactionRow {
  serial: number; transaction_id: string; razorpay_payment_id: string;
  failure_class: number; class_label: string | null; archetype: string | null;
  ai_tag: string | null; is_at_risk: boolean; confidence: number | null;
  event_type: string | null; error_code: string | null;
  status: LifecycleStatus; amount_inr: number; currency: string;
  customer_name: string | null; customer_contact_masked: string;
  time_to_recovery_seconds: number | null;
  playbook: string | null; channel: string | null; stopping_rule: string | null;
  created_at: string; updated_at: string;
}

export interface TransactionList { total: number; items: TransactionRow[]; }

export interface AuditEntry {
  id: number; transaction_id: string; node_name: string; action_type: string;
  payload: Record<string, unknown>; outcome: string; timestamp: string;
}

export interface TransactionDetail extends TransactionRow {
  diagnosis: { root_cause?: string; recommended_playbook?: string; confidence?: number };
  audit_trail: AuditEntry[];
}

export interface AuditList { total: number; items: AuditEntry[]; }

export interface EscalationTicket {
  id: number; transaction_id: string; reason: string;
  rule: string | null; status: string; created_at: string;
}

export interface ConversationMessage {
  id: number; channel: string;
  direction: "OUTBOUND" | "INBOUND";
  sender: "AGENT" | "CUSTOMER" | "SYSTEM";
  body: string; status: "SENT" | "DELIVERED" | "READ";
  seq: number; meta: Record<string, unknown> | null; created_at: string;
}

export interface CallData {
  id: number; status: string; duration_sec: number;
  outcome: string | null; provider: string | null; started_at?: string;
  turns: { speaker: "AGENT" | "CUSTOMER"; text: string; seq: number; at_offset_sec: number }[];
}

export interface Conversation { messages: ConversationMessage[]; call: CallData | null; }

export interface PolicyResponse {
  policy: {
    max_discount_pct: number; max_intervention_amount_minor: number;
    allowed_channels: string[]; allowed_actions: string[];
  };
  money_moving_actions: string[];
  stopping_rules: { name: string; description: string }[];
}

export interface SubscriptionItem {
  transaction_id: string; serial: number; customer_name: string; plan: string;
  amount_inr: number; cycle: string; next_debit_date: string; salary_day: number;
  mandate_status: string; retry_count: number; retry_cap: number;
  predicted_fail: boolean; status: string;
}

export interface InvoiceItem {
  transaction_id: string; serial: number; buyer_name: string; invoice_no: string;
  amount_inr: number; issue_date: string; due_date: string; terms: string;
  days_overdue: number; aging_bucket: string; p2p_date: string | null;
  next_reminder_date: string; status: string; open: boolean;
}
```

**Backend enumerations** (use these exact strings):

```text
LifecycleStatus   PENDING DIAGNOSING WAITING INTERVENING RECOVERED ESCALATED CANCELLED FAILED
NodeName          INGEST DIAGNOSE WAIT EXECUTE_INTERVENTION RECONCILE OPERATOR
ActionType        STATE_TRANSITION INTERVENTION_DISPATCH RETRY_SCHEDULED ESCALATION
Outcome           SUCCESS FAILURE ESCALATED
Channel           WHATSAPP VOICE PAYMENT_LINK
Action            SEND_WHATSAPP VOICE_CALL OFFER_FEE_WAIVER GENERATE_PAYMENT_LINK
                  RETRY_CHARGE CANCEL_SUBSCRIPTION
Playbook          REROUTE_RAIL PREAUTH_LINK UPI_AUTOPAY_NUDGE NEGOTIATION
                  SALARY_CYCLE_SEQUENCER MANDATE_REFRESH P2P_TRACKER
StoppingRule      NO_DOUBLE_CHARGE CROSS_DEVICE_COMPLETION RBI_MAX_RETRIES EXPLICIT_CANCEL
                  OPT_OUT DISPUTE_FREEZE TRAI_QUIET_HOURS VOICE_ATTEMPT_CAP
EscalationStatus  OPEN RESOLVED
```

Stopping rules, in human language — use this copy:

| Rule | What it means |
| --- | --- |
| `NO_DOUBLE_CHARGE` | The payment settled late; don't charge twice |
| `CROSS_DEVICE_COMPLETION` | The customer already completed it elsewhere |
| `RBI_MAX_RETRIES` | RBI cap — at most 3 auto-debit retries |
| `EXPLICIT_CANCEL` | The customer asked to cancel the plan |
| `OPT_OUT` | The customer opted out of contact |
| `DISPUTE_FREEZE` | A dispute is on file — route to a human |
| `TRAI_QUIET_HOURS` | No contact 20:00–09:00 IST |
| `VOICE_ATTEMPT_CAP` | At most 2 voice calls in 72 hours |

---

# Appendix C — The four failure classes (EN + HI)

Content asset. Transcribe verbatim; do not re-translate.

**Class 1 — accent cyan, viz "reroute"**
- EN — tag: `Class 1 · Infrastructure Triage` · title: `Failed Payments` ·
  problem: `UPI switch timeouts and gateway drops.` ·
  rescue: `Detects latency and dynamically re-routes to healthy fallback rails, instantly.`
- HI — tag: `श्रेणी 1 · इंफ्रास्ट्रक्चर ट्राइएज` · title: `असफल भुगतान` ·
  problem: `UPI स्विच टाइमआउट और गेटवे ड्रॉप।` ·
  rescue: `लेटेंसी का पता लगाकर तुरंत स्वस्थ फॉलबैक रेल्स पर री-रूट करता है।`

**Class 2 — accent blue, viz "otp"**
- EN — tag: `Class 2 · Friction Rescue` · title: `Abandoned Checkouts` ·
  problem: `Users dropping at the OTP / 3DS step.` ·
  rescue: `Dispatches a 1-tap UPI Autopay link via WhatsApp, bypassing card friction.`
- HI — tag: `श्रेणी 2 · फ्रिक्शन रेस्क्यू` · title: `छोड़े गए चेकआउट` ·
  problem: `OTP / 3DS चरण पर उपयोगकर्ता छोड़ रहे हैं।` ·
  rescue: `WhatsApp के ज़रिए 1-टैप UPI ऑटोपे लिंक भेजता है, कार्ड फ्रिक्शन से बचते हुए।`

**Class 3 — accent amber, viz "calendar"**
- EN — tag: `Class 3 · Smart Sequencer` · title: `Failed Subscriptions` ·
  problem: `Auto-debits failing on month-end low balance.` ·
  rescue: `Defers the retry to align with the user's salary-credit window.`
- HI — tag: `श्रेणी 3 · स्मार्ट सीक्वेंसर` · title: `असफल सब्सक्रिप्शन` ·
  problem: `महीने के अंत में कम बैलेंस से ऑटो-डेबिट विफल।` ·
  rescue: `रीट्राई को उपयोगकर्ता की सैलरी-क्रेडिट विंडो के साथ संरेखित करने के लिए स्थगित करता है।`

**Class 4 — accent violet, viz "invoice"**
- EN — tag: `Class 4 · P2P Tracker` · title: `Overdue Invoices` ·
  problem: `Overdue Net-30 invoices awaiting manual follow-up.` ·
  rescue: `Negotiates and extracts a hard Promise-to-Pay (P2P) date.`
- HI — tag: `श्रेणी 4 · P2P ट्रैकर` · title: `बकाया इनवॉइस` ·
  problem: `मैन्युअल फॉलो-अप की प्रतीक्षा में अतिदेय Net-30 चालान।` ·
  rescue: `बातचीत करके एक ठोस Promise-to-Pay (P2P) तिथि प्राप्त करता है।`

Shape it as:

```ts
export interface FailureClass {
  id: 1 | 2 | 3 | 4;
  accent: "cyan" | "blue" | "amber" | "violet";
  microViz: "reroute" | "otp" | "calendar" | "invoice";
  copy: Record<"en" | "hi", { tag: string; title: string; problem: string; rescue: string }>;
}
```

Class ↔ backend mapping: `1 REALTIME_DEGRADATION · 2 CHECKOUT_ABANDONMENT ·
3 SUBSCRIPTION_MANDATE · 4 B2B_RECEIVABLES`. In navigation and filters, show the plain problem
name ("Overdue Invoices"), not "Class 4".

---

# Appendix D — Status presentation

| Status | Label (EN) | Tone | Meaning |
| --- | --- | --- | --- |
| `PENDING` | Pending | muted | Detected, not yet worked |
| `DIAGNOSING` | Diagnosing | inflight | Working out the root cause |
| `WAITING` | Waiting | inflight | Deliberately paused (e.g. salary window) |
| `INTERVENING` | Intervening | inflight | Outreach in progress |
| `RECOVERED` | Recovered | recovered | Money captured |
| `ESCALATED` | With a human | escalated | Compliant handoff |
| `CANCELLED` | Stopped | stopped | A stopping rule halted it — guardrails worked |
| `FAILED` | Lost | lost | Retries exhausted |

`ESCALATED`, `CANCELLED`, and `FAILED` are three different outcomes and must read as three
different things. Collapsing them into "unsuccessful" destroys the compliance story, which is the
strongest part of this product.
