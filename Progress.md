# Recova — Build Progress

Living status file. Update it at the end of every slice. If you are an agent picking this
repo up cold, read this file and then `.Agents/Repo-State.md`.

**What Recova is:** an AI revenue-recovery agent for Razorpay's buildathon (Track 03). It detects
revenue at risk, diagnoses why, picks a *bounded* intervention, runs it, and stops when policy says
stop. The product spec is `.Agents/Problem_Explaination/Skill.md`; the frontend brief plus the full
HTTP contract is `Frontend/.Agents/Frontend-Vision.md`.

---

## Build order

The frontend is built in seven steps. This ordering exists only here — it came from a build prompt
that was never committed, so treat this list as its canonical home.

| Step | Slice | Status |
| --- | --- | --- |
| 1 | Foundation: `lib/` + `hooks/` + UI primitives | **done** (`64d817f`) |
| 2 | `/console` zone 1 — batch evidence | **done** (`64d817f`), being reworked in step 3 |
| 3 | `/console` zones 2–3 — case list + case detail + bounds gauge, **now simulation-led** | **in progress** |
| 4 | SSE live-run feed inside the case panel | not started |
| 5 | `/console/guardrails` — stopping rules, escalation queue, policy editor + sandbox | stub route exists |
| 6 | `/console/audit` — audit trail grouped by node, filterable, exportable | stub route exists |
| 7 | `/` landing page — built last, least load-bearing | placeholder exists |

Four routes total, by design: `/`, `/console`, `/console/guardrails`, `/console/audit`. Failure class
is a **filter** on `/console`, not four routes.

### Zone breakdown of `/console`
- **Zone 1** — batch evidence: summary sentence, recovered money as the hero, GRRR/TTR/in-flight/lost,
  six-segment funnel bar. Built; step 3 repoints it from `GET /metrics` to simulation-run output.
- **Zone 2** — case list: filters (`q`, `failure_class`, `status`, `archetype`), desktop table,
  mobile stacked cards.
- **Zone 3** — case detail panel (`?case=<id>`, right sheet on desktop / bottom sheet on mobile):
  payment facts → diagnosis → **bounds gauge** → decision trace → conversation → audit timeline.

---

## Current slice — step 3

Plan: `~/.claude/plans/the-zone-1-is-streamed-raven.md`.

Step 3 grew beyond the original zone 2–3 scope. The console no longer *reports* money that was
already sitting in `recovery_engine.db`; it *produces* it. The user supplies a scenario, presses Run,
and N cases stream through the real recovery engine concurrently.

- [x] Part 0 — `Progress.md` + `.Agents/Repo-State.md`
- [x] Part 1 — backend: quiet hours + voice cap enforced in the graph; WAL SQLite; simulation rows
      scoped out of the real metrics
- [x] Part 2 — backend: `application/simulation/` + `POST /api/v1/simulate/batch` (SSE)
- [ ] Part 3 — frontend: scenario form + sample presets, run progress, projection panel, case list,
      case detail panel, bounds gauge, decision trace, probability breakdown

### Backend, as shipped

**Guardrails.** `workflow_nodes.execute` now runs the quiet-hours and voice-cap gates it was
missing, in the precedence `armedRule()` uses on the client: quiet hours → retry cap → voice cap.
Quiet hours **defer** (`WAITING` + a `RETRY_SCHEDULED` audit naming the resume time); they never
cancel. A channel-less auto-debit retry is exempt, because TRAI governs outbound *contact*.

**The clock is injected.** `OrchestratorDeps.clock` follows the file's own "injected rather than
imported so the orchestrator is testable offline" rule. Tests and the seeder pin a fixed
mid-morning IST clock — without that, the suite would have started failing at 20:00 and
`POST /admin/seed` would have produced a different batch depending on the hour.

**Concurrency.** `persistence.py` puts SQLite in WAL with a busy timeout. Unrelated bonus: the
test suite went from 228s to 37s.

**Isolation.** Simulated cases carry `metadata_json.simulation_run_id`. `compute_metrics` and
`list_transactions` exclude them by default and select only that run when given one, so a what-if
never moves the merchant's real numbers. Verified: four full runs left `/metrics` byte-identical.

**`application/simulation/`** — `scenario.py` (inputs, deterministic expansion, 4 one-click
presets), `probability.py` (Beta priors + logistic adjustment, closed form, no new deps),
`runner.py` (asyncio pool, one Session per worker thread, coalesced progress), `trace.py`
(audit rows → readable decisions), `store.py` (list/replay/delete/prune runs).

Endpoints: `POST /simulate/batch` (SSE), `GET /simulate/scenarios`, `GET /simulate/runs`,
`GET|DELETE /simulate/runs/{run_id}`, `POST /simulate/prune`.

Measured: 200 cases in ~3.1s, ~65 cases/sec, p95 ~280ms, 8 workers.

**LLM tiers.** `build_strong_generate()` in `ai_client.py` owns provider selection; the assistant
moved onto it. `LLM_PROVIDER=openai` switches the strong tier only, with a lazy import so the
OpenAI SDK stays optional. Diagnosis and drafting are unchanged.

Tests: 251 passing (was 218).

---

## Decisions log

Newest first. Record *why*, not just what.

### 2026-09-04 — A cooperative reply must not guarantee payment
First cut had the customer's reply decide settlement, which produced a 99.2% GRRR — the recovered
figure was something the scenario *asserted*, which is the pre-computed-number problem moved one
layer down. Now settlement is drawn against the model's own probability, seeded deterministically
from the scenario so two runs stay comparable. GRRR now lands between 4.8% and 29% depending on
the scenario, and the guardrails are what move it.

### 2026-09-04 — A spent bound zeroes the projection, it does not merely penalise it
The retry-exhausted scenario projected ₹68k against ₹8.5k measured, because the model applied a
per-retry penalty while the engine was refusing to work those cases at all. `CaseFeatures.blocked_by`
now returns p=0 when a cap is already spent. The projection dropped to ₹15k and landed inside its
own band. A projection must never forecast money from cases the engine is about to stop itself on.

### 2026-09-04 — Deferred money is reported separately
Quiet hours put cases in `WAITING`: neither recovered nor lost. The `complete` event carries
`deferred_inr` so the screen can explain the gap between measured and projected instead of leaving
two numbers looking like a contradiction. The three figures are not additive and must not be summed.

### 2026-09-04 — Backend is the only source of a decision's "why"
The simulator drives the real LangGraph engine through a new endpoint rather than reimplementing the
rules in TypeScript. A second implementation in the client would drift from the engine, and the
whole claim of the product is that the reason shown on screen is the code that would run in
production. Cost: the graph's nodes commit to a DB session, so the worker pool needs one session per
thread and SQLite needs WAL.

### 2026-09-04 — The console leads with a simulation, not a stored number
A recovered figure that was already in the database is indistinguishable from a hardcoded one, and
`Frontend-Vision.md` §5 calls a stale number in a live demo "a credibility loss you don't recover
from." Inputs → run → measured outcome is falsifiable in a way a dashboard read is not. Sample
scenarios load in one click so the demo never stalls on data entry.

### 2026-09-04 — The batch is the scalability story
`recover-batch` was a sequential loop capped at 50 cases. It becomes an asyncio worker pool with
measured throughput (cases/sec, p50/p95, workers busy) streamed over SSE. The concurrency is real
and the numbers are measured, not asserted. Note the queue is in-process — do not imply distributed.

### 2026-09-04 — Outcome probabilities: Bayesian priors, not a trained model
Training on `batch_seed.py` output would only re-learn the seeder's own constants, which would be
circular. Instead: Beta-Bernoulli posteriors per (failure_class × playbook × channel) with
documented hand-set priors, plus a small logistic adjustment for amount / IST hour / retries used /
days overdue. Closed form, pure stdlib, no new dependencies. It yields per-feature contributions
(the explanation) and a credible interval, and it sharpens from real completed runs.
Projected money is always labelled as modelled, never as measured.

### 2026-09-04 — Stay on Gemini; hybrid is one extra tier, not a router
`policy_guard.py` and `compliance_rules.py` are deliberately model-free, so the LLM is advisory
everywhere and provider choice affects phrasing, never whether money moves. Batch drafting dominates
token cost, where Flash-lite wins on price and latency. Three tiers, one provider abstraction:
drafting → `gemini-flash-lite`, diagnosis → `gemini-3.6-flash`, assistant → a `strong` tier
(`gemini-3-pro`, or OpenAI via env). The assistant is the only call site doing strict structured
extraction over a large injected catalog, so it is the only one where model quality changes the
outcome. OpenAI stays a lazy import — an optional dependency, not a required one.

---

## Known issues / debt

- **`Backend/.env` is committed with live credentials** (Razorpay, Gemini, Twilio, encryption key).
  Rotate every key and add it to `.gitignore`. Not addressed in step 3.
- **No migrations.** `init_db()` runs `Base.metadata.create_all`, which only creates *missing*
  tables — an altered column will not apply. Alembic should own the schema once it stabilises.
- **`POST /admin/seed` wipes every table** with no auth, bypassing the append-only audit guards via
  bulk delete.
- **`contracts/*.py` are unused.** Every router hand-builds dicts, so FastAPI's OpenAPI schema for
  most endpoints is just `dict`.
- **`list_transactions` filters `archetype` and `q` in Python** after loading all matching rows.
  Fine at ~200 rows, O(n) beyond.
- **Appendix A drift** in `Frontend-Vision.md`: it omits `GET /stream/demo/{failure_class}` and
  `POST /assistant/tts`, and says `backend/` where the directory is `Backend/`.


## Part A — fully custom simulation scenarios

Implemented 2026-09-04. The simulator now accepts authored cases alongside generated cases. Authored
customer replies flow through the existing `screen_user_message()` ingest gate, so a typed Hinglish
opt-out is a real `OPT_OUT` decision. Expansion remains deterministic and rupees are converted to
paise only when a planned case becomes a transaction row.

- [x] `CustomCase`, explicit generated amount bounds, canned reply text overrides, authored/generated
      expansion, stable ordering, scenario-scoped playbook overrides, and the 25-case live-diagnosis cap.
- [x] `saved_scenarios` persistence with POST upsert, GET catalog, and DELETE.
- [x] Responsive authored-case builder, versioned base64url share links, saved scenario controls,
      and matching English/Hindi copy.
- [x] Regression coverage for free-text opt-out, deterministic expansion, amount bounds, live diagnosis
      cap, and saved-scenario round trip.

Part B (voice), Part C (`main_vision.md`), and Part D cleanup remain intentionally untouched.
