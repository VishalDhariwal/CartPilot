# CartPilot: Audit Trail Screen Recording Spoken Script
**Read this word-for-word during your recording.**

---

### **[00:00 – 00:15] SECTION 1: Introduction & Live Sync**

> **[ACTION: Start on `/audit`. Point your mouse cursor at the main header "Merchant Ledger & Audit Trail".]**

"Hi everyone. Welcome to the CartPilot Merchant Ledger and Audit Trail. 

In autonomous commerce, trust is everything. If you let an AI agent shop or manage checkouts, you cannot have it behaving like a black box. 

That is why CartPilot records every single intent, guardrail check, upsell, and payment on an immutable, cryptographic ledger."

> **[ACTION: Hover your mouse over the top-right "Synced Live" button.]**

"This page updates in real-time every four seconds, giving merchants complete visibility into both human shoppers and external AI agents connecting over MCP."

---

### **[00:15 – 00:45] SECTION 2: The 5 Core Telemetry KPIs & Formulas**

> **[ACTION: Slowly move cursor across the 5 top metric cards.]**

"At the top of the dashboard, we track five core commerce and safety metrics. Let’s look at how each one is calculated."

> **[ACTION: Hover over KPI Card 1: "Gross Order Volume" (keep mouse still for 1.5s to show the tooltip).]**

"First, **Gross Order Volume**. This is the sum of all cart values that successfully passed our guardrail policy. It represents true commercial purchase intent."

> **[ACTION: Hover over KPI Card 2: "AI Growth & Upsells" (keep mouse still for 1.5s to show tooltip).]**

"Second, **AI Growth and Upsells**. Unlike vanity metrics, this strictly calculates net incremental revenue from accepted cross-sells. If an order is later cancelled or refunded, our accounting engine automatically zeros out that revenue so your reporting stays clean."

> **[ACTION: Hover over KPI Card 3: "Settled Orders".]**

"Third, **Settled Orders**. These are transactions verified with HMAC-SHA256 cryptographic signatures directly from Razorpay payment capture webhooks."

> **[ACTION: Hover over KPI Card 4: "Guardrail Interceptions".]**

"Fourth, **Guardrail Interceptions**. This measures how many times our deterministic safety engine stopped an over-budget cart, an out-of-stock item, or a restricted category before any payment link could be created."

> **[ACTION: Hover over KPI Card 5: "Resolution Reversals".]**

"And fifth, **Resolution Reversals**. This tracks orders that were safely cancelled and refunded through our automated resolution engine."

---

### **[00:45 – 01:05] SECTION 3: Multi-Channel Filtering**

> **[ACTION: Click the filter buttons: `Settled`, `✨ AI Growth`, `Guardrail Blocked`, `Refunded`.]**

"Merchants can filter by completed orders, AI growth attribution, blocked attempts, or refunds."

> **[ACTION: Click the `🤖 MCP Agent` filter, then click `🌐 Web Chat`, then reset back to `All Orders`.]**

"Notice our multi-channel tracking. CartPilot supports both human web shoppers and autonomous agents like Claude Desktop running over Model Context Protocol. Both channels are held to the exact same spend caps and audit rules."

---

### **[01:05 – 01:30] SECTION 4: Deep-Dive into an Order Ledger Slip**

> **[ACTION: Click on the top completed order card with the green "Settled & Captured ✓" badge to expand it.]**

"Let's open an active order slip."

> **[ACTION: Point cursor at the item thumbnails and pricing chip.]**

"At the top, we see the itemized product list, the buyer’s spend cap, and the verified Razorpay payment mandate ID."

> **[ACTION: Scroll down slightly to show the chronological audit timeline points.]**

"Below it is the chronological audit stream. You can trace the exact lifecycle:
- First, the **Intent Mandate** was created with the customer's budget limit.
- Second, the **Cart Mandate** was approved by the guardrail.
- Third, our AI growth engine offered an **Item2Vec upsell**, which was accepted.
- And finally, the **Razorpay payment webhook** was captured and settled."

---

### **[01:30 – 01:45] SECTION 5: Closing Statement**

> **[ACTION: Scroll smoothly back up to the top overview.]**

"With CartPilot, you get the power of autonomous AI commerce with the mathematical safety of a banking ledger. Every action is explainable, policy-guarded, and auditable. 

Thank you for watching!"
