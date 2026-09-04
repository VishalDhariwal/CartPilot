# CartPilot: Merchant Ledger & Audit Trail Specification
**Author:** CartPilot Core Team  
**System Version:** 2.0 (Deterministic Guardrails & Multi-Agent Architecture)  
**Target Surface:** `/audit` (Merchant Ledger & Cryptographic Audit Trail)  

---

## 1. System Overview & Problem Statement

Autonomous e-commerce agents introduce significant financial, compliance, and operational risks if allowed to make black-box decisions. In traditional LLM architectures, agents can:
1. Overrun buyer budgets (spend cap violations).
2. Hallucinate non-existent products or out-of-stock items.
3. Move or refund real customer funds without deterministic validation.
4. Conflate vanity metrics with true incremental revenue.

**CartPilot solves this through the Mandate Chain and the Immutable Audit Ledger.**

```
[ User Request ] 
       │
       ▼
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│    Intent Mandate    │ ──> │     Cart Mandate     │ ──> │   Payment Mandate    │
│  (Immutable Session) │     │ (Guardrail Verified) │     │  (Razorpay Rails)    │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
       │                                │                                │
       ▼                                ▼                                ▼
──────────────────────────────────────────────────────────────────────────────────
                        IMMUTABLE CHRONOLOGICAL AUDIT LOG
──────────────────────────────────────────────────────────────────────────────────
```

Every action taken by either a **human shopper** via the web interface or an **autonomous AI agent** over the Model Context Protocol (MCP) is parsed into typed, immutable mandate records and recorded in an append-only cryptographic event stream.

---

## 2. Real-Time Telemetry: 5 Key Performance Indicators (KPIs)

The top of the `/audit` page renders five mission-critical commerce and safety KPIs. Each metric is computed on live database tables with exact inclusion/exclusion rules.

---

### KPI 1: Gross Order Volume (GMV)

* **Display Label:** `Gross Order Volume`
* **Purpose:** Measures the total commercial volume approved by the CartPilot guardrail engine.
* **Underlying Database Table:** `cart_mandates` (joined with `intent_mandates`)
* **Mathematical Formula:**
  $$\text{GMV} = \sum_{\substack{c \in \text{cart\_mandates} \\ c.\text{status} = \text{'approved'}}} \frac{c.\text{total\_paise}}{100}$$
* **Backend SQL Query:**
  ```sql
  SELECT SUM(total_paise) 
  FROM cart_mandates 
  WHERE status = 'approved';
  ```
* **Sub-Telemetry Badge:** Displays total shopping sessions initiated (`COUNT(intent_mandates)`).
* **Inclusion / Exclusion Rules:**
  * ✅ **Included:** All carts that passed the deterministic guardrail policy.
  * ❌ **Excluded:** Carts that were blocked due to spend cap overruns or policy restrictions.

---

### KPI 2: AI Growth & Incremental Revenue Lift

* **Display Label:** `AI Growth & Upsells`
* **Purpose:** Quantifies the net new basket revenue generated directly by AI cross-sell rules (Item2Vec embeddings and Market Basket Association).
* **Underlying Database Tables:** `upsell_events`, `growth_outcomes`, `basket_pairs`
* **Mathematical Formulas:**
  $$\text{Incremental Lift (₹)} = \sum_{\substack{e \in \text{upsell\_events} \\ e.\text{accepted} = 1}} \frac{e.\text{cart\_total\_after\_paise} - e.\text{cart\_total\_before\_paise}}{100}$$
  $$\text{Attach Rate (\%)} = \left( \frac{\text{Accepted Upsells}}{\text{Total Sessions}} \right) \times 100$$
* **Backend SQL Query:**
  ```sql
  SELECT 
    COUNT(*) AS total_offered,
    SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) AS total_accepted,
    SUM(CASE WHEN accepted = 1 THEN (cart_total_after_paise - cart_total_before_paise) ELSE 0 END) AS total_revenue_lift_paise
  FROM upsell_events u
  LEFT JOIN payment_mandates pm ON u.cart_id = pm.cart_id
  LEFT JOIN cart_mandates cm ON u.cart_id = cm.id
  WHERE COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
    AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED';
  ```
* **Strict Accounting Rule:** Cancelled or refunded orders are **voided** from AI attributed revenue (`incremental_paise = 0`).

---

### KPI 3: Settled Orders

* **Display Label:** `Settled Orders`
* **Purpose:** Counts real commerce transactions that have been successfully captured on payment rails and verified via webhook signatures.
* **Underlying Database Table:** `payment_mandates`
* **Mathematical Formula:**
  $$\text{Settled Orders} = \text{COUNT}\Big(\{p \in \text{payment\_mandates} \mid p.\text{status} = \text{'succeeded'} \land p.\text{recovery\_action} \neq \text{'refunded'}\}\Big)$$
* **Backend SQL Query:**
  ```sql
  SELECT COUNT(*) 
  FROM payment_mandates 
  WHERE status = 'succeeded' 
    AND (recovery_action IS NULL OR recovery_action != 'refunded')
    AND COALESCE(refund_status, 'NONE') != 'REFUNDED';
  ```
* **Verification Rail:** Verified through Razorpay HMAC-SHA256 signature verification on `payment.captured` webhooks.

---

### KPI 4: Guardrail Interceptions

* **Display Label:** `Guardrail Interceptions`
* **Purpose:** Proves the safety engine's effectiveness by counting the exact number of high-risk transactions stopped before payment initiation.
* **Underlying Database Tables:** `cart_mandates`, `audit_log`
* **Mathematical Formula:**
  $$\text{Interceptions} = \text{COUNT}\Big(\{c \in \text{cart\_mandates} \mid c.\text{status} = \text{'blocked'}\}\Big)$$
* **Trigger Conditions Stopped by Guardrails:**
  1. **Spend Cap Overrun:** Cart value exceeds the buyer's authorized spend limit.
  2. **Prohibited Category:** Attempt to procure items from merchant-restricted categories.
  3. **Out-of-Stock / Phantom SKUs:** Requested items unavailable in inventory.

---

### KPI 5: Resolution Reversals (Refunds)

* **Display Label:** `Resolution Reversals`
* **Purpose:** Tracks orders that were evaluated and safely refunded through the deterministic resolution engine.
* **Underlying Database Tables:** `refunds`, `payment_mandates`, `resolution_mandates`
* **Mathematical Formula:**
  $$\text{Reversals} = \text{COUNT}\Big(\{p \in \text{payment\_mandates} \mid p.\text{refund\_status} = \text{'REFUNDED'} \lor p.\text{recovery\_action} = \text{'refunded'}\}\Big)$$
* **Backend SQL Query:**
  ```sql
  SELECT COUNT(*) 
  FROM payment_mandates 
  WHERE refund_status = 'REFUNDED' 
     OR recovery_action = 'refunded';
  ```
* **Safety Rail:** Executed exclusively via deterministic post-purchase policies (zero LLM authorization of bank balances).

---

## 3. Order Ledger Slips & Interactive Features

Each shopping session on `/audit` is rendered as an **Order Ledger Slip** that groups all child mandates, metadata, line-items, and micro-events.

### Visual Slip Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🤖 MCP External Agent  Home Office Setup                                [ Settled & Captured ✓ ]│
│ ID: 9F2D81B4 • Spend Cap: ₹15,000 • Final Value: ₹12,490 • 3 items • 7 events • Today, 12:15 PM│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ ITEMS: [🖼️ Ergonomic Chair - ₹7,999] [🖼️ Desk Mat - ₹1,499] [🖼️ LED Light Bar - ₹2,992]    │
│ Razorpay Order: order_O8x912b • Payment ID: pay_P71k9a1                                     │
│                                                                                             │
│ AUDIT TIMELINE:                                                                             │
│  ● Payment Captured (ref: P71k9a1) — ₹12,490 captured via Razorpay webhook.    12:16:04 PM  │
│  ● Razorpay Order Created (ref: O8x912b) — Order initialized on test rails.   12:15:42 PM  │
│  ● Upsell Accepted (ref: 9F2D81B4) — Added 'LED Light Bar' (+₹2,992).          12:15:30 PM  │
│  ● Cart Mandate Approved (ref: 9F2D81B4) — ₹9,498 within ₹15,000 budget.       12:15:15 PM  │
│  ● Intent Mandate Created (ref: 9F2D81B4) — Channel: mcp_agent.                12:15:02 PM  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Status Badge Classification Logic

| Status Pill | Color | Condition | Meaning |
|---|---|---|---|
| `Settled & Captured ✓` | Green | `payment.status == 'succeeded'` | Payment captured and confirmed by gateway webhook. |
| `Refunded Reversal` | Purple | `payment.refund_status == 'REFUNDED'` | Full refund executed through resolution engine. |
| `Guardrail Intercepted` | Red | `cart.status == 'blocked'` | Policy breach stopped order before checkout. |
| `Payment Failed` | Red | `payment.status == 'failed'` | Gateway declined transaction (routed to recovery). |
| `Cart Gated / Pending` | Gray | `cart.status == 'pending'` | Awaiting user authorization or payment completion. |

---

## 4. Multi-Channel Parity: Web Chat vs. Remote MCP Agents

CartPilot provides identical safety guarantees regardless of where the shopping request originates:

```
                  ┌───────────────────────────────┐
                  │      Shopping Request         │
                  └──────────────┬────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       🌐 Buyer Web Chat              🤖 Remote MCP Agent
   (Direct Human Shopper)          (Claude Desktop / Cursor)
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                 ┌───────────────────────────────┐
                 │  Deterministic Guardrail &    │
                 │   Mandate Engine (Single Rail)│
                 └───────────────────────────────┘
```

1. **`🌐 Buyer Web Chat`**: Initiated by human shoppers through the web application.
2. **`🤖 MCP External Agent`**: Initiated by external AI agents connecting via Model Context Protocol (MCP). The remote agent must adhere to the same spend caps and cannot bypass the guardrail.

---

## 5. Chronological Audit Event Reference

Every step in the lifecycle generates a structured event in `audit_log`:

| Event Name | Type | Emitted By | Purpose |
|---|---|---|---|
| `Intent Mandate Created` | `intent` | Buyer Agent / MCP | Records the buyer's original goal and spend limit constraint. |
| `Catalog Search Executed` | `cart` | Search Engine | Logs candidate products discovered without hallucination. |
| `OOS Item Substituted` | `cart` | Substitution Agent | Transparently replaces zero-stock items with in-stock alternatives. |
| `Cart Mandate Approved` | `cart` | Guardrail Engine | Confirms cart total $\le$ spend cap and categories are compliant. |
| `Cart Mandate Blocked` | `cart` | Guardrail Engine | Prevents over-budget checkout with explicit policy justification. |
| `Upsell Offered` | `cart` | Growth Engine | Records 4-tier complementary recommendation offered to buyer. |
| `Upsell Accepted` | `cart` | Buyer / Agent | Logs acceptance of cross-sell and basket value modification. |
| `Razorpay Order Created` | `payment` | Checkout Engine | Creates Razorpay order instance on gateway test rails. |
| `Payment Captured` | `payment` | Webhook Handler | Confirms HMAC-SHA256 signature and settles payment mandate. |
| `Payment Failed` | `payment` | Webhook / Gateway | Triggers real-time recovery agent with bounded retry logic. |
| `Order Cancelled` | `cart` | Resolution Engine | Pre-fulfillment cancellation completed; order status set to `CANCELLED`. |
| `Refund Settled` | `payment` | Resolution Engine | Confirms gateway refund ID and zeroes store revenue attribution. |

---

## 6. Real-Time Ingestion & Performance Guarantees

* **Polling Rate:** 4,000 ms (4 seconds) automated refresh.
* **Auto-Reconciliation:** If an order sits in `created` state, the backend polls the Razorpay API directly on `/api/cart-status/{cart_id}` to prevent UI lag.
* **Immutability:** The `audit_log` table is append-only; records are never updated or deleted.
* **Accounting Guarantee:** Zero revenue leakage — all cancelled and refunded transactions are excluded from realized store revenue and recoverable cart opportunities.
