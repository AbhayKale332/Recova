# Recova — Repo State

An architecture map for an agent joining cold. Pair it with `Progress.md` (what is built and why)
and `Frontend/.Agents/Frontend-Vision.md` (the design brief + the full HTTP contract in its
appendices). `.Agents/Problem_Explaination/Skill.md` is the buildathon problem statement.

Last verified: 2026-09-04, at commit `e5e30af`.

```
Recova/
├── Backend/        FastAPI + SQLAlchemy + LangGraph, SQLite, uv
├── Frontend/       Next.js 16.3 App Router, React 19, Tailwind v4, zero runtime UI deps
└── .Agents/        Agent-facing docs (this file, the problem statement, Razorpay llms.txt pointer)
```

---

## Backend

Entry point is `application/server.py` (`uvicorn application.server:app`), **not** `main.py`, which
is vestigial. Every router mounts under `/api/v1`. Startup runs `init_db()` → `create_all`.

### Module layout

| Package | Owns |
| --- | --- |
| `endpoints/` | FastAPI routers. One file per surface: `health`, `webhook`, `metrics`, `stream`, `transaction`, `policy`, `admin`, `assistant`, `tracker`. |
| `entities/` | SQLAlchemy ORM models. |
| `contracts/` | Pydantic schemas — **currently unused**; routers hand-build dicts. |
| `operations/` | The services. Everything interesting lives here. |
| `workflow/` | The LangGraph DAG: `recovery_graph`, `workflow_nodes`, `workflow_state`, `workflow_factory`. |
| `integrations/` | Channel adapters (Twilio WhatsApp, Vapi voice, Razorpay actions) behind `routing_dispatcher`. |
| `configuration/` | `merchant_rules.json` — the default policy. |
| `test_suite/` | 33 pytest files, almost all offline. |

### The decision path — read this before touching recovery logic

`workflow/recovery_graph.py` builds a `StateGraph` over `RecoveryState`, with `OrchestratorDeps
{db, diagnosis, sandbox, dispatch}` injected so it is testable offline.

```
START → ingest → (disposition set? END : diagnose)
        diagnose → (playbook == SALARY_CYCLE_SEQUENCER ? wait : execute)
        wait → execute
        execute → (disposition set? END : reconcile) → END
```

Node by node (`workflow/workflow_nodes.py`):

1. **`ingest`** — sets `DIAGNOSING`; runs `screen_user_message()` on any customer message **before**
   the model sees it, so an opt-out or dispute cannot be overridden by the LLM.
   TERMINATE → `CANCELLED`; ESCALATE → escalation ticket + `ESCALATED`.
2. **`diagnose`** — calls the diagnosis engine, audits `{root_cause, recommended_playbook, confidence}`.
3. **`wait`** — `SALARY_CYCLE_SEQUENCER` only. Schedules to `helpers.next_salary_window()`, audits
   `RETRY_SCHEDULED`.
4. **`execute`** — resolves playbook → action via `_PLAYBOOK_ACTION`, checks the retry cap, builds a
   `ProposedAction`, and calls `sandbox.validate()`. **A rejected action is never dispatched** — it
   escalates to a human instead.
5. **`reconcile`** — only `payment.captured` / `payment.authorized` close a case as `RECOVERED`.
   Anything else logs `AWAITING_OUTCOME` and leaves it open.

Playbook → action table (`_PLAYBOOK_ACTION` in `workflow_nodes.py`):

| Playbook | Action | Channel |
| --- | --- | --- |
| `REROUTE_RAIL` | `GENERATE_PAYMENT_LINK` | `PAYMENT_LINK` |
| `PREAUTH_LINK` | `GENERATE_PAYMENT_LINK` | `PAYMENT_LINK` |
| `UPI_AUTOPAY_NUDGE` | `SEND_WHATSAPP` | `WHATSAPP` |
| `NEGOTIATION` | `OFFER_FEE_WAIVER` | `WHATSAPP` |
| `SALARY_CYCLE_SEQUENCER` | `RETRY_CHARGE` | — |
| `MANDATE_REFRESH` | `VOICE_CALL` | `VOICE` |
| `P2P_TRACKER` | `SEND_WHATSAPP` | `WHATSAPP` |

Class → default playbook (`diagnosis_service._DEFAULT_PLAYBOOK`): 1 → `REROUTE_RAIL`,
2 → `UPI_AUTOPAY_NUDGE`, 3 → `SALARY_CYCLE_SEQUENCER`, 4 → `P2P_TRACKER`.

### Where each stopping rule is actually enforced

Eight rules are enumerated in `constants.StoppingRule`. They are **not** all enforced in the same
place, and two were not enforced in the graph at all before step 3.

| Rule | Enforced in |
| --- | --- |
| `EXPLICIT_CANCEL` | `compliance_rules.screen_user_message()` → `ingest` node, `live_recovery` |
| `OPT_OUT` | same |
| `DISPUTE_FREEZE` | same (→ ESCALATE, not TERMINATE) |
| `RBI_MAX_RETRIES` | `compliance_rules.retry_cap_exceeded()` → `execute` node |
| `TRAI_QUIET_HOURS` | `compliance_rules.is_within_quiet_hours()` — **added to `execute` in step 3**; it *defers* (`WAITING`), it does not cancel |
| `VOICE_ATTEMPT_CAP` | `compliance_rules.voice_attempts_exhausted()` — **added to `execute` in step 3** |
| `NO_DOUBLE_CHARGE` | seeded outcome only (`batch_seed` `late_settlement`); no live gate |
| `CROSS_DEVICE_COMPLETION` | seeded outcome only (`batch_seed` `cross_device`); no live gate |

Precedence, and it must stay identical on both sides of the wire (`armedRule()` in
`Frontend/src/lib/bounds.ts`): **quiet hours → retry cap → voice cap.** Quiet hours bind first
because they gate every outbound channel.

Constants live in exactly two places and mirror each other: `operations/compliance_rules.py`
(`RBI_MAX_RETRIES=3`, `VOICE_ATTEMPT_CAP=2`, `QUIET_HOURS_START=20`, `QUIET_HOURS_END=9`) and
`Frontend/src/lib/bounds.ts`. Change one, change the other.

### The two model-free boundaries

These are load-bearing for the product's claim and must stay model-free:

- **`operations/policy_guard.py`** — `PolicySandbox.validate()` is the only gate every outbound
  action passes. Its `Decision.reason` strings are user-facing copy; surface them verbatim rather
  than rewriting them. The amount ceiling applies only to `_MONEY_MOVING_ACTIONS`
  (`GENERATE_PAYMENT_LINK`, `RETRY_CHARGE`, `OFFER_FEE_WAIVER`).
- **`operations/compliance_rules.py`** — deterministic phrase matching (EN + Hinglish) for
  cancel/opt-out/dispute, plus the numeric caps. Cancel and opt-out beat dispute, because ceasing
  contact is the safer instruction to honour.

The editable policy is a **single row** in `merchant_policy` (`entities/merchant_rules.py`). Only a
human operator writes it — the conversational layer has no path to it, which is what keeps the
guardrails un-negotiable by the model. A simulation must build a scenario-scoped `PolicySandbox`
instead of writing that row.

### LLM surfaces

OpenAI first, with Google Gemini as the provider fallback, through
`operations/model_router.py`. Both SDKs are imported lazily; a missing key, missing SDK, 429, or
transport error never takes down the API. Function calling is explicitly **disabled** — there are
no tool definitions. Five router tasks share three capability tiers and every routed response has
a `RouteDecision` explaining the choice. The three wired call sites retain deterministic offline
fallbacks, so the demo survives a dead network:

| Call site | Model tier | Fallback |
| --- | --- | --- |
| `operations/diagnosis_service.py` | `DIAGNOSE`: mini (`gpt-5.4-mini` / `gemini-3.6-flash`), JSON mode | `_DEFAULT_PLAYBOOK[class]`, `root_cause="UNDIAGNOSED"`, confidence 0.0 |
| `operations/message_drafter.py` | `DRAFT`: nano in batch (`gpt-5.4-nano` / `gemini-flash-lite-latest`), mini live (`gpt-5.4-mini` / `gemini-3.6-flash`), plain text | hardcoded EN/HI template |
| `operations/assistant_service.py` | `DECIDE`: full (`gpt-5.4` / `gemini-3-pro`), JSON mode | `_fallback_parse()`, pure keyword matching, EN + Hindi |

`operations/ai_client.py` keeps the legacy builders as thin compatibility wrappers over the
router. `LLM_PROVIDER` remains the manual provider override; `router_stakes_threshold_inr` is
₹25,000 by default, and stakes plus guardrail proximity can raise a route one tier at a time,
capped at `full`. LLM output is **advisory everywhere**: an unknown playbook string is coerced to
the class default, and the assistant re-resolves every transaction reference against the DB so the
model cannot name a case that does not exist. `openai_free_tier` is deliberately explicit because
the free daily quota requires opting into sharing that traffic with OpenAI.

Batch paths pass `generate=None` to `draft_message` deliberately — template drafting, no live model.
N cases × one model call each is the dominant cost and latency and will hit rate limits mid-demo.

### Data model

A **case** is one row in `transaction_states`. Columns carry the hard facts (`failure_class` 1–4 with
a CHECK constraint, `current_state`, `retry_count`/`max_retries`, `amount_minor` in **paise**,
`customer_contact` **Fernet-encrypted** via `protection.EncryptedString`). Everything demo-shaped
lives in `metadata_json`:

`customer_name` · `archetype` (`CLASS_1..4` | `HEALTHY` | `NON_RECOVERABLE`) · `class_label` ·
`is_at_risk` · `confidence` · `event_type` · `error_code` · `ai_tag` · `unworked` · `run_outcome` ·
`p2p_date` · `payment_link_id` · tracker fields (`plan`, `next_debit_date`, `salary_day`,
`invoice_no`, `due_date`, `terms`) · `simulation_run_id` *(added in step 3)*.

| Table | Model | Note |
| --- | --- | --- |
| `transaction_states` | `entities/transaction_record.py` | the case |
| `audit_trails` | `entities/audit_record.py` | **append-only** — `before_update`/`before_delete` listeners raise |
| `escalation_queue` | `entities/escalation_queue.py` | `rule` is nullable |
| `merchant_policy` | `entities/merchant_rules.py` | single row, id=1 |
| `messages` | `entities/message_record.py` | WhatsApp thread, ordered by `seq` |
| `call_sessions` / `call_turns` | `entities/call_session.py` | voice transcript |
| `processed_events` | `entities/handled_event.py` | webhook idempotency |
| `saved_scenarios` | `entities/saved_scenario.py` | operator-authored simulator scenarios, upserted by slug |

`operations/audit_service.py::record_audit()` is the **single writer** to the audit trail. Reasoning
is captured as structured payload, not prose. No Alembic — `create_all` only creates missing tables.

### Metrics

`operations/reconciliation_service.py::compute_metrics()` derives everything on read; nothing is
stored. `grrr` = recovered ÷ at-risk in paise. Rows with `metadata_json.is_at_risk == false`
(the `HEALTHY` archetype) are excluded from the denominator, and rows carrying a `simulation_run_id`
are excluded by default so what-if runs never contaminate the real batch.

### Demo data

`operations/batch_seed.py` (711 lines) is the demo engine, and seeded at-risk cases are pushed
through the **real LangGraph**, so their audit trails are genuine. `class_profile()` is the shared
per-class vocabulary (label, telemetry, root cause, confidence) — the live runner reads it too, so a
seeded case and a live case never tell two different stories. Reuse it rather than adding a copy.

`operations/live_recovery.py` drives the single-case SSE run. The **customer's side is scripted**
(`metadata_json.run_outcome`); the engine's decisions are real code. Say so if you describe it.

---

## Frontend

Next.js 16.3 App Router, React 19.2, TypeScript strict, Tailwind v4 (CSS-first, no config file).
**Runtime dependencies: `next`, `react`, `react-dom`. That is all** — no shadcn, no Radix, no clsx,
no icon library. Keep it that way; `three`, `@react-three/*` and `postprocessing` are forbidden by
the vision doc.

Read `node_modules/next/dist/docs/` before writing code — Next 16 conventions differ from most
training data, and both layouts already use the typed-routes `LayoutProps<"/console">` API.
`reactStrictMode` stays on.

```
src/app/          layout · page (landing placeholder) · globals.css (the whole design system)
                  console/{layout,page} · console/guardrails · console/audit  (last two are stubs)
src/components/   Money · StatusChip · ClassChip · Sheet · States · Toast
                  console/{ConsoleContext,ConsoleShell,ConsoleScreen,HeroMetrics,
                           SummarySentence,FunnelBar,LocaleToggle}
                  sim/{ScenarioForm,FormPrimitives,CaseBuilder,RunProgress,ProjectionPanel,ProbabilityBreakdown,
                      CaseFilters,CaseTable,CasePanel,BoundsGauge,DecisionTrace}
src/lib/          api · types · format · status · bounds · summary · failure-classes · simulation · i18n/
src/hooks/        useApi · useRecoveryRun · useSimulationRun
```

| Module | Owns — do not duplicate |
| --- | --- |
| `lib/api.ts` | The typed client for **every** endpoint in Appendix A, including the simulation catalog and saved-scenario mutations. `ApiError`/`NetworkError` carry status/method/path. `TransactionQuery` is the case-list filter shape. |
| `lib/types.ts` | Wire types, verbatim from Appendix B, plus runtime const arrays for every backend enum. **The contract — do not "improve" these shapes.** |
| `lib/format.ts` | The only place money, dates, durations and ratios are formatted. `parseApiDate` exists because the backend serializes UTC without an offset. |
| `lib/bounds.ts` | The bounds-gauge math: budgets, channels remaining, armed rule, next action time. Mirrors `compliance_rules.py`. |
| `lib/status.ts` | Lifecycle → label + tone, and the tone → class maps. |
| `lib/i18n/` | `en.ts` is the source of truth; `hi.ts` is typed as `Dictionary`, so a missing Hindi key **fails the build**. |
| `lib/simulation.ts` | Scenario wire types, authored-case/share-link helpers, defaults, and simulator stream types. |
| `hooks/useApi.ts` | Abortable fetch that discards stale responses, plus `useMutation` and `describeError`. |
| `hooks/useRecoveryRun.ts` | `EventSource` wrapper for the single-case SSE run. Written; not yet mounted. |

Design tokens are CSS custom properties in `src/app/globals.css`, re-exported through
`@theme inline`. One light theme, single teal accent, status colours green/amber/blue/slate/rose.
Components reference them as `bg-[var(--surface)]`.

**Unit discipline:** `amount_inr` is rupees; `max_intervention_amount_minor` is paise. Convert once,
at the boundary, in `format.ts`.

Dictionary keys for the case list (`filters.*`, `table.*`, `batch.*`) are **already written and
unused** — use them rather than adding new ones.

---

## Gotchas

- `Backend/main.py` is dead code.
- `POST /admin/seed` calls `_clear(db)` — it wipes every table, with no auth, bypassing the
  append-only audit guards via bulk delete.
- `CallTurn.seq` is set to `at_offset_sec` in three places (`transaction_api`, `live_recovery`,
  `batch_seed`).
- `list_transactions` loads all matching rows before filtering `archetype`/`q` in Python.
- `failure_class` as a query param implicitly drops `HEALTHY` rows.
- `EscalationQueue.rule` is nullable, which is why stopping rules are counted from audit payloads
  *and* ticket rules separately.
- `Frontend-Vision.md` Appendix A omits `GET /stream/demo/{failure_class}` and `POST /assistant/tts`.
