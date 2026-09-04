# Project brief — Agentic Commerce for Razorpay Buildathon (Track 01)

## One-liner
A merchant-side agentic commerce system: an agent-readable catalog, a guardrail/mandate
engine, an upsell agent, and a Razorpay test-mode checkout — all wrapped in a visible
audit trail — that makes a merchant both (a) sellable to AI buyer agents end-to-end and
(b) able to grow revenue via agent-driven upsell/substitution.

## Context (do not skip — this shapes every decision below)
This is for Razorpay's buildathon, Track 01: "AI Growth & Agentic Commerce."
Real-world reference points this design is deliberately modeled on:
- **AP2 (Google)**: chains three signed mandates — Intent, Cart, Payment — to make every
  agent purchase explainable and bounded. We are replicating this pattern (without real
  cryptographic signing — a hackathon-appropriate simplification).
- **ACP (OpenAI + Stripe)**: standardizes catalog discovery + checkout handoff between a
  buyer agent and a merchant, while the merchant stays "merchant of record."
- **NPCI's UAP / Razorpay Reserve Pay**: a pre-authorized spending cap lets an agent
  transact multiple times without re-confirming each time, within a bound.

We are NOT implementing these protocols literally (no real crypto signatures, no OAuth
delegation, no external agent registry). We are implementing their *pattern* —
explainable, bounded, gated, audited — on top of Razorpay's test-mode APIs.

## Non-negotiables ("THE BAR" — every phase must serve these, no exceptions)
1. **Every money action is explainable, bounded, and gated.** No code path may create a
   Razorpay order or attempt a charge without first passing through the guardrail engine
   and producing a logged reason.
2. **The audit trail is a real, visible UI**, not console logs. A person with zero context
   must be able to open it and understand what happened and why for any given order.
3. **At least one failure is deliberately triggered and gracefully recovered**, visibly,
   in the demo — not just handled silently in a try/catch.

If a proposed feature does not serve one of these three, it is lower priority than a
feature that does.

## Scope: build BOTH halves of the track, combined
- **Growth half**: upsell/cross-sell agent that increases cart value with one relevant,
  reasoned suggestion per order.
- **Transactable-by-AI-buyer half**: an agent-readable catalog + guardrail-gated checkout
  that any external buyer agent (simulated by our own minimal buyer agent for the demo)
  can transact against.

## Tech stack (keep it boring — optimize for finishing, not novelty)
- **Backend**: Python + FastAPI (or Node + Express — pick one and don't switch later).
- **DB**: SQLite. No need for Postgres at this scale; zero setup friction.
- **LLM calls**: Anthropic API (Claude) for both the buyer agent and the upsell agent.
  Use plain `messages.create` calls with a strict system prompt instructing JSON-only
  output for structured steps (intent parsing, cart building, upsell suggestion).
- **Payments**: Razorpay test-mode, Orders API + Payment Links + Webhooks. See
  `03_RAZORPAY_TESTMODE_REFERENCE.md`.
- **Frontend**: a single simple web page (plain HTML/JS or React, your call) with two
  panels: (1) a chat-style input to talk to the buyer agent, (2) the audit trail
  dashboard. No design system needed — clarity over polish, except on the audit
  dashboard, which should look genuinely good since it's the most judge-visible screen.

## Definition of done for the whole project
- A person can type a natural-language order request, watch the buyer agent build a
  cart from the catalog, watch it pass (or fail) the guardrail check, see an upsell
  suggestion offered and accepted/declined, complete a real Razorpay test-mode payment,
  and then open the audit dashboard and see the full Intent → Cart → Payment chain with
  every decision and its reason.
- A person can also trigger a deliberate failure (over spend cap, or a declined test
  card) and watch the system recover gracefully and log it.

## How to use the rest of these files
Read in this order: this file → `01_ARCHITECTURE_AND_DATA_MODEL.md` →
`02_BUILD_PHASES_AND_TASKS.md` (work through phases in order, one at a time) →
`03_RAZORPAY_TESTMODE_REFERENCE.md` (reference whenever touching payment code) →
`04_VERIFICATION_CHECKLIST.md` (use after every phase, not just at the end).
