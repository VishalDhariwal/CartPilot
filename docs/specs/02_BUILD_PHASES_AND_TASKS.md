# Build phases and tasks

Instructions for use: give Antigravity ONE phase at a time, in order. Do not paste the
whole file at once — each phase should be its own conversation turn/task so you can
verify before moving on. After each phase, run the "Verify" steps yourself before
telling Antigravity to proceed to the next phase. If verification fails, tell it exactly
which check failed and ask it to fix that before continuing — don't let it move on with
a broken foundation.

---

## Phase 1 (days 1-2): Razorpay test-mode plumbing, zero AI involved

**Task for Antigravity:**
Set up a Razorpay test-mode account integration. Write a minimal script (not the full
app yet) that:
1. Creates a Razorpay test-mode Order for a fixed amount (e.g. ₹420).
2. Generates a Payment Link for that order.
3. Sets up a local webhook receiver (use ngrok or similar) that logs incoming
   `payment.captured` and `payment.failed` events to the console.
Do not build the catalog, agents, or guardrail yet. This phase proves the payment rail
works before anything else depends on it.

**Verify (do this yourself, don't skip):**
- [ ] You can open the generated Payment Link in a browser and complete payment using a
      Razorpay test card (see `03_RAZORPAY_TESTMODE_REFERENCE.md` for test card numbers).
- [ ] The webhook receiver logs a `payment.captured` event within a few seconds of
      completing payment.
- [ ] Repeat with a test card designed to fail — confirm a `payment.failed` event is
      logged.
- [ ] No hardcoded API keys committed to any file that would be shared/pushed — keys in
      `.env`, `.env` in `.gitignore`.

---

## Phase 2 (days 3-4): the thin end-to-end slice, still no LLM

**Task for Antigravity:**
Implement the full data model from `01_ARCHITECTURE_AND_DATA_MODEL.md` in SQLite. Seed
`catalog` with 3-5 hardcoded products. Build a straight-through path with NO agent
intelligence yet — a hardcoded Intent Mandate, a hardcoded Cart Mandate built from 1-2
catalog items, passed through a guardrail check (even if the check is just "total <=
spend cap"), then a real Razorpay Order created via the API, then a webhook updating the
Payment Mandate status, with every step writing to `audit_log`.

**Verify:**
- [ ] Run the script/endpoint that triggers the hardcoded flow — confirm rows appear in
      `intent_mandates`, `cart_mandates`, `payment_mandates`, and `audit_log` (query the
      SQLite file directly to check).
- [ ] Every mandate row has a populated, human-readable `reason`/`detail` field — not
      null, not empty string.
- [ ] The `audit_log` entries are in correct chronological order and each references the
      correct `ref_id`.
- [ ] Complete a real test payment through this flow and confirm `payment_mandates.status`
      updates to "succeeded" via the webhook, not by manually setting it.

This phase is your safety net — do not proceed until this works completely, since every
later phase builds on top of it without changing this core wiring.

---

## Phase 3 (days 5-7): real buyer agent

**Task for Antigravity:**
Replace the hardcoded Intent/Cart with a real LLM call. Implement `buyer_agent.py`: it
takes a natural-language request string, calls the Anthropic API with a system prompt
that demands JSON-only output matching the Intent Mandate shape (goal, spend_cap_paise)
plus a proposed cart (array of {sku, qty} chosen from the actual catalog contents passed
into the prompt). Wire this into the Phase 2 pipeline in place of the hardcoded values.

**Verify:**
- [ ] Type "order me 2kg atta and a mixer whistle, budget 1500" (or similar, matching
      your actual seeded catalog) into whatever interface exists so far (CLI is fine for
      now) and confirm a real Intent Mandate and Cart Mandate are created with sensible
      values.
- [ ] Try a deliberately vague or malformed request and confirm the system does NOT crash
      — it should either ask a clarifying question or reject gracefully with a reason.
- [ ] Confirm the agent only ever selects SKUs that actually exist in the catalog — test
      by asking for something not in the catalog and checking it doesn't hallucinate a
      SKU.

---

## Phase 4 (days 8-9): guardrail engine, for real

**Task for Antigravity:**
Build out `guardrail.py` properly: check cart total against `policy_config.spend_cap_paise`,
check every SKU's category against `allowed_categories`, classify the cart as reversible
(true for anything before Razorpay capture; you can keep this simple) or not, and produce
a specific, human-readable reason for approval OR rejection. On rejection, do not create
a Payment Mandate at all — the flow stops at the Cart Mandate with status "blocked".

**Verify:**
- [ ] Send a request that exceeds the configured spend cap — confirm the Cart Mandate is
      created with `status = "blocked"` and a reason mentioning the cap and the amounts,
      and confirm NO Payment Mandate or Razorpay Order is created for it.
- [ ] Send a request for an item outside the allowed categories (if you've configured
      more than one category) — same check.
- [ ] Send a valid request — confirm it still flows through to a real Razorpay order as
      in Phase 3.
- [ ] Check the audit log captures the rejection with the same clarity as an approval —
      this is graded, don't let rejections be a one-line afterthought in the logs.

---

## Phase 5 (days 10-11): upsell / substitution agent

**Task for Antigravity:**
Implement `upsell_agent.py`. After a cart is approved by the guardrail (but before
payment), call it with the approved cart contents and the full catalog. It should
propose exactly one addition (a complementary item, with a one-line reason) OR, if
triggered from a stock-check failure elsewhere, exactly one substitute. Any accepted
suggestion must be re-validated by the SAME guardrail engine (re-check spend cap) before
being added to the cart — do not bypass the guardrail for upsell items.

**Verify:**
- [ ] Complete a normal order and confirm exactly one upsell suggestion appears with a
      sensible reason tied to the actual cart contents (not generic/random).
- [ ] Accept the suggestion — confirm the cart total updates and it's re-validated against
      the spend cap (test by accepting an upsell that would push the total over the cap
      and confirming it's rejected, not silently added).
- [ ] Decline the suggestion — confirm the order proceeds normally without it, and that
      the decline is still logged in the audit trail (a declined suggestion is still an
      auditable event).

---

## Phase 6 (day 12): deliberate failure and graceful recovery

**Task for Antigravity:**
Add a path that uses a Razorpay test-mode card known to fail (see
`03_RAZORPAY_TESTMODE_REFERENCE.md`). When the webhook reports `payment.failed`, the
system should: mark the Payment Mandate as "failed" with the `failure_reason` populated
from the webhook payload, check the cart's `reversible` flag, and then either (a) offer
a retry, (b) call the upsell/substitution agent to propose a cheaper alternative if the
failure looks amount-related, or (c) cleanly cancel and notify — whichever is most
appropriate — and log which recovery action was taken in `payment_mandates.recovery_action`
and in the audit log.

**Verify:**
- [ ] Trigger a payment using a known-failing test card and confirm the webhook is
      received and processed (don't just assume — check the logs/DB).
- [ ] Confirm the system does not crash, hang, or silently do nothing — some recovery
      action is visibly taken and logged.
- [ ] Confirm the audit trail shows the full story for this order: created → failed →
      recovery action → final state, all readable in sequence.

---

## Phase 7 (day 13): audit trail dashboard

**Task for Antigravity:**
Build `audit.html` (or equivalent) as a real, clean UI — not a raw table dump. For each
order, show a timeline: Intent → Cart (approved/blocked + reason) → Upsell decision (if
any) → Payment (created → succeeded/failed → recovery, if any). Make blocked carts and
failed/recovered payments visually distinct (e.g. color) from clean successes — these
are the interesting cases and should be easy to find, not buried in a long list.

**Verify:**
- [ ] Open the dashboard with no prior context and confirm you can explain what happened
      in any given order just by reading it — if you have to check the database to
      understand an entry, the dashboard isn't done.
- [ ] Confirm the blocked-cart example from Phase 4 and the failed-payment example from
      Phase 6 are both visible and clearly explained here, not just in raw logs.

---

## Phase 8 (day 14): end-to-end rehearsal

**Task for Antigravity:**
No new features. Run through the full demo script below multiple times, fixing any
rough edges, error states, or slow paths encountered:
1. Type a normal order request → agent builds cart → guardrail approves → upsell offered
   and accepted → real Razorpay test payment completed → audit dashboard shows the full
   chain.
2. Type a request that exceeds the spend cap → guardrail blocks it → audit dashboard
   shows the block with reason.
3. Complete an order using the known-failing test card → recovery happens → audit
   dashboard shows the full failure-and-recovery story.

**Verify:**
- [ ] Run the full script twice in a row without restarting the server/DB and confirm
      it works both times, cleanly.
- [ ] Time it — if any single step takes more than a few seconds with no loading
      indication, add a simple loading state; a silent multi-second pause reads as broken
      in a live demo.

---

## Phase 9 (day 15): buffer
No tasks — this day is reserved for whatever broke during rehearsal. Do not add new
scope on this day, even if there's time left over.
