import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.db import init_db, get_db
from backend.api import routes_checkout, routes_webhook, routes_resolution, routes_recovery, routes_console, routes_growth





app = FastAPI(title="CartPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup database and recommendation engines on startup
@app.on_event("startup")
def startup_event():
    print("🚀 Initializing Database...")
    init_db()

    # Sync DummyJSON catalog if empty or missing images
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM catalog WHERE image_url IS NOT NULL AND image_url != ''")
        valid_items_count = cursor.fetchone()[0]
        conn.close()

        if valid_items_count < 150:
            print("📦 Syncing live catalog from DummyJSON...")
            from backend.integrations.dummyjson_sync import sync_dummyjson_catalog
            sync_dummyjson_catalog()
        else:
            # Compute empirical rules for any pairs with >= 8 real orders
            from backend.recommendations.lift_engine import compute_lift_pairs
            compute_lift_pairs(min_co_occurrence=8)

            # Check if category_compatibility graph exists; if empty, generate
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM category_compatibility")
            cc_count = cursor.fetchone()[0]
            conn.close()
            if cc_count == 0:
                from backend.recommendations.scalable_engine import generate_category_compatibility
                generate_category_compatibility()

    except Exception as e:
        print(f"⚠️ Error during startup sync: {e}")

    # Precompute missing catalog embeddings & train item2vec in background thread
    import threading
    def _bg_embeddings():
        try:
            from backend.recommendations.embedding_engine import precompute_catalog_embeddings
            precompute_catalog_embeddings(force=False)
        except Exception as e:
            print(f"⚠️ Error precomputing catalog embeddings: {e}")

        try:
            from backend.recommendations.scalable_engine import train_co_purchase_embeddings
            train_co_purchase_embeddings(min_orders=50)
        except Exception as e:
            print(f"⚠️ Error training co-purchase embeddings: {e}")

    threading.Thread(target=_bg_embeddings, daemon=True).start()

    # Start Autonomous AI Growth Worker (5-minute background loop)
    import asyncio
    from backend.agents.growth_worker import run_autonomous_growth_worker
    asyncio.create_task(run_autonomous_growth_worker(interval_seconds=300))


# Include routers
app.include_router(routes_checkout.router, prefix="/checkout", tags=["Checkout"])
app.include_router(routes_webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(routes_resolution.router, prefix="/resolution", tags=["Resolution"])
app.include_router(routes_recovery.router, prefix="/recovery", tags=["Recovery"])
app.include_router(routes_console.router, prefix="/api/console", tags=["Merchant Console"])
app.include_router(routes_growth.router, prefix="/api/growth", tags=["AI Growth Agent"])

# Mount Remote Model Context Protocol (MCP) Servers
from backend.mcp_server import buyer_mcp, merchant_mcp
app.mount("/mcp/merchant", merchant_mcp.http_app(transport="streamable-http"))
app.mount("/mcp", buyer_mcp.http_app(transport="streamable-http"))


@app.get("/.well-known/ucp", tags=["Universal Commerce Protocol"])
def get_ucp_profile():
    """
    Universal Commerce Protocol (UCP) Discovery Profile.
    Publishes merchant capabilities, guardrail boundaries, and remote MCP endpoint for AI buyers.
    """
    return {
        "ucp_version": "1.0",
        "merchant_name": "CartPilot Merchant Store",
        "description": "Explainable Autonomous Commerce Engine with 3-Tier Recommendations & Guardrail Governance",
        "capabilities": {
            "catalog_search": True,
            "cart_mandate": True,
            "guardrail_validation": True,
            "upsell_engine": True,
            "checkout_razorpay_test": True,
            "refund_reversal": False,
            "audit_trail": True
        },
        "mcp_endpoint": "/mcp",
        "transports": ["streamable-http", "sse"],
        "governance": {
            "spend_cap_enforced": True,
            "stock_verified": True,
            "autonomous_reversibility": True,
            "audit_trail_immutable": True
        },
        "llms_txt_url": "/llms.txt"
    }


@app.get("/llms.txt", tags=["Agent Discovery"])
def get_llms_txt():
    """
    Plain-text Agent Discovery file describing CartPilot capabilities and MCP entrypoint.
    """
    from fastapi.responses import PlainTextResponse
    content = """# CartPilot — Agentic Commerce Server

CartPilot enables autonomous AI buyers to discover products, itemize carts within budget spend caps, receive grounded recommendations, and execute Razorpay test-mode transactions with complete explainability.

## MCP Server Endpoint (Public Buyer Tools)
- Remote MCP Endpoint: /mcp (Streamable HTTP & SSE)
- Transport: streamable-http

## Available MCP Buyer Tools:
- search_catalog(query, category, max_price_paise): Discover in-stock catalog products.
- get_product(sku): Fetch full product specs, pricing, and live inventory.
- propose_cart(intent_text, spend_cap_paise): Build a cart from natural language with strict spend cap & stock verification.
- get_upsell_suggestions(cart_id): Retrieve ranked 3-tier cross-sells (Data-Verified, Item2Vec, Live Scoped).
- add_item_to_cart(cart_id, sku, qty): Add items to cart with mandatory guardrail re-validation.
- checkout(cart_id): Generate real Razorpay test-mode order and checkout payment link.
- check_payment_status(cart_id): Poll live webhook-driven payment status.
- get_order_audit_trail(cart_id): Inspect full explainable mandate chain & audit ledger.

## Authenticated Merchant Growth MCP:
- Protected Endpoint: /mcp/merchant (Requires Bearer/merchant_token authorization)
- Merchant Tools: get_growth_opportunities, get_growth_metrics, execute_growth_action

## Policy & Guardrail Guarantees:
Every cart is validated against buyer spend caps and live catalog inventory before payment links are created. All actions are logged to an append-only audit ledger.
"""
    return PlainTextResponse(content=content, media_type="text/plain")


@app.get("/catalog", tags=["Catalog"])
def get_catalog():
    """
    Agent-readable catalog endpoint.
    Returns the full merchant catalog as structured JSON with authentic product images and descriptions.
    Any AI buyer agent can query this to discover available SKUs.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description, tags FROM catalog ORDER BY category, name"
        )
        rows = cursor.fetchall()
        items = [
            {
                "sku": row["sku"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "price_rupees": round(row["price_paise"] / 100, 2),
                "stock": row["stock"],
                "category": row["category"],
                "merchant": row["merchant"],
                "boosted": bool(row["boosted"]),
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "tags": json.loads(row["tags"]) if row["tags"] else []
            }
            for row in rows
        ]
        return {"count": len(items), "items": items}
    finally:
        conn.close()



@app.get("/api/cart-status/{cart_id}", tags=["Dashboard"])
def get_cart_status(cart_id: str):
    """
    Polling endpoint for the frontend to check payment status.
    If the status in DB is still 'created', it proactively checks Razorpay API directly
    to verify if the payment was captured or failed.
    This guarantees instantaneous UI transitions even if webhooks are delayed!
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, status, razorpay_order_id, razorpay_payment_id, failure_reason, recovery_action FROM payment_mandates WHERE cart_id = ?",
            (cart_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"found": False, "status": None}

        mandate_id = row["id"]
        status = row["status"]
        order_id = row["razorpay_order_id"]
        payment_id = row["razorpay_payment_id"]
        failure_reason = row["failure_reason"]
        recovery_action = row["recovery_action"]

        # If still waiting in 'created' state, proactively check Razorpay API or auto-settle in bypass mode!
        if status == "created" and order_id:
            try:
                from backend.integrations.razorpay_client import is_bypass_mode, client
                from backend.engine.mandates import update_payment_mandate_status
                import uuid

                if is_bypass_mode() or str(order_id).startswith("order_mock_"):
                    mock_payment_id = f"pay_mock_{uuid.uuid4().hex[:14]}"
                    update_payment_mandate_status(
                        razorpay_order_id=order_id,
                        cart_id=cart_id,
                        status="succeeded",
                        payment_id=mock_payment_id
                    )
                    status = "succeeded"
                    payment_id = mock_payment_id
                elif client:
                    # Check payments for this order
                    payments_resp = client.order.payments(order_id)
                    items = payments_resp.get("items", [])

                    # If not found directly on order, check recent payments for matching notes
                    if not items:
                        recent = client.payment.all({"count": 10})
                        for p in recent.get("items", []):
                            p_notes = p.get("notes", {})
                            if p_notes.get("order_id") == order_id or p_notes.get("cart_id") == cart_id:
                                items.append(p)
                                break

                    for p in items:
                        p_status = p.get("status")
                        p_id = p.get("id")
                        if p_status == "captured":
                            update_payment_mandate_status(
                                razorpay_order_id=order_id,
                                cart_id=cart_id,
                                status="succeeded",
                                payment_id=p_id
                            )
                            status = "succeeded"
                            payment_id = p_id
                            break
                        elif p_status == "failed":
                            p_error = p.get("error_description", "Payment failed")
                            from backend.agents.recovery_agent import analyze_failure
                            recovery_data = analyze_failure(p_error)
                            rec = recovery_data.get("recommendation", "Please try another payment method.")

                            update_payment_mandate_status(
                                razorpay_order_id=order_id,
                                cart_id=cart_id,
                                status="failed",
                                failure_reason=p_error,
                                payment_id=p_id,
                                recovery_action=rec
                            )
                            status = "failed"
                            failure_reason = p_error
                            recovery_action = rec
                            break
            except Exception as e:
                print(f"Error querying Razorpay API for order {order_id}: {e}")

        return {
            "found": True,
            "payment_mandate_id": mandate_id,
            "status": status,
            "razorpay_payment_id": payment_id,
            "failure_reason": failure_reason,
            "recovery_action": recovery_action,
        }
    finally:
        conn.close()


@app.get("/api/upsell-stats", tags=["Dashboard"])
def get_upsell_stats():
    """
    Upsell conversion metrics for the Growth Metrics card.
    Calculates verified incremental lift from growth_outcomes and active upsell events.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM intent_mandates")
        total_orders = cursor.fetchone()[0] or 1

        cursor.execute("""
            SELECT COUNT(DISTINCT u.cart_id) 
            FROM upsell_events u
            JOIN cart_mandates cm ON u.cart_id = cm.id
            JOIN payment_mandates pm ON u.cart_id = pm.cart_id
            WHERE u.accepted = 1 
              AND pm.status = 'succeeded'
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
        """)
        orders_with_upsell = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM upsell_events")
        total_offered_raw = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) 
            FROM upsell_events u
            JOIN cart_mandates cm ON u.cart_id = cm.id
            JOIN payment_mandates pm ON u.cart_id = pm.cart_id
            WHERE u.accepted = 1 
              AND pm.status = 'succeeded'
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
        """)
        total_accepted = cursor.fetchone()[0] or 0

        # Verified incremental cross-sell revenue from growth_outcomes
        cursor.execute("""
            SELECT COALESCE(SUM(g.incremental_paise), 0)
            FROM growth_outcomes g
            WHERE g.outcome_type = 'paid' 
              AND g.revenue_type = 'cross_sell' 
              AND g.incremental_paise > 0
              AND NOT EXISTS (
                  SELECT 1 FROM payment_mandates pm
                  JOIN cart_mandates cm ON pm.cart_id = cm.id
                  WHERE (g.id = 'go_paid_' || pm.id OR g.action_id = pm.id OR (g.id LIKE 'go_xs_%' AND g.action_id = cm.id))
                    AND (COALESCE(pm.refund_status, 'NONE') = 'REFUNDED' OR COALESCE(cm.order_status, 'CREATED') = 'CANCELLED')
              )
        """)
        total_lift_paise = cursor.fetchone()[0] or 0

        total_offered = max(total_offered_raw, total_accepted)
        total_revenue_lift_rupees = round(total_lift_paise / 100, 2)
        conversion_rate = round((total_accepted / total_orders * 100), 1) if total_orders > 0 else 0.0
        avg_uplift_rupees = round((total_lift_paise / total_accepted) / 100, 2) if total_accepted > 0 else 0.0

        return {
            "total_orders": total_orders,
            "orders_with_upsell": orders_with_upsell,
            "total_offered": total_offered,
            "total_accepted": total_accepted,
            "accepted_count": total_accepted,
            "total_declined": max(0, total_offered - total_accepted),
            "conversion_rate_pct": conversion_rate,
            "acceptance_rate_pct": conversion_rate,
            "total_revenue_lift_paise": total_lift_paise,
            "total_revenue_lift_rupees": total_revenue_lift_rupees,
            "avg_uplift_paise": round(total_lift_paise / total_accepted) if total_accepted > 0 else 0,
            "avg_uplift_rupees": avg_uplift_rupees
        }
    finally:
        conn.close()



@app.post("/api/recommendations/recompute-lift", tags=["Recommendations"])
def trigger_recompute_lift():
    """
    On-demand endpoint to trigger Market Basket Lift recomputation.
    """
    from backend.recommendations.lift_engine import compute_lift_pairs
    rules_count = compute_lift_pairs()
    return {"status": "ok", "rules_count": rules_count}


@app.get("/api/recommendations/lift-pairs", tags=["Recommendations"])
def get_lift_pairs(limit: int = 20):
    """
    Returns top Market Basket Association rules with product names, lift, and support.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                bp.sku_a, ca.name AS name_a, ca.category AS category_a,
                bp.sku_b, cb.name AS name_b, cb.category AS category_b,
                bp.lift, bp.support, bp.computed_at
            FROM basket_pairs bp
            JOIN catalog ca ON ca.sku = bp.sku_a
            JOIN catalog cb ON cb.sku = bp.sku_b
            ORDER BY bp.lift DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        pairs = [
            {
                "sku_a": row["sku_a"],
                "name_a": row["name_a"],
                "category_a": row["category_a"],
                "sku_b": row["sku_b"],
                "name_b": row["name_b"],
                "category_b": row["category_b"],
                "lift": row["lift"],
                "support": row["support"],
                "computed_at": row["computed_at"],
            }
            for row in rows
        ]
        return {"count": len(pairs), "pairs": pairs}
    finally:
        conn.close()


@app.get("/api/dashboard", tags=["Dashboard"])
def get_dashboard():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM intent_mandates ORDER BY created_at DESC LIMIT 500")
        intents = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM cart_mandates ORDER BY created_at DESC LIMIT 1000")
        carts = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM payment_mandates ORDER BY created_at DESC LIMIT 1000")
        payments = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 2000")
        audit_logs = [dict(row) for row in cursor.fetchall()]

        return {
            "intents": intents,
            "carts": carts,
            "payments": payments,
            "audit_logs": audit_logs
        }
    finally:
        conn.close()


class UpdatePolicyRequest(BaseModel):
    spend_cap_paise: Optional[int] = None
    spend_cap_rupees: Optional[int] = None



@app.get("/api/policy", tags=["Policy"])
def get_policy():
    """
    Returns the active merchant / user policy configuration including spend cap and allowed categories.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            return {
                "spend_cap_paise": 1000000,
                "spend_cap_rupees": 10000,
                "allowed_categories": []
            }
        return {
            "spend_cap_paise": row["spend_cap_paise"],
            "spend_cap_rupees": round(row["spend_cap_paise"] / 100, 2),
            "allowed_categories": json.loads(row["allowed_categories"]) if row["allowed_categories"] else []
        }
    finally:
        conn.close()


@app.post("/api/policy/spend-cap", tags=["Policy"])
def update_spend_cap(req: UpdatePolicyRequest):
    """
    Allows the user or merchant to dynamically update their active spend cap at any time.
    Immediately updates policy_config in SQLite and records an audit log event.
    """
    new_cap = req.spend_cap_paise
    if new_cap is None and req.spend_cap_rupees is not None:
        new_cap = int(req.spend_cap_rupees * 100)

    if new_cap is None or new_cap <= 0:
        raise HTTPException(status_code=400, detail="spend_cap_paise or spend_cap_rupees must be a positive integer")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE policy_config SET spend_cap_paise = ? WHERE id = 1", (new_cap,))
        from backend.engine.mandates import create_audit_log
        create_audit_log(
            cursor, "policy", "config_1", "Spend Cap Updated",
            f"Spend ceiling updated to ₹{new_cap/100:.0f} ({new_cap} paise)"
        )
        conn.commit()
        return {
            "status": "updated",
            "spend_cap_paise": new_cap,
            "spend_cap_rupees": round(new_cap / 100, 2)
        }
    finally:
        conn.close()


class SaveSessionRequest(BaseModel):
    id: str
    title: str
    session_data: dict


@app.get("/api/chat-sessions", tags=["Chat"])
def list_chat_sessions():
    """
    Returns all cross-browser persistent chat sessions from SQLite database.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT 50")
        rows = cursor.fetchall()
        sessions = []
        for r in rows:
            try:
                data = json.loads(r["session_data"])
                sessions.append(data)
            except Exception:
                pass
        return {"sessions": sessions}
    finally:
        conn.close()


@app.post("/api/chat-sessions", tags=["Chat"])
def save_chat_session(req: SaveSessionRequest):
    """
    Persists or updates a chat session across all browsers and devices in SQLite.
    """
    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.utcnow().isoformat()
    try:
        cursor.execute(
            """
            INSERT INTO chat_sessions (id, title, session_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                session_data=excluded.session_data,
                updated_at=excluded.updated_at
            """,
            (req.id, req.title, json.dumps(req.session_data), now_iso, now_iso)
        )
        conn.commit()
        return {"status": "saved", "id": req.id}
    finally:
        conn.close()


@app.delete("/api/chat-sessions/{session_id}", tags=["Chat"])
def delete_chat_session(session_id: str):
    """
    Deletes a persistent chat session from SQLite.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return {"status": "deleted", "id": session_id}
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


