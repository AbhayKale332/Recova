/**
 * The English dictionary is the source of truth for the key set.
 * `hi.ts` is typed as `Dictionary`, so a missing Hindi key is a build error.
 */
export const en = {
  locale: { en: "English", hi: "हिन्दी", switchLabel: "Language" },

  brand: {
    name: "Recova",
    tagline: "Revenue recovery that knows when to stop.",
  },

  nav: {
    console: "Console",
    guardrails: "Guardrails",
    audit: "Audit",
    landing: "Overview",
    skipToContent: "Skip to content",
    primary: "Primary",
  },

  actions: {
    refresh: "Refresh",
    refreshing: "Refreshing…",
    reseed: "Reseed demo",
    reseeding: "Reseeding…",
    seed: "Seed the demo batch",
    seeding: "Seeding…",
    retry: "Try again",
    close: "Close",
    cancel: "Cancel",
    clearFilters: "Clear filters",
    runBatch: "Run batch",
    running: "Running…",
    confirm: "Confirm",
    export: "Export CSV",
    copy: "Copy",
    copied: "Copied",
  },

  states: {
    loadingTitle: "Loading",
    loadingBody: "Fetching from the recovery engine.",
    emptyTitle: "Nothing here yet",
    emptyBody: "No records match.",
    errorTitle: "Couldn't load this",
    unseededTitle: "The database is empty",
    unseededBody:
      "Recova has no cases to work yet. Seed the demo batch to populate transactions, audit trail and metrics.",
    offlineTitle: "Backend unreachable",
    offlineBody:
      "Nothing answered at the API base URL. Start the FastAPI server, then try again.",
  },

  console: {
    title: "Recovery console",
    batchEvidence: "Batch evidence",
    heroLabel: "Recovered",
    ofAtRisk: "of {amount} at risk",
    grrr: "Gross Revenue Recovery Rate",
    grrrShort: "GRRR",
    avgTtr: "Average time to recovery",
    avgTtrShort: "Avg. TTR",
    inFlight: "In flight",
    inFlightHint: "Being worked right now",
    lost: "Lost",
    lostHint: "Retries exhausted",
    atRisk: "At risk",
    funnelTitle: "What happened to the {count} cases at risk",
    funnelHint: "Select a segment to filter the case list.",
    funnelSelected: "Filtered to {label}. Select again to clear.",
    caseList: "Cases",
    caseCount: "{shown} of {total} cases",
    lastUpdated: "Updated {when}",
  },

  /**
   * The summary sentence — the highest-value string in the product.
   * Assembled in lib/summary.ts; every number comes from /metrics.
   */
  summary: {
    sentence:
      "Recova recovered {recovered} of {atRisk} at risk across {cases} cases — {escalated} escalated to a human, {stopped} stopped by policy.",
    sentenceNoCases: "Recova has no cases at risk yet. Seed the demo batch to see a recovery run.",
    caseWord: "case",
    caseWordPlural: "cases",
  },

  funnel: {
    at_risk: "At risk",
    intervened: "Intervened",
    recovered: "Recovered",
    escalated: "With a human",
    cancelled: "Stopped by policy",
    failed: "Lost",
  },

  status: {
    PENDING: "Pending",
    DIAGNOSING: "Diagnosing",
    WAITING: "Waiting",
    INTERVENING: "Intervening",
    RECOVERED: "Recovered",
    ESCALATED: "With a human",
    CANCELLED: "Stopped",
    FAILED: "Lost",
  },

  statusMeaning: {
    PENDING: "Detected, not yet worked",
    DIAGNOSING: "Working out the root cause",
    WAITING: "Deliberately paused",
    INTERVENING: "Outreach in progress",
    RECOVERED: "Money captured",
    ESCALATED: "Compliant handoff to a person",
    CANCELLED: "A stopping rule halted it — the guardrails worked",
    FAILED: "Retries exhausted",
  },

  filters: {
    label: "Filters",
    search: "Search",
    searchPlaceholder: "Customer or transaction id",
    failureClass: "Problem",
    status: "Status",
    archetype: "Row type",
    all: "All",
    archetypeCase: "Recovery cases",
    archetypeHealthy: "Healthy (context only)",
    archetypeNonRecoverable: "Not recoverable",
    active: "{count} filter active",
    activePlural: "{count} filters active",
  },

  table: {
    customer: "Customer",
    amount: "Amount",
    problem: "Problem",
    status: "Status",
    playbook: "Playbook",
    confidence: "Confidence",
    ttr: "TTR",
    caseId: "Case",
    noPlaybook: "Not yet chosen",
    notRecovered: "—",
  },

  batch: {
    confirmTitle: "Run recovery on {count} cases?",
    confirmBody:
      "Recova will work {count} cases worth {amount}. Each runs the real recovery loop — diagnosis, outreach, stopping rules.",
    skipped: "{count} of the filtered cases are already closed and will be skipped.",
    noneRunnable: "None of the filtered cases can be run — they are all already closed.",
    capped: "The backend accepts 50 cases per batch; the first 50 will run.",
    localeNote: "Outreach will be drafted in {language}.",
    successTitle: "Batch finished",
    successBody: "{recovered} of {total} recovered.",
    failureTitle: "Batch failed",
  },

  toast: { dismiss: "Dismiss", notifications: "Notifications" },

  errors: {
    withStatus: "{method} {path} returned {status}.",
    network: "Couldn't reach the backend at {base}.",
    aborted: "Request cancelled.",
    unknown: "Something failed and the backend gave no reason.",
    seedFailed: "Couldn't seed the demo batch.",
    seedOk: "Seeded {count} transactions.",
  },

  landing: { comingSoon: "Overview" },
  guardrails: { title: "Guardrails" },
  audit: { title: "Audit trail" },
};

/**
 * No `as const` on purpose: every leaf widens to `string`, so `hi.ts` may hold
 * different text but not a different key set. A missing Hindi key is a build error.
 */
export type Dictionary = typeof en;
export type Locale = "en" | "hi";
