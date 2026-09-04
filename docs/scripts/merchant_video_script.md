# 🎬 CartPilot — Merchant Video Script & Navigation Guide

---

## 🧭 Recording Setup Checklist
- Open storefront & console at `http://localhost:3001`
- Backend API running at `http://localhost:8000`
- Zoom level: 110–125% for clean readability
- Fullscreen recording in 1080p

---

## INTRO [0:00 – 0:30]
> 🖥️ **Navigate to:** `http://localhost:3001` → Login as Merchant → Overview Dashboard

"Hi everyone. What I've built here is called **CartPilot** — it's an AI-powered commerce platform that gives a merchant complete, real-time control over how their store behaves, how products are recommended, and how revenue is recovered — all without writing a single line of code.

In the next few minutes, I'm going to walk you through the **merchant side** of the product, which is essentially the command center — the place where the merchant sees everything happening, makes decisions, and configures the AI engine behind their store.

Let's jump in."

---

## SECTION 1 — Command Center Overview [0:30 – 1:30]
> 🖥️ **Stay on:** Overview / Command Center — scroll slowly down

"This is the **Overview page** — the first thing a merchant sees when they log in.

At the top, you've got live KPI cards. These pull real data from the backend — things like AI-attributed revenue, how many carts the system autonomously recovered, and how many cross-sell suggestions were accepted by shoppers.

These numbers update every time the AI growth agent runs. So the merchant always has a live pulse on what the AI is actually doing for their business.

Below that, you have actionable insights — things like 'this product hasn't been promoted in a while' or 'there are 3 idle carts worth recovering right now.' Each card tells the merchant exactly what to do next, so it's not just data — it's decisions."

---

## SECTION 2 — Growth Manager [1:30 – 2:45]
> 🖥️ **Navigate to:** Sidebar → **Manager**

"Now let's go into the **Growth Manager**.

This is where the autonomous AI agent operates. The agent runs in the background on a schedule — it looks at your catalog, your orders, your idle carts, and it figures out what opportunities exist right now.

These are **Next Best Actions** — things like 'Customer X has an abandoned cart worth ₹1,200. Send them a recovery offer.' The merchant can see each opportunity, and either let the AI handle it automatically, or approve it manually.

The pipeline view shows the AI's work queue — all the opportunities it has identified, sorted by potential revenue impact.

> 🖥️ **Click:** Recovery Offers tab

This is the **Cart Recovery** tab. If someone added products to their cart and left, the system generates a personalized recovery offer for them — with a payment link, no discount gaming, no spam. It's intelligent recovery.

> 🖥️ **Click:** Ledger / Audit tab

And this tab shows a **cryptographic audit log** of every action the AI ever took — every recommendation made, every cart it touched, every decision. This is important because the merchant can always see *why* something happened. Full transparency.

This autonomy slider at the top lets the merchant set how much they trust the AI. Full autonomous mode, semi-auto, or manual review. The merchant stays in control."

---

## SECTION 3 — Campaign Studio [2:45 – 4:15]
> 🖥️ **Navigate to:** Sidebar → **Campaign Studio**

"Now here's something I'm particularly excited about — the **Campaign Studio**.

The idea is simple: every store has big selling moments — festivals, seasons, local events. Diwali, Onam, Monsoon, End-of-Year clearance. Instead of manually boosting products every time one of these comes around, CartPilot handles it automatically.

These cards tell you, right now, how many campaigns are active, what the current boost multiplier is, and how many product categories are covered by the current campaign.

> 🖥️ **Click:** Active Now tab

You can see which campaigns are currently live and boosting. The system calculates that Onam, for example, starts 2 days *before* the event date — because that's when real retail demand starts building.

> 🖥️ **Click:** Upcoming tab

These are the festivals coming up — pre-loaded from a built-in retail calendar covering major Indian festivals. Each campaign shows the name, date, boost multiplier, and which categories are being targeted. Enable or disable with one click.

> 🖥️ **Click:** + New Sale Campaign

Now here's the custom campaign creator. Say you're running a Monsoon Clearance sale — you type the name, the date, the duration, and how strong you want the AI boost to be.

Then — and this is really cool — you can use this multi-select category picker to choose exactly which product categories this campaign should boost.

Or — if you leave it empty — the AI uses a dense semantic model called **MiniLM** to automatically figure out which categories fit your campaign's theme. So if you type 'monsoon season,' it knows to boost rain gear, hot beverages, and indoor products — without you having to spell it out.

That's the hybrid approach — manual precision when you want it, full AI automation when you don't."

---

## SECTION 4 — Cross-Sell Rules & Safety Guardrails [4:15 – 5:15]
> 🖥️ **Navigate to:** Sidebar → **Cross-Sell Rules**

"Next is the **Rules Engine** — this is where the merchant defines how cross-selling works in their store.

A cross-sell rule says something like: 'Whenever someone buys a coffee maker, always suggest coffee beans and a cleaning kit.' These override the AI's default behavior.

Each rule shows the trigger product and the suggested products. Add, edit, or delete at any time. No deployment. No code changes.

> 🖥️ **Scroll to:** Safety Guardrails section

Now this section is equally important — **Safety Guardrails**.

These are the hard rules the AI cannot break. For example: 'Never recommend products above ₹5,000 as cross-sells.' These are deterministic — the AI doesn't get a vote here.

This is what makes CartPilot different from a black-box AI. The merchant always has a veto."

---

## SECTION 5 — Order Ledger & Forensic Audit [5:15 – 5:50]
> 🖥️ **Navigate to:** Sidebar → **Order Ledger**

"Finally, the **Order Ledger** — a complete, immutable timeline of every transaction in the store.

Every order shows the items purchased, whether cross-sells were accepted, whether the cart passed the AI guardrail check, and the final payment status.

The mandate chain — from the shopper's intent, through the cart, to payment — is logged and cryptographically verifiable at every step. Full forensic auditability."

---

## OUTRO [5:50 – 6:30]
> 🖥️ **Navigate back to:** Overview Dashboard

"So to summarize what I've built on the merchant side:

— A **live command center** with real-time AI revenue attribution  
— An **autonomous growth agent** that finds and recovers lost revenue  
— A **Campaign Studio** that auto-boosts the right products for every festival  
— A **Rules Engine** where merchants define their own cross-sell logic  
— And **Safety Guardrails** that keep the AI in check, always

The whole philosophy of CartPilot is: **give the AI autonomy, but keep the merchant in control.** Every decision the AI makes is transparent, explainable, and reversible.

Thanks for watching — I'm happy to dive deeper into any part of this."
