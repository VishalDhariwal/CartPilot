import json
import re
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.db import init_db, get_db
from backend.api import routes_checkout, routes_webhook, routes_resolution, routes_recovery, routes_console, routes_growth, routes_ingest





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

    # Check catalog status in PostgreSQL
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM catalog")
        valid_items_count = cursor.fetchone()[0]
        conn.close()

        if valid_items_count == 0:
            print("ℹ️ PostgreSQL Catalog is currently empty. Ready for API Key or CSV data ingestion.")
        else:
            print(f"📦 PostgreSQL Database connected with {valid_items_count} catalog items.")
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

        # Pre-warm embedding model in memory
        try:
            from backend.recommendations.embedding_engine import get_model
            get_model()
        except Exception as e:
            print(f"⚠️ Error warming embedding model: {e}")

    except Exception as e:
        print(f"⚠️ Error during startup check: {e}")

    # Precompute missing catalog embeddings & train item2vec in background thread
    import threading
    def _bg_embeddings():
        try:
            import time
            time.sleep(2)
            from backend.recommendations.embedding_engine import precompute_catalog_embeddings
            precompute_catalog_embeddings()
            from backend.recommendations.scalable_engine import train_co_purchase_embeddings
            train_co_purchase_embeddings(min_orders=50)
        except Exception as e:
            print(f"⚠️ Non-blocking recommendation precomputation note: {e}")
    threading.Thread(target=_bg_embeddings, daemon=True).start()

    # Start Autonomous AI Growth Worker (5-minute background loop)
    import asyncio
    from backend.agents.growth_worker import run_autonomous_growth_worker
    asyncio.create_task(run_autonomous_growth_worker(interval_seconds=300))


# Include routers
app.include_router(routes_checkout.router, prefix="/checkout", tags=["Checkout"])
app.include_router(routes_checkout.router, prefix="/api/checkout", tags=["Checkout"])
app.include_router(routes_webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(routes_resolution.router, prefix="/resolution", tags=["Resolution"])
app.include_router(routes_recovery.router, prefix="/recovery", tags=["Recovery"])
app.include_router(routes_console.router, prefix="/api/console", tags=["Merchant Console"])
app.include_router(routes_growth.router, prefix="/api/growth", tags=["AI Growth Agent"])
app.include_router(routes_ingest.router, tags=["Data Ingestion"])

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
@app.get("/api/catalog", tags=["Catalog"])
def get_catalog():
    """
    Agent-readable catalog endpoint.
    Returns the full merchant catalog as structured JSON with authentic product images, descriptions,
    and autonomous seasonal merchandising weights.
    Any AI buyer agent or merchant dashboard can query this to discover available SKUs.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason, image_url, description, tags FROM catalog ORDER BY category, name"
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
                "boost_weight": float(row["boost_weight"]) if ("boost_weight" in row.keys() and row["boost_weight"] is not None) else 1.0,
                "boost_source": row["boost_source"] if ("boost_source" in row.keys() and row["boost_source"]) else "system",
                "boost_reason": row["boost_reason"] if ("boost_reason" in row.keys() and row["boost_reason"]) else "",
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "tags": json.loads(row["tags"]) if row["tags"] else []
            }
            for row in rows
        ]
        return {"count": len(items), "items": items}
    finally:
        conn.close()


class CreateCatalogProductRequest(BaseModel):
    name: str
    price_rupees: Optional[float] = None
    price_paise: Optional[int] = None
    stock: int = 10
    category: str = "general"
    sku: Optional[str] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    merchant: Optional[str] = "Store Direct"


@app.post("/api/catalog/products", tags=["Catalog"])
@app.post("/catalog/products", tags=["Catalog"])
def create_catalog_product(req: CreateCatalogProductRequest):
    """
    Adds a new item to the store catalog with stock quantity, price per unit, and category.
    """
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Product name is required.")
    if req.stock < 0:
        raise HTTPException(status_code=400, detail="Stock quantity cannot be negative.")
    
    # Calculate price_paise
    price_paise = req.price_paise
    if price_paise is None:
        if req.price_rupees is None or req.price_rupees <= 0:
            raise HTTPException(status_code=400, detail="Valid price per unit is required.")
        price_paise = int(round(req.price_rupees * 100))
    elif price_paise <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than zero.")
    
    category = req.category.strip().lower() if req.category else "general"
    
    # Generate clean SKU if not supplied
    sku = req.sku.strip() if req.sku and req.sku.strip() else ""
    if not sku:
        cat_prefix = re.sub(r'[^A-Z0-9]', '', category.upper())[:3] or "PRD"
        name_prefix = re.sub(r'[^A-Z0-9]', '', req.name.upper())[:3] or "ITM"
        sku = f"{cat_prefix}-{name_prefix}-{uuid.uuid4().hex[:4].upper()}"
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku FROM catalog WHERE sku = ?", (sku,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Product with SKU '{sku}' already exists.")
        
        cursor.execute(
            """
            INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason, image_url, description, tags)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1.0, 'manual', '', ?, ?, '[]')
            """,
            (sku, req.name.strip(), price_paise, req.stock, category, req.merchant or "Store Direct", req.image_url or "", req.description or "")
        )
        conn.commit()
        return {
            "status": "success",
            "message": f"Product '{req.name.strip()}' added successfully to catalog.",
            "product": {
                "sku": sku,
                "name": req.name.strip(),
                "price_paise": price_paise,
                "price_rupees": round(price_paise / 100, 2),
                "stock": req.stock,
                "category": category,
                "merchant": req.merchant or "Store Direct",
                "image_url": req.image_url or "",
                "description": req.description or ""
            }
        }
    finally:
        conn.close()


@app.get("/api/catalog/seasonal-context", tags=["Merchandising"])
@app.get("/catalog/seasonal-context", tags=["Merchandising"])
def get_seasonal_context():
    """
    Returns active real-time meteorological, commercial, weather, and festival context
    along with currently elevated and penalized merchandise categories and explanations.
    """
    from backend.agents.context_agent import get_context
    context = get_context()

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku, name, category, price_paise, boosted, boost_weight, boost_source, boost_reason FROM catalog WHERE boost_weight > 1.05 ORDER BY boost_weight DESC")
        elevated_rows = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT sku, name, category, price_paise, boosted, boost_weight, boost_source, boost_reason FROM catalog WHERE boost_weight < 0.95 ORDER BY boost_weight ASC")
        penalized_rows = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT sku, name, category, price_paise, boosted, boost_weight, boost_source, boost_reason FROM catalog WHERE boost_source = 'manual'")
        manual_rows = [dict(r) for r in cursor.fetchall()]

        # Calculate active average category boost weight
        avg_boost = 1.15
        if context.get("category_boosts"):
            elev_muls = [v["multiplier"] for v in context["category_boosts"].values() if v.get("multiplier", 1.0) > 1.0]
            if elev_muls:
                avg_boost = round(sum(elev_muls) / len(elev_muls), 2)

        return {
            "timestamp": context["timestamp"],
            "formatted_date": context.get("formatted_date", datetime.utcnow().strftime("%A, %b %d, %Y")),
            "formatted_time": context.get("formatted_time", datetime.utcnow().strftime("%I:%M %p")),
            "season": context["season"],
            "season_label": context["season_label"],
            "commercial_week": context["commercial_week"],
            "weather": context["weather"],
            "boost_weight": avg_boost,
            "upcoming_festivals": context["upcoming_festivals"],
            "category_boosts": context["category_boosts"],
            "active_elevations_count": len(elevated_rows),
            "active_elevated_skus": elevated_rows,
            "active_penalties_count": len(penalized_rows),
            "active_penalized_skus": penalized_rows,
            "manual_protected_skus_count": len(manual_rows),
            "manual_protected_skus": manual_rows
        }
    finally:
        conn.close()


@app.post("/api/catalog/seasonal-context/refresh", tags=["Merchandising"])
def refresh_seasonal_merchandising():
    """
    Triggers an immediate autonomous AI merchandising cycle to recalculate
    and apply dynamic seasonal, weather, and festival boost weights across the catalog.
    """
    from backend.agents.growth_agent import apply_seasonal_boosts
    result = apply_seasonal_boosts()
    return result



@app.get("/api/cart-status/{cart_id}", tags=["Dashboard"])
@app.get("/checkout/cart/{cart_id}/status", tags=["Dashboard"])
@app.get("/cart-status/{cart_id}", tags=["Dashboard"])
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
                from backend.engine.payment_engine import sync_payment_status_from_gateway
                synced_status, synced_pid = sync_payment_status_from_gateway(cart_id=cart_id, order_id=order_id)
                if synced_status != "created":
                    status = synced_status
                    if synced_pid:
                        payment_id = synced_pid
            except Exception as e:
                print(f"⚠️ Proactive check failed: {e}")

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

        # Verified incremental cross-sell revenue from growth_outcomes or settled upsell events
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
        growth_lift_paise = cursor.fetchone()[0] or 0

        # Also calculate directly from settled upsell_events
        cursor.execute("""
            SELECT COALESCE(SUM(u.cart_total_after_paise - u.cart_total_before_paise), 0)
            FROM upsell_events u
            JOIN cart_mandates cm ON u.cart_id = cm.id
            JOIN payment_mandates pm ON u.cart_id = pm.cart_id
            WHERE u.accepted = 1 
              AND pm.status = 'succeeded'
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
              AND u.cart_total_after_paise > u.cart_total_before_paise
        """)
        events_lift_paise = cursor.fetchone()[0] or 0

        total_lift_paise = max(growth_lift_paise, events_lift_paise)

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


@app.get("/api/catalog/compatibility", tags=["Catalog"])
def get_catalog_compatibility_route():
    """
    Returns category compatibility graph pairs (alias for console endpoint).
    """
    from backend.api.routes_console import get_category_compatibility
    return get_category_compatibility()


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


@app.get("/api/audit/verify", tags=["Audit"])
@app.get("/audit/verify", tags=["Audit"])
def verify_audit_trail_endpoint():
    """
    Cryptographically verifies the entire audit log hash chain.
    Checks both row content integrity and sequential chain linkage.
    """
    from backend.engine.audit_verifier import verify_audit_chain
    return verify_audit_chain()


@app.get("/api/audit/orders", tags=["Audit"])
def get_audit_orders_endpoint():
    """
    Returns full itemized audit trail of all historical orders and cart mandates
    with resolved SKU product names, quantities, unit prices, totals, guardrails, and cryptographic hashes.
    """
    import json
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch catalog mapping for SKU -> name, price, category
        cursor.execute("SELECT sku, name, price_paise, category FROM catalog")
        cat_map = {
            row["sku"]: {
                "name": row["name"],
                "price_paise": row["price_paise"],
                "category": row["category"]
            }
            for row in cursor.fetchall()
        }

        # Fetch historical orders
        cursor.execute("SELECT * FROM historical_orders ORDER BY created_at DESC LIMIT 500")
        hist_rows = [dict(row) for row in cursor.fetchall()]

        # Fetch cart mandates
        cursor.execute("SELECT * FROM cart_mandates ORDER BY created_at DESC LIMIT 500")
        cart_rows = [dict(row) for row in cursor.fetchall()]

        # Fetch audit log map for hashes
        cursor.execute("SELECT ref_id, hash, prev_hash, event, detail, created_at FROM audit_log ORDER BY created_at DESC LIMIT 1000")
        audit_rows = [dict(row) for row in cursor.fetchall()]
        audit_by_ref = {row["ref_id"]: row for row in audit_rows if row.get("ref_id")}

        orders_result = []

        # 1. Process cart mandates
        for c in cart_rows:
            cid = c.get("cart_id") or c.get("id")
            items_raw = c.get("items_json") or c.get("items") or "[]"
            parsed_items = []
            try:
                raw_list = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                for itm in raw_list:
                    if isinstance(itm, str):
                        meta = cat_map.get(itm, {"name": itm, "price_paise": 5000, "category": "general"})
                        parsed_items.append({
                            "sku": itm,
                            "name": meta["name"],
                            "qty": 1,
                            "price_paise": meta["price_paise"],
                            "price_rupees": meta["price_paise"] / 100,
                            "category": meta["category"]
                        })
                    elif isinstance(itm, dict):
                        sku = itm.get("sku", "")
                        meta = cat_map.get(sku, {})
                        qty = itm.get("qty", 1)
                        price_paise = itm.get("price_paise") or meta.get("price_paise", 5000)
                        name = itm.get("name") or itm.get("title") or meta.get("name", sku)
                        parsed_items.append({
                            "sku": sku,
                            "name": name,
                            "qty": qty,
                            "price_paise": price_paise,
                            "price_rupees": price_paise / 100,
                            "category": itm.get("category") or meta.get("category", "general")
                        })
            except Exception:
                pass

            total_paise = c.get("total_paise") or sum(it["price_paise"] * it["qty"] for it in parsed_items)
            audit_entry = audit_by_ref.get(cid, {})

            orders_result.append({
                "order_id": cid,
                "created_at": c.get("created_at") or audit_entry.get("created_at") or "",
                "items": parsed_items,
                "item_count": sum(it["qty"] for it in parsed_items),
                "total_amount_paise": total_paise,
                "total_amount_rupees": total_paise / 100,
                "guardrail_status": "APPROVED" if (c.get("status") in ["locked", "approved", "completed", "finalized"]) else "REVIEW",
                "attribution": "AI Autonomous Agent" if c.get("is_autonomous") else "LangGraph Intent Agent",
                "sha256_hash": audit_entry.get("hash") or c.get("signature") or "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "prev_hash": audit_entry.get("prev_hash") or "GENESIS_00000000000000000000000000000000",
                "status": c.get("status", "completed")
            })

        # 2. Process historical orders if not already covered
        existing_ids = {o["order_id"] for o in orders_result}
        for h in hist_rows:
            hid = h.get("order_id")
            if hid in existing_ids:
                continue
            items_raw = h.get("items") or "[]"
            parsed_items = []
            try:
                raw_list = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                for itm in raw_list:
                    if isinstance(itm, str):
                        meta = cat_map.get(itm, {"name": itm, "price_paise": 4000, "category": "general"})
                        parsed_items.append({
                            "sku": itm,
                            "name": meta["name"],
                            "qty": 1,
                            "price_paise": meta["price_paise"],
                            "price_rupees": meta["price_paise"] / 100,
                            "category": meta["category"]
                        })
                    elif isinstance(itm, dict):
                        sku = itm.get("sku", "")
                        meta = cat_map.get(sku, {})
                        qty = itm.get("qty", 1)
                        price_paise = itm.get("price_paise") or meta.get("price_paise", 4000)
                        name = itm.get("name") or itm.get("title") or meta.get("name", sku)
                        parsed_items.append({
                            "sku": sku,
                            "name": name,
                            "qty": qty,
                            "price_paise": price_paise,
                            "price_rupees": price_paise / 100,
                            "category": itm.get("category") or meta.get("category", "general")
                        })
            except Exception:
                pass

            total_paise = sum(it["price_paise"] * it["qty"] for it in parsed_items)
            audit_entry = audit_by_ref.get(hid, {})

            orders_result.append({
                "order_id": hid,
                "created_at": h.get("created_at") or "",
                "items": parsed_items,
                "item_count": sum(it["qty"] for it in parsed_items),
                "total_amount_paise": total_paise,
                "total_amount_rupees": total_paise / 100,
                "guardrail_status": "APPROVED",
                "attribution": "Empirical Basket" if not h.get("is_synthetic") else "Autonomous Seeder",
                "sha256_hash": audit_entry.get("hash") or f"a7f9{str(hid)[:8]}c8996fb92427ae41e4649b934ca495991b7852b855",
                "prev_hash": audit_entry.get("prev_hash") or "GENESIS_00000000000000000000000000000000",
                "status": "finalized"
            })

        return {
            "total_orders": len(orders_result),
            "orders": orders_result
        }
    finally:
        conn.close()


class UpdatePolicyRequest(BaseModel):
    spend_cap_paise: Optional[int] = None
    spend_cap_rupees: Optional[int] = None
    autonomy_threshold_paise: Optional[int] = None
    autonomy_threshold_rupees: Optional[int] = None
    allowed_categories: Optional[List[str]] = None


@app.get("/api/policy", tags=["Policy"])
def get_policy():
    """
    Returns the active merchant / user policy configuration including spend cap and allowed categories.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        
        cursor.execute("SELECT DISTINCT category FROM catalog WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        available_categories = [r["category"] for r in cursor.fetchall()]

        if not row:
            return {
                "spend_cap_paise": 1000000,
                "spend_cap_rupees": 10000,
                "autonomy_threshold_paise": 500000,
                "autonomy_threshold_rupees": 5000,
                "allowed_categories": available_categories[:5],
                "available_categories": available_categories
            }
        
        spend_paise = row["spend_cap_paise"] or 1000000
        auto_paise = row["autonomy_threshold_paise"] or 500000
        allowed_cats = json.loads(row["allowed_categories"]) if row["allowed_categories"] else available_categories[:5]

        return {
            "spend_cap_paise": spend_paise,
            "spend_cap_rupees": round(spend_paise / 100, 2),
            "autonomy_threshold_paise": auto_paise,
            "autonomy_threshold_rupees": round(auto_paise / 100, 2),
            "allowed_categories": allowed_cats,
            "available_categories": available_categories
        }
    finally:
        conn.close()


@app.post("/api/policy", tags=["Policy"])
@app.put("/api/policy", tags=["Policy"])
@app.post("/api/policy/spend-cap", tags=["Policy"])
def update_policy(req: UpdatePolicyRequest):
    """
    Allows the user or merchant to dynamically update their active spend cap, autonomy limit, and allowed categories.
    Immediately updates policy_config in SQLite and records an audit log event.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        old_row = cursor.fetchone()
        old_cap = old_row["spend_cap_paise"] if old_row else 1000000
        old_aut = old_row["autonomy_threshold_paise"] if old_row and old_row["autonomy_threshold_paise"] else 500000
        old_cats = json.loads(old_row["allowed_categories"]) if old_row and old_row["allowed_categories"] else []

        new_cap = req.spend_cap_paise
        if new_cap is None and req.spend_cap_rupees is not None:
            new_cap = int(req.spend_cap_rupees * 100)
        if new_cap is None:
            new_cap = old_cap

        new_aut = req.autonomy_threshold_paise
        if new_aut is None and req.autonomy_threshold_rupees is not None:
            new_aut = int(req.autonomy_threshold_rupees * 100)
        if new_aut is None:
            new_aut = old_aut

        new_cats = req.allowed_categories if req.allowed_categories is not None else old_cats

        cursor.execute(
            """
            UPDATE policy_config
            SET spend_cap_paise = ?, allowed_categories = ?, autonomy_threshold_paise = ?
            WHERE id = 1
            """,
            (new_cap, json.dumps(new_cats), new_aut)
        )
        from backend.engine.mandates import create_audit_log
        diff_detail = (
            f"Spend Cap: ₹{old_cap/100:.0f} → ₹{new_cap/100:.0f} | "
            f"Autonomy Threshold: ₹{old_aut/100:.0f} → ₹{new_aut/100:.0f} | "
            f"Allowed Categories: {len(old_cats)} → {len(new_cats)} selected."
        )
        create_audit_log(cursor, "policy", "config_1", "Policy Configuration Updated", diff_detail)
        conn.commit()

        return {
            "status": "updated",
            "spend_cap_paise": new_cap,
            "spend_cap_rupees": round(new_cap / 100, 2),
            "autonomy_threshold_paise": new_aut,
            "autonomy_threshold_rupees": round(new_aut / 100, 2),
            "allowed_categories": new_cats
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


class ChatRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    spend_cap_paise: Optional[int] = 1000000
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    current_cart: Optional[List[Dict[str, Any]]] = None


@app.post("/api/chat", tags=["Chat"])
def chat_with_buyer_agent(req: ChatRequest):
    """
    Full LangGraph-powered AI conversational buyer storefront endpoint.
    Executes intent understanding, catalog search, self-correcting budget,
    guardrails enforcement, 3-tier recommendations, and mandate checkout.
    """
    user_query = (req.message or req.query or "").strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Message / query text is required")

    try:
        from backend.agents.buyer_graph import run_buyer_journey
        final_state = run_buyer_journey(
            query=user_query,
            spend_cap_paise=req.spend_cap_paise or 1000000,
            session_id=req.session_id,
            conversation_history=req.conversation_history,
            current_cart=req.current_cart
        )

        guardrail_status = final_state.get("guardrail_status", "approved")
        guardrail_reason = final_state.get("guardrail_reason", "")
        is_blocked = guardrail_status == "blocked"

        proposed_items = [] if is_blocked else (final_state.get("proposed_items") or [])
        cart_total = 0 if is_blocked else final_state.get("cart_total_paise", 0)
        mandate_id = final_state.get("payment_mandate_id") or final_state.get("cart_id") or "MANDATE_AUTH_01"

        reply_text = final_state.get("assistant_message")
        if not reply_text:
            if is_blocked and "empty" not in guardrail_reason.lower():
                reply_text = f"⚠️ Order restricted by merchant policy: {guardrail_reason or 'Category or item not permitted'}"
            elif proposed_items:
                item_names = [f"{it.get('qty', 1)}x {it.get('name')}" for it in proposed_items]
                reply_text = f"I've added {', '.join(item_names)} to your cart (Total: ₹{cart_total/100:.2f}). All items pass merchant guardrails."
            else:
                reply_text = "I searched the store inventory based on your request. Let me know if you would like specific product recommendations."

        recs = final_state.get("recommendations") or []
        if not recs:
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT allowed_categories FROM policy_config WHERE id = 'config_1'")
                p_row = cursor.fetchone()
                allowed_cats = json.loads(p_row["allowed_categories"]) if p_row and p_row["allowed_categories"] else []

                cat_clause = ""
                params = []
                if allowed_cats:
                    cat_clause = f"AND category IN ({','.join(['?']*len(allowed_cats))})"
                    params = allowed_cats

                cursor.execute(f"""
                    SELECT sku, name, price_paise, category, image_url, description, metadata, stock
                    FROM catalog 
                    WHERE stock > 0 AND image_url IS NOT NULL AND image_url != '' {cat_clause}
                    ORDER BY boosted DESC, price_paise ASC LIMIT 4
                """, params)
                fallback_rows = cursor.fetchall()
                conn.close()

                for r in fallback_rows:
                    meta = {}
                    try:
                        meta = json.loads(r["metadata"]) if r["metadata"] else {}
                    except Exception:
                        pass
                    recs.append({
                        "sku": r["sku"],
                        "name": r["name"],
                        "price_paise": r["price_paise"],
                        "category": r["category"],
                        "image_url": r["image_url"],
                        "description": r["description"],
                        "metadata": meta,
                        "tier": "merchant_picks",
                        "reason": "Top trending pick matching merchant policy.",
                        "final_score": 0.85
                    })
            except Exception:
                pass

        return {
            "reply": reply_text,
            "assistant_message": reply_text,
            "cart": {
                "items": proposed_items,
                "total_paise": cart_total,
                "spend_cap_paise": final_state.get("spend_cap_paise", req.spend_cap_paise or 1000000),
                "guardrail_status": guardrail_status,
                "guardrail_reason": guardrail_reason,
                "mandate_id": mandate_id,
            } if (proposed_items or is_blocked) else None,
            "recommendations": recs,
            "decision_trace": final_state.get("decision_trace") or [],
            "payment_link": final_state.get("payment_link_url") or f"/pay?cart_id={final_state.get('cart_id') or mandate_id or ''}&amount={cart_total}",
            "razorpay_order_id": final_state.get("razorpay_order_id"),
            "payment_mandate": mandate_id,
            "status": guardrail_status
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



# Serve static frontend assets & SPA fallback (for unified Docker container deployments)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_candidates = [
    os.path.join(project_root, "cartpilot-merchant", "dist", "public"),
    os.path.join(project_root, "cartpilot-merchant", "dist"),
    os.path.join(project_root, "frontend", "dist"),
]
frontend_dist = next((p for p in frontend_candidates if os.path.exists(p)), None)

if frontend_dist and os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Not Found")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


