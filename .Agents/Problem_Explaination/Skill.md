# Skill: AI Revenue Recovery

## Track

**Track 03 — AI Revenue Recovery**

## Problem Statement

Build an agent that detects revenue at risk, determines the appropriate intervention, and executes a bounded recovery workflow.

The workflow may cover revenue loss occurring through:

* Payment failures
* Checkout abandonment
* Failed subscriptions
* Overdue receivables

The objective is to find revenue that is slipping away and recover it.

---

## Why This Problem Exists

Revenue loss may occur through a sequence of events rather than a single event.

Examples include:

```text
Payment degradation
→ continued payment problems
→ revenue at risk
```

```text
Checkout initiated
→ checkout abandoned
→ potential revenue lost
```

```text
Subscription renewal attempted
→ payment fails
→ subscription revenue at risk
```

```text
Invoice reaches due date
→ invoice becomes overdue
→ receivable remains unpaid
```

AI can be used to connect the stages between:

```text
Detection
→ Diagnosis
→ Intervention
→ Recovery
```

---

## Required Capabilities

The agent must address the following functional stages:

### 1. Detect

Identify revenue that is at risk or has the potential to be lost.

### 2. Determine Cause

Determine the relevant reason, condition, or cause associated with the revenue risk.

### 3. Determine Intervention

Determine an appropriate intervention for the identified revenue risk.

### 4. Execute Recovery Workflow

Execute the selected recovery workflow.

The recovery workflow must be **bounded**.

### 5. Measure Recovery

The system must demonstrate measured money recovered across a batch.

### 6. Escalation

The workflow must include compliant escalation where escalation is applicable.

### 7. Stopping Rules

The workflow must define conditions under which recovery actions stop.

### 8. Audit Trail

The workflow must maintain an audit trail of the recovery process.

---

## Example Directions

The following are example directions for implementing the problem:

### Payment Degradation

```text
Payment degradation
→ root cause
→ recovery action
```

### Checkout Drop-off Recovery

Recover revenue associated with abandoned checkout activity.

### Failed Subscription Recovery

Recover revenue associated with failed subscription payments or renewals.

### B2B Receivables Chaser

Handle overdue business-to-business receivables through a recovery workflow.

### Mandate Retry Sequencer

Execute a bounded sequence for retrying failed payment mandates.

### Hinglish Voice Recovery

Use Hinglish voice interaction as part of a revenue recovery workflow.

### Promise-to-Pay Tracker

Track a customer's promise to make a payment and the subsequent recovery process.

These are example directions and do not define a required implementation.

---

## Core Requirement

The system must go beyond identifying a revenue problem.

The system should demonstrate the complete progression:

```text
Revenue at Risk
      ↓
Detection
      ↓
Determination / Diagnosis
      ↓
Intervention
      ↓
Recovery Workflow
      ↓
Measured Revenue Recovered
```

---

## Bounded Recovery

Recovery actions must operate within defined bounds.

A recovery workflow must therefore have defined limits or conditions governing its execution.

The workflow must not operate without stopping conditions.

---

## Compliant Escalation

Where escalation is part of the recovery workflow, escalation must be compliant with the applicable requirements governing that workflow.

---

## Stopping Rules

The recovery workflow must define conditions that cause recovery activity to stop.

Stopping conditions are part of the required workflow.

---

## Audit Trail

The system must maintain an audit trail describing relevant events and actions in the recovery workflow.

The audit trail should allow the recovery process to be examined after execution.

---

## Batch-Level Evaluation

The solution must demonstrate recovery across a **batch** of cases rather than only presenting an isolated identification of a revenue-risk case.

The result must include measured money recovered.

The central outcome is:

```text
Money recovered
```

rather than only:

```text
Revenue risk identified
```

---

## Scope

The problem domain includes revenue that may be at risk because of:

```text
Payment failures
Checkout abandonment
Failed subscriptions
Overdue receivables
Payment degradation
Mandate failures
Promise-to-pay situations
```

The example directions listed above are not exhaustive.

---

## Required Outcome

A valid solution addresses the following sequence:

```text
Detect revenue at risk
        ↓
Determine the relevant cause or condition
        ↓
Determine an intervention
        ↓
Execute a bounded recovery workflow
        ↓
Apply compliant escalation where applicable
        ↓
Stop according to defined stopping rules
        ↓
Maintain an audit trail
        ↓
Demonstrate measured money recovered across a batch
```

## Problem Definition in One Sentence

> **Build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow that demonstrates measured money recovered, with compliant escalation, stopping rules, and an audit trail.**
