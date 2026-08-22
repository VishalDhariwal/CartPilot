import json
from typing import Optional
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.db import init_db, get_db
from backend.api import routes_checkout, routes_webhook, routes_resolution, routes_recovery



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
            # Refresh association lift pairs
            from backend.recommendations.lift_engine import compute_lift_pairs
            compute_lift_pairs()
    except Exception as e:
        print(f"⚠️ Error during startup sync: {e}")

    # Precompute missing catalog embeddings in background thread
    import threading
    def _bg_embeddings():
        try:
            from backend.recommendations.embedding_engine import precompute_catalog_embeddings
            precompute_catalog_embeddings(force=False)
        except Exception as e:
            print(f"⚠️ Error precomputing catalog embeddings: {e}")

    threading.Thread(target=_bg_embeddings, daemon=True).start()


# Include routers
app.include_router(routes_checkout.router, prefix="/checkout", tags=["Checkout"])
app.include_router(routes_webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(routes_resolution.router, prefix="/resolution", tags=["Resolution"])
app.include_router(routes_recovery.router, prefix="/recovery", tags=["Recovery"])


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

        # If still waiting in 'created' state, proactively check Razorpay API!
        if status == "created" and order_id:
            try:
                from backend.integrations.razorpay_client import client
                from backend.engine.mandates import update_payment_mandate_status

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
    Reads from upsell_events table — the real, measured numbers.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM upsell_events")
        total_offered = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM upsell_events WHERE accepted = 1")
        total_accepted = cursor.fetchone()[0]

        acceptance_rate = round((total_accepted / total_offered * 100), 1) if total_offered > 0 else 0.0

        cursor.execute(
            "SELECT AVG(cart_total_after_paise - cart_total_before_paise) FROM upsell_events WHERE accepted = 1"
        )
        avg_uplift_row = cursor.fetchone()[0]
        avg_uplift_paise = round(avg_uplift_row) if avg_uplift_row else 0

        return {
            "total_offered": total_offered,
            "total_accepted": total_accepted,
            "total_declined": total_offered - total_accepted,
            "acceptance_rate_pct": acceptance_rate,
            "avg_uplift_paise": avg_uplift_paise,
            "avg_uplift_rupees": round(avg_uplift_paise / 100, 2),
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
        cursor.execute("SELECT * FROM intent_mandates ORDER BY created_at DESC LIMIT 50")
        intents = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM cart_mandates ORDER BY created_at DESC LIMIT 50")
        carts = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM payment_mandates ORDER BY created_at DESC LIMIT 50")
        payments = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100")
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


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

