/**
 * Ready-made cases for the console's "Start from a sample" launch screen.
 *
 * Each entry builds exactly one `CustomCase` — picking a sample appends that
 * single case to the Case editor (`scenario.custom_cases`). The set is meant
 * to cover visibly different situations (failure class, customer reply,
 * budget already spent, time of day) so a first-time viewer can see the agent
 * behave differently without filling in the form.
 */

import type { CustomCase, ReplyKind } from "@/lib/simulation";

export interface SampleCase {
  key: string;
  title: string;
  blurb: string;
  build: () => CustomCase;
}

function make(overrides: Partial<CustomCase>): CustomCase {
  return {
    customer_name: "Customer",
    amount_inr: 5000,
    failure_class: 1,
    reply_text: null,
    reply: null as ReplyKind | null,
    retries_used: 0,
    voice_attempts: 0,
    days_overdue: null,
    outcome_event: null,
    playbook: null,
    clock_ist: null,
    ...overrides,
  };
}

export const SAMPLE_CASES: SampleCase[] = [
  {
    key: "gateway-timeout",
    title: "Gateway timeout, first attempt",
    blurb: "A ₹4,200 payment dropped on a UPI switch timeout. No outreach yet.",
    build: () =>
      make({
        customer_name: "Rohit Sharma",
        amount_inr: 4200,
        failure_class: 1,
        days_overdue: 0,
      }),
  },
  {
    key: "checkout-otp",
    title: "Abandoned at the OTP step",
    blurb: "₹1,899 checkout left at 3DS. Customer replies that they are ready to pay.",
    build: () =>
      make({
        customer_name: "Ananya Iyer",
        amount_inr: 1899,
        failure_class: 2,
        reply: "cooperative",
        reply_text: "haan abhi karta hoon, link bhej do",
      }),
  },
  {
    key: "mandate-month-end",
    title: "Subscription debit, month-end low balance",
    blurb: "₹599 auto-debit failed on the 28th. Salary lands on the 1st.",
    build: () =>
      make({
        customer_name: "Vikram Desai",
        amount_inr: 599,
        failure_class: 3,
        days_overdue: 3,
        reply: "p2p",
        reply_text: "1 tarikh ko salary aate hi ho jayega",
      }),
  },
  {
    key: "invoice-net30",
    title: "Net-30 invoice, 40 days overdue",
    blurb: "₹86,000 B2B invoice past due. Buyer keeps promising a date.",
    build: () =>
      make({
        customer_name: "Meridian Supplies Pvt Ltd",
        amount_inr: 86000,
        failure_class: 4,
        days_overdue: 40,
        reply: "p2p",
        reply_text: "parso transfer kar denge, thoda cashflow issue tha",
      }),
  },
  {
    key: "retries-exhausted",
    title: "Retries already spent",
    blurb: "₹2,500 case with 3 retries and 1 voice attempt used — near the guardrail.",
    build: () =>
      make({
        customer_name: "Priya Nair",
        amount_inr: 2500,
        failure_class: 3,
        retries_used: 3,
        voice_attempts: 1,
        days_overdue: 12,
      }),
  },
  {
    key: "quiet-hours",
    title: "Comes in during quiet hours",
    blurb: "₹7,400 case at 21:30 IST — TRAI quiet hours should hold outreach.",
    build: () =>
      make({
        customer_name: "Arjun Menon",
        amount_inr: 7400,
        failure_class: 1,
        clock_ist: "21:30",
      }),
  },
  {
    key: "dispute",
    title: "Customer disputes the charge",
    blurb: "₹3,100 case where the reply is a chargeback threat — automation must freeze.",
    build: () =>
      make({
        customer_name: "Sana Kapoor",
        amount_inr: 3100,
        failure_class: 2,
        reply: "dispute",
        reply_text: "maine ye kabhi authorize nahi kiya, bank ko bolunga",
      }),
  },
  {
    key: "opt-out",
    title: "Customer asks to stop contact",
    blurb: "₹950 case where the customer opts out — all outreach must stop.",
    build: () =>
      make({
        customer_name: "Deepak Rao",
        amount_inr: 950,
        failure_class: 3,
        reply: "opt_out",
        reply_text: "please stop messaging me",
      }),
  },
];
