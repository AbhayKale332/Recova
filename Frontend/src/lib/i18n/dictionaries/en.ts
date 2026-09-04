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

  /**
   * The simulator. The console no longer reports a number that was already in
   * the database — the user describes a book of failures and the engine works
   * it, so every figure is the output of a run they triggered.
   */
  sim: {
    title: "Simulate a recovery run",
    subtitle:
      "Describe a book of at-risk payments. Recova works every case through the real engine and shows what it recovered, and where it refused to go.",
    presets: "Start from a sample",
    presetsHint: "One click fills in every field below.",
    custom: "Custom",
    run: "Run batch",
    running: "Running…",
    stop: "Stop",
    again: "Run again",
    reset: "Clear run",
    idleTitle: "Nothing has been run yet",
    idleBody: "Pick a sample scenario or set the inputs, then run the batch.",

    groupCases: "Case shape",
    groupEdges: "Edge cases",
    groupPolicy: "Merchant policy",

    groupCustom: "Authored cases",
    scenarioName: "Scenario name",
    scenarioDescription: "Description",
    amountBounds: "Generated amount bounds",
    amountBoundsHint: "Optional rupee limits for generated cases; authored amounts stay exact.",
    amountMin: "Minimum",
    amountMax: "Maximum",
    authoredHint: "Write the cases you want to inspect. Replies are screened by the real compliance rules.",
    addCase: "Add case",
    noAuthoredCases: "No authored cases yet. Generated cases will still use the distribution above.",
    customerName: "Customer",
    amountInr: "Amount (₹)",
    failureClass: "Problem",
    replyText: "Customer reply",
    replyHint: "Up to 280 characters; try a real Hinglish opt-out.",
    replyPlaceholder: "e.g. band karo, stop contacting me",
    actions: "Actions",
    duplicate: "Duplicate",
    delete: "Delete",
    liveDiagnosis: "Use live Gemini diagnosis",
    liveDiagnosisHint: "Available for up to 25 total cases. The fallback remains deterministic if the provider is unavailable.",
    saveScenario: "Save scenario",
    copyLink: "Copy link",
    linkCopied: "Link copied",
    shareHint: "Share this exact scenario without saving it.",
    savedScenarios: "Saved scenarios",
    savedTitle: "Scenario saved",
    saveFailed: "Couldn’t save scenario",
    deletedTitle: "Scenario deleted",
    deleteFailed: "Couldn’t delete scenario",

    count: "Cases",
    countHint: "How many at-risk payments are in this book.",
    classMix: "Problem mix",
    classMixHint: "Relative weights. A class with no weight is left out.",
    amountScale: "Ticket size",
    amountScaleHint: "Multiplier on each problem's typical amount.",
    amountSpread: "Spread",

    replyMix: "Customer replies",
    replyMixHint: "What customers say back. This is what makes the guardrails fire.",
    reply_cooperative: "Cooperative",
    reply_opt_out: "Opts out",
    reply_dispute: "Disputes",
    reply_p2p: "Promises a date",
    reply_silent: "No reply",

    clock: "Time of day (IST)",
    clockHint: "TRAI forbids contact 20:00–09:00. Set an evening hour to watch it bind.",
    clockNow: "Use the real clock",
    quietArmed: "Quiet hours armed — outbound contact will be deferred to 09:00 IST.",
    retriesUsed: "Retries already used",
    retriesHint: "RBI permits 3 auto-debit retries per cycle.",
    voiceUsed: "Voice calls already made",
    voiceHint: "At most 2 in a rolling 72 hours.",
    lateSettlement: "Settled late",
    lateSettlementHint: "Triggers NO_DOUBLE_CHARGE.",
    crossDevice: "Paid elsewhere",
    crossDeviceHint: "Triggers CROSS_DEVICE_COMPLETION.",
    daysOverdue: "Invoice age",
    days: "days",

    maxDiscount: "Max discount",
    maxDiscountHint: "An action above this cap is handed to a human instead of sent.",
    allowedChannels: "Allowed channels",
    policyDefault: "Merchant default",

    measured: "Recovered",
    measuredHint: "Measured — the engine drove these cases to settlement.",
    projected: "Projected",
    projectedHint:
      "Modelled — expected eventual recovery across the book, with a 95% band. Not money that has moved.",
    deferred: "Deferred",
    deferredHint: "Held by a stopping rule that defers rather than stops. Neither recovered nor lost.",
    notAdditive: "These three figures overlap — they are not meant to be added.",
    band: "{low} to {high}",

    throughput: "Throughput",
    perSecond: "{rate}/s",
    workers: "{busy} of {total} workers",
    latency: "p50 {p50} · p95 {p95}",
    elapsed: "{seconds}s elapsed",
    doneOf: "{done} of {total}",
    concurrency: "Concurrency",

    casesFromRun: "Cases from this run",
    whyTitle: "Why",
    whyEmpty: "No decisions recorded for this case.",
    boundsTitle: "Bounds",
    retriesBudget: "Auto-debit retries",
    voiceBudget: "Voice calls",
    channelsRemaining: "Channels left",
    channelsNone: "None left",
    armed: "Armed: {rule}",
    fired: "Fired: {rule}",
    nextAction: "Next action {when}",
    noneArmed: "Nothing armed",

    probabilityTitle: "Likelihood this case pays",
    baseRate: "Base rate for this playbook",
    adjustments: "Adjustments",
    contribution: "{delta} pp",
    modelNote:
      "A starting rate per problem and playbook, adjusted for this case, sharpened by outcomes already observed.",
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
