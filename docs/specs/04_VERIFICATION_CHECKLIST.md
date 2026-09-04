# Master verification checklist

Use this after every phase, and again in full before you consider the project demo-ready.
It's organized around the brief's actual grading criteria ("THE BAR"), not around your
code structure — so you're always checking against what judges will actually look for.

## "Every money action explainable, bounded and gated"

- [ ] Search the codebase for every place a Razorpay Order is created. Confirm each one
      is only reachable AFTER a guardrail check has run and produced an "approved" status.
      If you find even one code path that can create an order without going through the
      guardrail, that's a real gap — fix it, don't just note it.
- [ ] Pick any three orders (mix of approved and blocked) in your database. For each,
      confirm you can answer, from stored data alone (not memory of testing it): what was
      requested, what the cap was, what the cart contained, why it was approved/blocked.
- [ ] Confirm there is an actual configured spend cap (not effectively infinite) and an
      actual configured allow-list, and that both are enforced, not just present in code
      as unused variables.

## "Show the audit trail"

- [ ] Open the audit dashboard cold (no context from just having tested it) and confirm
      you can narrate any order's full story from the screen alone.
- [ ] Confirm blocked carts and failed/recovered payments are visually distinguishable
      from clean successes, not buried in a uniform list.
- [ ] Confirm every mandate type (Intent, Cart, Payment) and the upsell decision (if any)
      appear somewhere in the trail for a given order — not just the payment result.

## "One failure handled gracefully"

- [ ] Confirm you can reliably trigger the failure on demand (known-failing test card,
      or a spend-cap violation) — "reliably" meaning it works the same way every time you
      demo it, not something that worked once.
- [ ] Confirm the system's response to the failure is visible in the UI in real time, not
      only discoverable afterward in the audit log — the demo moment matters.
- [ ] Confirm the recovery is a real action (retry / substitute / clean cancel), not a
      generic "something went wrong" message.

## General project health

- [ ] The full demo script (from Phase 8 in `02_BUILD_PHASES_AND_TASKS.md`) runs twice in
      a row without a restart, cleanly.
- [ ] No API keys or secrets anywhere in committed files.
- [ ] The pitch narrative explicitly names what this is modeled on (AP2's mandate chain,
      NPCI UAP's spending-limit model, ACP's catalog/checkout split) — this signals
      protocol literacy to judges familiar with the space, and ties your build back to
      the "WHY NOW" framing in the brief.
- [ ] You can explain, in one sentence each, what would need to change to make this a
      real production integration (e.g. real cryptographic mandate signing, real agent
      identity/registration, live-mode Razorpay) — judges may ask this, and "we know
      exactly where the simplifications are" is a stronger answer than pretending there
      aren't any.
