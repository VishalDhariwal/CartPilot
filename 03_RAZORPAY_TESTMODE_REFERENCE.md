# Razorpay test-mode reference

Note: verify every endpoint/parameter name below against Razorpay's current official
docs before relying on it — payment API details can change, and this file is a starting
reference, not a substitute for the live docs at https://razorpay.com/docs/.

## Setup
1. Sign up / log in to the Razorpay Dashboard, switch to **Test Mode** (toggle in the
   dashboard — test mode never touches real money).
2. Generate a Key ID + Key Secret under Settings → API Keys (test mode keys).
3. Store both in a `.env` file, never in committed code:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxx
   ```
4. Set up a webhook (Dashboard → Webhooks) pointing at your local endpoint via a tunnel
   (ngrok, cloudflared, etc.) during development — you need a public URL for Razorpay
   to reach. Subscribe at minimum to `payment.captured` and `payment.failed`.
5. Note the webhook secret shown in the dashboard — used to verify signatures on
   incoming webhook calls (do not skip signature verification, even in test mode — build
   the habit).

## Creating a test-mode Order (conceptual shape — confirm exact fields in current docs)
```
POST https://api.razorpay.com/v1/orders
Authorization: Basic base64(key_id:key_secret)
Content-Type: application/json

{
  "amount": 42000,          // amount in paise
  "currency": "INR",
  "receipt": "cart_def456", // tie this back to your cart_mandate id
  "notes": {
    "cart_id": "cart_def456"
  }
}
```
The response includes an `id` like `order_XXXXXXXXXXXX` — store this in
`payment_mandates.razorpay_order_id`.

## Payment Links
Payment Links are the simplest way to get a payable checkout URL without building a
full checkout UI — good fit for a hackathon timeline. Create one referencing the order
amount and pass it back to whatever surface (chat, buyer agent output) is asking the
"buyer" to pay.

## Test cards (for triggering success and failure paths)
Razorpay publishes a standard set of test-mode card numbers for simulating both
successful and failed payments (declined card, insufficient funds, etc.), along with any
required test OTP. Pull the current, exact list from Razorpay's test-mode documentation
before Phase 1 — do not guess card numbers, use the ones the docs currently publish, as
these are specifically whitelisted by Razorpay's test environment and change over time.
Use one "always succeeds" card for the happy path and one "always fails" card
specifically for Phase 6 (deliberate failure).

## Webhook verification (do not skip this)
Every incoming webhook payload should be verified against the webhook secret before
being trusted — Razorpay signs the payload and provides a signature header. Reject and
log (don't crash on) any webhook that fails verification. This is a real security
practice worth having even in test mode, and "we verify webhook signatures" is a good
line in your pitch under "bounded and gated."

## Mapping webhook events to your data model
| Razorpay event | Action in your system |
|---|---|
| `payment.captured` | Update matching `payment_mandates` row (via `razorpay_order_id`) to `status = "succeeded"`; write audit log entry. |
| `payment.failed` | Update to `status = "failed"`, populate `failure_reason` from the payload; trigger Phase 6 recovery logic; write audit log entry. |

## Common pitfalls to check for
- Amounts must be integers in the smallest currency unit (paise), never floats/rupees —
  a ₹420 order is `amount: 42000`, not `420.00`.
- Webhook delivery can be delayed by a few seconds — don't assume synchronous updates;
  the UI should reflect "payment pending" state until the webhook lands.
- Test-mode and live-mode keys are completely separate — double check you're reading
  `RAZORPAY_KEY_ID` starting with `rzp_test_`, not a live key, anywhere in the project.
