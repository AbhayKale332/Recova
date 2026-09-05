export type Pose =
  | "wave"
  | "worried"
  | "confused"
  | "facepalm"
  | "hips"
  | "tired"
  | "hopeful";

export type Character = "meena" | "shashank";

export type StoryBeat = {
  id: string;
  character: Character;
  pose: Pose;
  lines: string[];
  classId?: 1 | 2 | 3 | 4;
};

export const CHARACTER_NAME: Record<Character, string> = {
  meena: "Meena",
  shashank: "Shashank",
};

/**
 * The story runs in two acts on the same problem.
 *
 * Act 1 — Meena: a three-person home-décor label out of Pune. The leak is
 * small enough to feel personal and invisible enough that she can't chase it.
 *
 * Act 2 — Shashank: head of revenue at a SaaS company doing crores a month.
 * His CEO wants to know where the money is going. It turns out to be Meena's
 * exact four leaks — running at a thousand times the volume.
 *
 * The point: one kitchen table or one boardroom, the leak is the same shape,
 * and it needs something that watches, understands, and recovers on its own.
 */
export const STORY: StoryBeat[] = [
  {
    id: "meena-open",
    character: "meena",
    pose: "wave",
    lines: [
      "Hi. I'm Meena.",
      "Three people run our home-décor label out of Pune. We have a WhatsApp catalog, a checkout link, and a spreadsheet I update at midnight.",
    ],
  },
  {
    id: "meena-checkout",
    character: "meena",
    pose: "worried",
    lines: [
      "Last Tuesday someone added ₹4,200 of cushion covers to her cart…",
      "…and closed the tab. No error. No complaint. Just gone.",
    ],
    classId: 2,
  },
  {
    id: "meena-payment",
    character: "meena",
    pose: "confused",
    lines: [
      "Then a card got declined. Then declined again.",
      "Fraud? A typo? An expired card? I genuinely couldn't tell you.",
    ],
    classId: 1,
  },
  {
    id: "meena-subscription",
    character: "meena",
    pose: "facepalm",
    lines: [
      "My 'Décor of the Month' box renews on its own, except when the payment quietly fails and nobody notices for three weeks.",
    ],
    classId: 3,
  },
  {
    id: "meena-receivable",
    character: "meena",
    pose: "tired",
    lines: [
      "And somewhere in my spreadsheet, an invoice just turned 46 days overdue.",
      "I didn't chase it. I was asleep.",
    ],
    classId: 4,
  },
  {
    id: "meena-turn",
    character: "meena",
    pose: "hopeful",
    lines: [
      "I keep telling myself it's just my mess to clean up.",
      "But money doesn't leak through one clean break. It drains through a hundred cracks I can't watch at once. I can't be the only one.",
    ],
  },
  {
    id: "shashank-intro",
    character: "shashank",
    pose: "hips",
    lines: [
      "You're not. I'm Shashank, and I run revenue operations at a SaaS company.",
      "A few thousand business customers, subscriptions and invoices, crores through the gateway every month.",
    ],
  },
  {
    id: "shashank-pressure",
    character: "shashank",
    pose: "worried",
    lines: [
      "In every review my CEO asks the same thing: 'We missed the number again. Where is it going?'",
      "I open the dashboard. Revenue is down four percent. It won't tell me why, and 'I'll look into it' isn't an answer anymore.",
    ],
  },
  {
    id: "shashank-same",
    character: "shashank",
    pose: "confused",
    lines: [
      "So we pulled the data apart. It wasn't one big hole.",
      "It was Meena's four leaks: failed payments, dropped checkouts, broken renewals, and overdue invoices. They were simply running at a thousand times the volume.",
    ],
  },
  {
    id: "shashank-scale",
    character: "shashank",
    pose: "tired",
    lines: [
      "Six analysts. A wall of dashboards. They can tell me the number is down.",
      "None of them can tell me which payments to chase before the month closes. There are simply too many to reconcile by hand.",
    ],
  },
  {
    id: "resolution",
    character: "shashank",
    pose: "hopeful",
    lines: [
      "Whether it's a kitchen table or a boardroom, the leak is the same shape.",
      "It needs something that watches every transaction, works out why each one failed, and recovers what it can while staying inside clear limits.",
    ],
  },
];
