export type FailureClassId = 1 | 2 | 3 | 4;

export type StoryFailureClass = {
  tag: string;
  title: string;
  problem: string;
  rescue: string;
};

/**
 * Plain-language copy for the four leaks in Meena's story. This is the
 * marketing/story surface only — the console's own failure-class data lives in
 * `@/lib/failure-classes` and is keyed differently.
 */
const STORY_CLASSES: Record<FailureClassId, StoryFailureClass> = {
  1: {
    tag: "Problem 01",
    title: "A card that keeps failing",
    problem:
      "A card fails, then fails again — and there's no way to tell if it's fraud, a typo, or the bank timing out.",
    rescue:
      "The agent works out why the card was declined, rules out anything risky, and tries again only when the reason says trying again will actually work.",
  },
  2: {
    tag: "Problem 02",
    title: "A full cart, left behind",
    problem:
      "A ready-to-buy cart closes quietly. No error, no message — just a sale that never happened.",
    rescue:
      "One gentle, well-timed reminder goes out — in the customer's own language, sent when they're actually free to finish paying.",
  },
  3: {
    tag: "Problem 03",
    title: "A renewal that slipped",
    problem:
      "An auto-renewing plan fails without a sound. The customer didn't mean to leave — they just never noticed.",
    rescue:
      "The next attempt is lined up with the customer's actual payday instead of a fixed date, and it never keeps knocking forever.",
  },
  4: {
    tag: "Problem 04",
    title: "An invoice nobody chased",
    problem:
      "An unpaid invoice drifts past its date while everyone quietly assumes someone else is following up.",
    rescue:
      "A polite sequence of reminders runs on its own — and passes the case to a person the moment it stops being a job for software.",
  },
};

export function getFailureClass(id: FailureClassId): StoryFailureClass {
  return STORY_CLASSES[id];
}
