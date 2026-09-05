# Recova — 5-Minute Video Script

**Format:** screen recording + voiceover. Target ~750 spoken words at ~150 wpm.
**One line to remember:** *Any system can send more messages. Ours knows when to stop.*

Legend — **[V]** = what's on screen · **[VO]** = what you say · timings are cumulative.

---

## 0:00 – 0:18 · Cold open (the hook)

**[V]** Black screen. One number types itself out, large: `₹0`. Then it climbs — `₹41,200 recovered` — and freezes.

**[VO]**
> This number isn't from a database. It isn't hardcoded.
> It's what happened when I pressed Run, thirty seconds ago, live.
> This is Recova.

**[V]** Cut to logo: *Recova — revenue recovery that knows when to stop.*

---

## 0:18 – 0:50 · The problem

**[V]** Split screen. Left: Meena's photo, a home-décor label in Pune. Right: Shashank, head of revenue at a SaaS company doing crores a month.

**[VO]**
> Meena lost ₹4,200 of cushion covers — someone filled a cart and closed the tab. No error. No complaint. Just gone.
> Shashank has six analysts and a wall of dashboards, and none of them can tell him which payments to chase before the month closes.
> Same leak, different scale: failed payments, dropped checkouts, broken renewals, overdue invoices.

**[V]** Four short labels stack up: *degraded payment · abandoned checkout · failed auto-debit · overdue invoice.*

**[VO]**
> Dashboards are great at telling you money is at risk. They do nothing to get it back.

---

## 0:50 – 1:15 · The idea

**[V]** The Track 03 flow animates left to right: **Detect → Diagnose → Intervene → Bound → Escalate → Stop → Audit → Measure.**

**[VO]**
> Recova runs the *whole* chain. It detects revenue at risk, works out *why* each payment failed, runs a bounded recovery — one nudge, one link, one call — and it stops the moment policy says stop.
> Then it shows you the receipt.
> The headline outcome is money *recovered*. Not risk *identified*.

---

## 1:15 – 3:15 · The demo

### 1:15 – 1:55 · The console produces the money

**[V]** `/console`. Pick a sample scenario — a mix of the four failure classes, a few edge cases. Hit **Run**.

**[VO]**
> I give it a scenario. Two hundred at-risk cases. Press Run —
> and every one of them streams through the real recovery engine, concurrently.

**[V]** Progress bar fills fast. Counters tick: throughput ~65 cases/sec, p95 latency, workers busy. Cases land in the list with tags: *recovered · escalated · stopped · deferred.*

**[VO]**
> Two hundred cases in about three seconds. That number in the corner is the money the engine actually drove to "recovered" — and if I change the inputs, it moves. You can't fake that in a live demo.

### 1:55 – 2:20 · Three numbers, never summed

**[V]** Projection panel: **Recovered** (measured, green) · **Projected** with a 95% band (blue) · **Deferred** (amber).

**[VO]**
> Three numbers, and we never add them up. Recovered is measured. Projected is modelled, with an honest confidence band. Deferred is cases we paused for quiet hours — not won, not lost.
> Most demos hide that gap. We explain it.

### 2:20 – 2:50 · The bounds gauge — restraint is the feature

**[V]** Open one case. The **bounds gauge**: retries 2 of 3 · voice attempts 1 of 2 · discount near cap. Then a case that *stopped* — audit row reads `RBI_MAX_RETRIES`.

**[VO]**
> Here's the part I care about. Every case shows how close it is to its limits.
> This one hit three retries — an RBI cap, not a preference — so the engine stopped and logged which rule stopped it.
> Escalating to a human is a *success* of the guardrails, not a failure.

### 2:50 – 3:15 · The live theatre

**[V]** `/live`. A WhatsApp phone mockup. A recovery message goes out. Type a customer reply in Hinglish: *"band karo, mat bhejo."*

**[VO]**
> And it's interactive. Customer replies "stop sending" — in Hinglish —
> and before the model ever sees that message, a deterministic screen catches the opt-out and shuts the case down.

**[V]** Red card: *🛑 OPT_OUT → CANCELLED.* Audit row appears.

**[VO]**
> A hallucinating model can't talk its way past that.

---

## 3:15 – 4:15 · Under the hood

**[V]** Architecture diagram. Highlight two files in a lock icon: `policy_guard.py`, `compliance_rules.py`.

**[VO]**
> The whole product rests on one boundary. The language model is advisory — everywhere. It suggests wording and a root cause.
> Two files — the policy sandbox and the compliance rules — are deterministic, model-free, and mirrored line-for-line on the frontend. They decide whether money moves. Nothing else does.

**[V]** Router chip on a case: *"₹48,000 at stake → raised to full tier · OpenAI unavailable → Gemini."*

**[VO]**
> There's a cost-aware router — high-stakes cases get the strong model, routine drafting gets the cheap one, and it tells you why in plain language.

**[V]** Quick flash: Razorpay MCP diagram — closed 7-tool set, four gates, *model never sees the tool list.*

**[VO]**
> Payments go through a private Razorpay MCP server — but the model never sees that tool surface. It proposes from a closed set, four gates run in order, and only then does a payment dispatch.

**[V]** Audit view grouped by node, export to CSV. Append-only badge.

**[VO]**
> And every step is written to an append-only audit trail. Try to edit history and the code raises an exception.

---

## 4:15 – 5:00 · Close

**[V]** Back to `/console`. Re-run with a stricter policy. The recovered number comes out lower. Zoom on it.

**[VO]**
> Tighten the policy, run it again — the recovered number drops, and you can see exactly which guardrail moved it.
> That's the honest version of this problem. Recovery rate lands between five and twenty-nine percent depending on the scenario, and the limits are what drive it.

**[V]** Full-screen text: **detect · diagnose · intervene · bound · escalate · stop · audit · measure.**

**[VO]**
> Recova. It detects the leak, recovers what it can, and knows when to walk away.
> Any system can send more messages. Ours knows when to stop.

**[V]** End card: repo URL · *Razorpay Buildathon — Track 03.*

---

## Shot list (record these first)

| # | Screen | Action to capture |
|---|--------|-------------------|
| 1 | `/console` | Pick scenario → Run → progress counters → case list fills |
| 2 | `/console` | Projection panel: recovered / projected+band / deferred |
| 3 | `/console` case sheet | Bounds gauge; a `RBI_MAX_RETRIES` stop with its audit row |
| 4 | `/live` | Send message → type Hinglish opt-out → red `OPT_OUT → CANCELLED` card |
| 5 | `/console/guardrails` | Stopping-rule counts + policy editor + sandbox |
| 6 | `/console/audit` | Trail grouped by node → CSV export |
| 7 | `/console` | Re-run with stricter policy → lower recovered number |
| 8 | README diagrams | Architecture; model-free boundary; Razorpay MCP gates |

## Delivery notes
- Pace fast. Cut every "so" and "basically". Let the counters breathe for one beat, then talk over them.
- The three payoff lines, hit them hard: *"You can't fake that in a live demo." · "Escalating is a success, not a failure." · "Ours knows when to stop."*
- No music under the voiceover in the demo section — keep the tick of the counters.
