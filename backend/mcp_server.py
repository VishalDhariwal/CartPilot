"""
CartPilot MCP Server Adapter

Exposes CartPilot's explainable commerce engine as a standard Model Context Protocol (MCP) server
using FastMCP with Streamable HTTP transport.

Tools exposed:
  1. search_catalog: Semantic and filtered catalog search
  2. get_product: Live SKU details, pricing, and stock
  3. propose_cart: Intent-to-cart parsing with strict guardrail enforcement (tagged channel: mcp_agent)
  4. get_upsell_suggestions: 3-tier growth recommendations (Data-Verified, Item2Vec, Live Scoped)
  5. add_item_to_cart: Dynamic cart expansion with mandatory guardrail re-validation
  6. checkout: Finalization with real Razorpay test-mode order & payment link creation
  7. check_payment_status: Live polling of webhook-driven payment mandate state
  8. get_order_audit_trail: Full explainable mandate chain & audit ledger
"""

import os
import json
import hmac
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from fastmcp import FastMCP

import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

from backend.db import get_db
from backend.agents.buyer_agent import generate_cart_proposal
from backend.engine.mandates import (
    create_intent_mandate,
    create_cart_mandate,
    create_payment_mandate,
    get_cart_state,
    execute_refund,
    create_audit_log
)
from backend.engine.guardrail import validate_cart
from backend.recommendations.lift_engine import find_cross_sell
from backend.integrations.razorpay_client import create_order, create_payment_link
from backend.agents.resolution_agent import decide_resolution


# ─── FAST MCP SERVER INITIALIZATION ──────────────────────────────────────────

MERCHANT_AUTH_KEY = os.environ.get("CARTPILOT_MERCHANT_KEY", "cartpilot_merchant_secret_key_v1")


def verify_merchant_auth(token: Optional[str]) -> bool:
    """
    Constant-time comparison for merchant credential verification.
    """
    if not token or not isinstance(token, str):
        return False
    expected = os.environ.get("CARTPILOT_MERCHANT_KEY", "cartpilot_merchant_secret_key_v1")
    return hmac.compare_digest(token.strip(), expected.strip())


# 1. Public Buyer MCP Server (Standard Shopping & Commerce)
buyer_mcp = FastMCP(
    name="CartPilot Buyer Agent",
    instructions="""
You are interacting with CartPilot — an autonomous, explainable agentic commerce backend.
You have access to real merchant inventory, guardrail-governed cart mandates, a 3-tier recommendation/upsell engine, and Razorpay test checkout.

Standard Shopping Workflow:
1. Use `propose_cart` to convert the user's intent into an approved cart.
2. When presenting the cart to the user, ALSO present the merchant's complementary items included in `recommended_upsells` (or retrieved via `get_upsell_suggestions`). Mention the reason (e.g. "Customers who bought X also bought Y").
3. If the user agrees to add a suggested item, call `add_item_to_cart`.
4. Call `checkout` when the buyer is ready to pay to receive their live Razorpay payment link.
"""
)

# 2. Authenticated Merchant Growth MCP Server (Administration & Autonomy Levers)
merchant_mcp = FastMCP(
    name="CartPilot Merchant Growth Agent",
    instructions="""
You are interacting with CartPilot Merchant Growth Agent.
This interface requires valid merchant authorization credentials (`merchant_token`).
You can inspect live revenue growth opportunities, monitor real-time AI attribution metrics, and dispatch Next Best Actions.
"""
)

# Backwards compatibility alias
mcp = buyer_mcp


# ─── BUYER TOOLS (REGISTERED ON BUYER_MCP) ───────────────────────────────────

@buyer_mcp.tool()
def search_catalog(
    query: str,
    category: Optional[str] = None,
    max_price_paise: Optional[int] = None
) -> Dict[str, Any]:
    """
    Search the merchant catalog by semantic keywords, category, and budget limit.
    Returns in-stock products matching the query.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        sql = "SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description FROM catalog WHERE stock > 0"
        params: List[Any] = []

        if category:
            sql += " AND category = ?"
            params.append(category)

        if max_price_paise:
            sql += " AND price_paise <= ?"
            params.append(max_price_paise)

        # Keyword matching
        if query:
            keywords = query.lower().split()
            clauses = []
            for kw in keywords[:3]:
                clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(category) LIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            if clauses:
                sql += " AND (" + " OR ".join(clauses) + ")"

        sql += " ORDER BY boosted DESC, price_paise ASC LIMIT 10"
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "sku": r["sku"],
                "name": r["name"],
                "price_paise": r["price_paise"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "stock": r["stock"],
                "category": r["category"],
                "merchant": r["merchant"],
                "boosted": bool(r["boosted"]),
                "image_url": r["image_url"] or "",
                "description": r["description"] or ""
            })

        return {
            "query": query,
            "count": len(results),
            "products": results
        }
    finally:
        conn.close()


@buyer_mcp.tool()
def get_product(sku: str) -> Dict[str, Any]:
    """
    Retrieve complete specifications, live inventory, and pricing for a specific SKU.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description, metadata FROM catalog WHERE sku = ?",
            (sku,)
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"SKU '{sku}' not found in catalog."}

        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                meta = {}

        return {
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": row["price_paise"],
            "price_rupees": round(row["price_paise"] / 100, 2),
            "stock": row["stock"],
            "in_stock": row["stock"] > 0,
            "category": row["category"],
            "merchant": row["merchant"],
            "boosted": bool(row["boosted"]),
            "image_url": row["image_url"] or "",
            "description": row["description"] or "",
            "metadata": meta
        }
    finally:
        conn.close()


@buyer_mcp.tool()
def propose_cart(
    intent_text: str,
    spend_cap_paise: int = 1000000
) -> Dict[str, Any]:
    """
    Parse a buyer's natural language shopping goal into a structured cart and execute Guardrail verification.
    Tagged with channel='mcp_agent'.
    If blocked by spend cap or policy, returns status='blocked' with plain-language reasoning.
    """
    # 1. Generate proposal via Buyer Agent
    agent_output = generate_cart_proposal(
        natural_language_request=intent_text,
        custom_spend_cap_paise=spend_cap_paise,
        conversation_history=None,
        current_cart=[]
    )

    # 2. Record Intent Mandate with channel='mcp_agent'
    intent = create_intent_mandate(
        raw_request=intent_text,
        goal=agent_output["goal"],
        spend_cap_paise=agent_output["spend_cap_paise"],
        channel="mcp_agent"
    )

    proposed_items = agent_output.get("proposed_items", [])
    if not proposed_items:
        return {
            "status": "blocked",
            "reason": "No valid in-stock items found for your request.",
            "intent_id": intent["id"],
            "spend_cap_rupees": round(spend_cap_paise / 100, 2),
            "items": [],
            "total_paise": 0
        }

    total_paise = sum(item["price_paise"] * item["qty"] for item in proposed_items)

    # 3. Guardrail Engine Verification
    validation = validate_cart(intent["id"], proposed_items, total_paise)

    # 4. Create Cart Mandate
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=proposed_items,
        total_paise=total_paise,
        status=validation["status"],
        reason=validation["reason"],
        reversible=validation["reversible"]
    )

    # 5. Fetch 3-Tier Growth Recommendations
    recommended_upsells = []
    upsell_summary_lines = []
    if cart["status"] == "approved":
        try:
            candidates = find_cross_sell(proposed_items, top_k=3)
            for c in candidates:
                p_rupees = round(c["price_paise"] / 100, 2)
                reason = c.get("reason", "Frequently bought together with your items.")
                recommended_upsells.append({
                    "sku": c["sku"],
                    "name": c["name"],
                    "price_rupees": p_rupees,
                    "category": c["category"],
                    "reason": reason,
                    "boosted": c.get("boosted", False)
                })
                upsell_summary_lines.append(f"• **{c['name']}** (₹{p_rupees}) — *{reason}* [SKU: `{c['sku']}`]")
        except Exception as e:
            print(f"⚠️ Upsell computation error in propose_cart: {e}")

    upsell_text = ""
    if upsell_summary_lines:
        upsell_text = (
            "✨ **Merchant Recommended Add-ons for Your Cart:**\n"
            + "\n".join(upsell_summary_lines)
            + "\n\n*(Tell me if you would like to add any of these to your cart before paying!)*"
        )

    return {
        "status": cart["status"],
        "cart_id": cart["id"],
        "intent_id": intent["id"],
        "goal": intent["goal"],
        "spend_cap_rupees": round(spend_cap_paise / 100, 2),
        "total_paise": total_paise,
        "total_rupees": round(total_paise / 100, 2),
        "items": proposed_items,
        "recommended_upsells": recommended_upsells,
        "merchant_recommendations_text": upsell_text,
        "instruction_to_agent": "Present the cart items AND present the 'merchant_recommendations_text' so the buyer can see complementary items before checking out.",
        "guardrail_reason": validation["reason"],
        "reversible": validation["reversible"],
        "channel": "mcp_agent"
    }


@buyer_mcp.tool()
def get_upsell_suggestions(cart_id: str) -> Dict[str, Any]:
    """
    Retrieve ranked 3-tier growth recommendations for an existing cart.
    Blends Data-Verified rules (Tier 1), Item2Vec sequences (Tier 2), and Live Category Scoped embeddings (Tier 3).
    """
    state = get_cart_state(cart_id)
    if not state or not state["cart"]:
        return {"error": f"Cart '{cart_id}' not found."}

    cart = state["cart"]
    items = json.loads(cart["items"]) if isinstance(cart["items"], str) else cart["items"]

    candidates = find_cross_sell(items, top_k=3)
    results = []
    for c in candidates:
        results.append({
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "price_rupees": round(c["price_paise"] / 100, 2),
            "category": c["category"],
            "source": c.get("source", "category_scoped"),
            "lift": c.get("lift"),
            "support": c.get("support"),
            "confidence": c.get("confidence"),
            "reason": c.get("reason", "Complementary recommendation for your cart."),
            "boosted": c.get("boosted", False)
        })

    return {
        "cart_id": cart_id,
        "cart_items_count": len(items),
        "suggestions_count": len(results),
        "suggestions": results
    }


@buyer_mcp.tool()
def add_item_to_cart(
    cart_id: str,
    sku: str,
    qty: int = 1
) -> Dict[str, Any]:
    """
    Add an item to an existing cart mandate.
    Re-runs the exact same Guardrail Engine to guarantee spend-cap and policy compliance.
    """
    state = get_cart_state(cart_id)
    if not state or not state["cart"]:
        return {"error": f"Cart '{cart_id}' not found."}

    original_cart = state["cart"]
    current_items = json.loads(original_cart["items"]) if isinstance(original_cart["items"], str) else original_cart["items"]

    # Fetch SKU details
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku, name, price_paise, category, stock, image_url, description FROM catalog WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if not row:
            return {"error": f"SKU '{sku}' not found in catalog."}
        if row["stock"] < qty:
            return {"error": f"Insufficient stock for SKU '{sku}'. Available: {row['stock']}."}

        # Append or update quantity
        updated_items = list(current_items)
        found = False
        for item in updated_items:
            if item["sku"] == sku:
                item["qty"] += qty
                found = True
                break
        if not found:
            updated_items.append({
                "sku": row["sku"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "qty": qty,
                "category": row["category"],
                "image_url": row["image_url"] or "",
                "description": row["description"] or ""
            })

        new_total_paise = sum(i["price_paise"] * i["qty"] for i in updated_items)

        # Re-validate through Guardrail Engine
        validation = validate_cart(original_cart["intent_id"], updated_items, new_total_paise)

        # Create updated Cart Mandate
        new_cart = create_cart_mandate(
            intent_id=original_cart["intent_id"],
            items=updated_items,
            total_paise=new_total_paise,
            status=validation["status"],
            reason=validation["reason"],
            reversible=validation["reversible"]
        )

        create_audit_log(
            cursor, "cart", new_cart["id"], "Cart Updated via MCP Agent",
            f"Added {qty}x {row['name']} ({sku}). New total: ₹{new_total_paise/100:.2f}. Status: {validation['status']}"
        )

        # Record accepted upsell event for revenue attribution
        if new_total_paise > original_cart["total_paise"] and new_cart["status"] == "approved":
            cursor.execute(
                """INSERT INTO upsell_events
                   (cart_id, suggested_sku, accepted, cart_total_before_paise,
                    cart_total_after_paise, created_at)
                   VALUES (?, ?, 1, ?, ?, ?)""",
                (new_cart["id"], sku, original_cart["total_paise"],
                 new_total_paise, datetime.utcnow().isoformat() + "Z")
            )

        conn.commit()

        return {
            "status": new_cart["status"],
            "cart_id": new_cart["id"],
            "previous_cart_id": cart_id,
            "total_paise": new_total_paise,
            "total_rupees": round(new_total_paise / 100, 2),
            "items": updated_items,
            "guardrail_reason": validation["reason"],
            "reversible": validation["reversible"]
        }
    finally:
        conn.close()


@buyer_mcp.tool()
def checkout(cart_id: str) -> Dict[str, Any]:
    """
    Finalize an approved cart mandate: creates a real Razorpay test-mode Order and Payment Link.
    Returns the URL for the user/agent to complete test payment.
    """
    state = get_cart_state(cart_id)
    if not state or not state["cart"]:
        return {"error": f"Cart '{cart_id}' not found."}

    cart = state["cart"]
    if cart["status"] not in ["approved", "pending_confirmation"]:
        return {"error": f"Cannot checkout cart with status '{cart['status']}'. Reason: {cart['reason']}"}

    total_paise = cart["total_paise"]

    # Create real Razorpay order
    order = create_order(
        amount_paise=total_paise,
        receipt_id=cart["id"],
        notes={"cart_id": cart["id"], "channel": "mcp_agent"}
    )

    # Create Razorpay payment link
    payment_link = create_payment_link(
        amount_paise=total_paise,
        order_id=order["id"],
        cart_id=cart["id"],
        description=f"CartPilot Order: {cart['id']}"
    )

    # Record Payment Mandate
    payment_mandate = create_payment_mandate(
        cart_id=cart["id"],
        razorpay_order_id=order["id"],
        amount_paise=total_paise
    )

    conn = get_db()
    cursor = conn.cursor()
    create_audit_log(
        cursor, "payment", payment_mandate["id"], "Payment Link Created via MCP Agent",
        f"Razorpay Order {order['id']} created for ₹{total_paise/100:.2f}. Link: {payment_link['short_url']}"
    )
    conn.commit()
    conn.close()

    # Compute post-checkout add-ons (identical to web chat)
    cart_items = json.loads(cart["items"]) if isinstance(cart["items"], str) else cart["items"]
    post_addons = []
    try:
        raw_addons = find_cross_sell(cart_items, top_k=2)
        for a in raw_addons:
            post_addons.append({
                "sku": a["sku"],
                "name": a["name"],
                "price_rupees": round(a["price_paise"] / 100, 2),
                "reason": a.get("reason", "Great match for this purchase.")
            })
    except Exception:
        post_addons = []

    return {
        "status": "pending_payment",
        "cart_id": cart["id"],
        "payment_mandate_id": payment_mandate["id"],
        "razorpay_order_id": order["id"],
        "amount_paise": total_paise,
        "amount_rupees": round(total_paise / 100, 2),
        "payment_url": payment_link["short_url"],
        "post_checkout_addons": post_addons,
        "instructions": "Present the payment_url to the buyer. You can also mention the 'post_checkout_addons' as 1-click add-on items they can add before or after paying."
    }


@buyer_mcp.tool()
def check_payment_status(cart_id: str) -> Dict[str, Any]:
    """
    Poll live payment mandate status for an order.
    Returns status: 'created', 'succeeded', 'failed', or 'cancelled'.
    """
    state = get_cart_state(cart_id)
    if not state or not state["payment"]:
        return {"error": f"No payment mandate found for cart '{cart_id}'."}

    pm = state["payment"]
    return {
        "payment_id": pm["id"],
        "cart_id": cart_id,
        "amount_rupees": round(pm["amount_paise"] / 100, 2),
        "status": pm["status"],
        "failure_reason": pm.get("failure_reason"),
        "razorpay_payment_id": pm.get("razorpay_payment_id"),
        "created_at": pm["created_at"],
        "updated_at": pm["updated_at"]
    }


def cancel_order(
    cart_id: Optional[str] = None,
    reason: Optional[str] = None,
    *args,
    **kwargs
) -> Dict[str, Any]:
    """
    Temporarily disabled for MCP clients.
    Order cancellation and refunds are supported via the web chat resolution interface (/resolution/cancel).
    """
    return {
        "error": "cancel_order is temporarily unavailable through MCP.",
        "status": "unavailable",
        "cart_id": cart_id,
        "message": "Order cancellation and refunds are currently only supported via the web chat console at /resolution/cancel."
    }


@buyer_mcp.tool()
def get_order_audit_trail(cart_id: str) -> Dict[str, Any]:
    """
    Return the full cryptographic and explainability mandate chain for an order:
    Intent Mandate, Cart Mandate, Payment Mandate, Guardrail reasons, and immutable Audit Log.
    """
    state = get_cart_state(cart_id)
    if not state or not state["cart"]:
        return {"error": f"Cart '{cart_id}' not found."}

    conn = get_db()
    cursor = conn.cursor()
    try:
        intent_id = state["cart"]["intent_id"]
        cursor.execute(
            """
            SELECT id, ref_type, ref_id, event, detail, created_at
            FROM audit_log
            WHERE ref_id = ? OR ref_id = ? OR ref_id = ?
            ORDER BY id DESC
            """,
            (cart_id, intent_id, (state["payment"]["id"] if state.get("payment") else "NULL"))
        )
        logs = [dict(r) for r in cursor.fetchall()]

        intent = state.get("intent")
        channel = "web_chat"
        if intent:
            if isinstance(intent, dict):
                channel = intent.get("channel", "web_chat")
            elif hasattr(intent, "__getitem__"):
                try:
                    channel = intent["channel"]
                except Exception:
                    channel = "web_chat"

        return {
            "cart_id": cart_id,
            "channel": channel,
            "intent_mandate": state.get("intent"),
            "cart_mandate": state.get("cart"),
            "payment_mandate": state.get("payment"),
            "audit_ledger": logs
        }
    finally:
        conn.close()


# ─── MERCHANT GROWTH TOOLS (REGISTERED ON MERCHANT_MCP WITH AUTH) ───────────

@merchant_mcp.tool()
def get_growth_opportunities(
    merchant_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merchant Growth Tool (Requires merchant_token):
    Returns live revenue growth opportunities detected by the AI Growth Agent:
    abandoned cart recoveries, high-lift cross-sells, inventory velocity boosts, and conversion reviews.
    """
    if not verify_merchant_auth(merchant_token):
        return {
            "error": "Unauthorized: Invalid or missing merchant_token. Merchant authorization required to access growth opportunities."
        }

    from backend.agents.growth_agent import detect_all_opportunities
    opps = detect_all_opportunities()
    return {
        "count": len(opps),
        "opportunities": opps
    }


@merchant_mcp.tool()
def get_growth_metrics(
    merchant_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merchant Growth Tool (Requires merchant_token):
    Returns live revenue attribution metrics distinguishing:
    - OBSERVED AI Incremental Revenue (cross-sell lift + recovered cart payments)
    - ESTIMATED Revenue Opportunity (potential value in idle carts & slow-moving stock)
    """
    if not verify_merchant_auth(merchant_token):
        return {
            "error": "Unauthorized: Invalid or missing merchant_token. Merchant authorization required to access growth metrics."
        }

    from backend.agents.growth_agent import get_growth_metrics as fetch_metrics
    return fetch_metrics()


@merchant_mcp.tool()
def execute_growth_action(
    action_type: str,
    target_id: str,
    merchant_token: Optional[str] = None,
    mode: str = "manual"
) -> Dict[str, Any]:
    """
    Merchant Growth Tool (Requires merchant_token):
    Executes a Next Best Action:
    - action_type='RECOVER_CART', target_id='<cart_id>': reissues Razorpay checkout link for an abandoned cart
    - action_type='PROMOTE_PRODUCT', target_id='<sku>': enables 1.35x merchant promotion boost in search
    - action_type='CROSS_SELL', target_id='<sku>': prioritizes cross-sell recommendation
    """
    if not verify_merchant_auth(merchant_token):
        return {
            "error": "Unauthorized: Invalid or missing merchant_token. Merchant authorization required to execute growth actions."
        }

    from backend.agents.growth_agent import execute_growth_action as run_action
    return run_action(action_type=action_type, target_id=target_id, mode=mode)


if __name__ == "__main__":
    buyer_mcp.run()
