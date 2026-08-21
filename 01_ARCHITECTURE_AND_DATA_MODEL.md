# Architecture and data model

## Components and responsibilities

| Component | Responsibility | Must never do |
|---|---|---|
| Buyer agent | Parse natural-language request into a structured Intent Mandate; propose a Cart from the catalog | Call Razorpay directly. It only ever talks to the merchant system. |
| Agent-readable catalog | Serve products as structured JSON (id, name, price, stock, category) | Contain business logic — it's a read-only data source. |
| Guardrail and mandate engine | Validate every Cart against spend cap, SKU allow-list; classify reversibility; sign Cart Mandate or reject with a reason; create Payment Mandate | Let anything reach Razorpay without passing through it first. |
| Upsell / substitution agent | On an approved cart, propose one add-on; on a blocked/out-of-stock item, propose one substitute | Add items to the cart directly — it only *proposes*; the guardrail re-validates the modified cart before anything is added. |
| Razorpay integration | Create test-mode Orders, generate Payment Links, receive and verify Webhooks | Hold any business logic — it's a thin wrapper around Razorpay's SDK. |
| Audit trail store + dashboard | Persist and display every mandate and every decision, linked | Summarize or drop failure/reject events — those are the most important entries. |

## Data model (SQLite)

```sql
CREATE TABLE catalog (
  sku TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  price_paise INTEGER NOT NULL,   -- store money in paise, never floats
  stock INTEGER NOT NULL,
  category TEXT NOT NULL
);

CREATE TABLE policy_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),  -- single row, simple global policy
  spend_cap_paise INTEGER NOT NULL,
  allowed_categories TEXT NOT NULL        -- JSON array
);

CREATE TABLE intent_mandates (
  id TEXT PRIMARY KEY,             -- e.g. "intent_" + uuid
  raw_request TEXT NOT NULL,       -- the buyer's original natural-language text
  goal TEXT NOT NULL,              -- structured summary
  spend_cap_paise INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE cart_mandates (
  id TEXT PRIMARY KEY,             -- e.g. "cart_" + uuid
  intent_id TEXT NOT NULL REFERENCES intent_mandates(id),
  items TEXT NOT NULL,             -- JSON array of {sku, qty, price_paise}
  total_paise INTEGER NOT NULL,
  status TEXT NOT NULL,            -- "approved" | "blocked"
  reason TEXT NOT NULL,            -- always populated, even on approval
  reversible INTEGER NOT NULL,     -- 1 or 0
  created_at TEXT NOT NULL
);

CREATE TABLE payment_mandates (
  id TEXT PRIMARY KEY,             -- e.g. "pay_" + uuid
  cart_id TEXT NOT NULL REFERENCES cart_mandates(id),
  razorpay_order_id TEXT,
  razorpay_payment_id TEXT,
  amount_paise INTEGER NOT NULL,
  status TEXT NOT NULL,            -- "created" | "succeeded" | "failed" | "recovered"
  failure_reason TEXT,
  recovery_action TEXT,            -- "retried" | "substituted" | "refunded" | null
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ref_type TEXT NOT NULL,          -- "intent" | "cart" | "payment" | "upsell"
  ref_id TEXT NOT NULL,
  event TEXT NOT NULL,             -- short human-readable event name
  detail TEXT NOT NULL,            -- human-readable reason/explanation
  created_at TEXT NOT NULL
);
```

Every write to `intent_mandates`, `cart_mandates`, or `payment_mandates` MUST be
accompanied by a write to `audit_log` in the same transaction. No exceptions — this is
what makes the trail trustworthy instead of reconstructed after the fact.

## Mandate JSON shapes (what the agents actually produce/consume)

```json
// Intent Mandate
{
  "id": "intent_abc123",
  "raw_request": "order me 2kg atta and a mixer whistle, budget 1500",
  "goal": "grocery + kitchenware purchase",
  "spend_cap_paise": 150000,
  "created_at": "2026-08-21T10:00:00Z"
}
```

```json
// Cart Mandate
{
  "id": "cart_def456",
  "intent_id": "intent_abc123",
  "items": [
    {"sku": "ATTA-2KG", "qty": 1, "price_paise": 12000},
    {"sku": "MIXER-WHISTLE", "qty": 1, "price_paise": 30000}
  ],
  "total_paise": 42000,
  "status": "approved",
  "reason": "within spend cap (42000 <= 150000); all SKUs in allowed categories",
  "reversible": true,
  "created_at": "2026-08-21T10:00:05Z"
}
```

```json
// Payment Mandate
{
  "id": "pay_ghi789",
  "cart_id": "cart_def456",
  "razorpay_order_id": "order_XXXXXXXXXXXX",
  "amount_paise": 42000,
  "status": "created",
  "created_at": "2026-08-21T10:00:06Z"
}
```

## Suggested folder structure

```
/backend
  /agents
    buyer_agent.py        # LLM call: raw text -> Intent Mandate + Cart proposal
    upsell_agent.py        # LLM call: approved cart -> one suggestion
  /engine
    guardrail.py           # validates cart, signs or rejects, writes audit log
    mandates.py             # create/read Intent, Cart, Payment records
  /integrations
    razorpay_client.py      # thin wrapper: create_order, verify_webhook
  /api
    routes_catalog.py       # GET /catalog
    routes_checkout.py      # POST /intent, POST /cart/approve, POST /checkout
    routes_webhook.py       # POST /webhook/razorpay
    routes_audit.py         # GET /audit
  db.py                     # SQLite connection + schema init
  main.py                   # FastAPI app entrypoint
/frontend
  index.html                # buyer chat panel
  audit.html                # audit dashboard
  app.js
seed_catalog.json            # 3-5 hardcoded products
```

Keep every LLM-facing prompt in its own small function with a fixed system prompt that
demands JSON-only output. Do not let the model free-write prose into a field that then
gets parsed — validate and re-ask on malformed JSON rather than guessing.
