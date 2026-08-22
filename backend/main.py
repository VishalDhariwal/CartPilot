import uvicorn
from fastapi import FastAPI
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

# Setup database on startup
@app.on_event("startup")
def startup_event():
    print("Initializing Database...")
    init_db()

# Include routers
app.include_router(routes_checkout.router, prefix="/checkout", tags=["Checkout"])
app.include_router(routes_webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(routes_resolution.router, prefix="/resolution", tags=["Resolution"])
app.include_router(routes_recovery.router, prefix="/recovery", tags=["Recovery"])


@app.get("/catalog", tags=["Catalog"])
def get_catalog():
    """
    Agent-readable catalog endpoint.
    Returns the full merchant catalog as structured JSON.
    Any AI buyer agent can query this to discover available SKUs.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT sku, name, price_paise, stock, category, merchant FROM catalog ORDER BY category, name"
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


@app.get("/api/dashboard", tags=["Dashboard"])
def get_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch intents (newest first for display)
        cursor.execute("SELECT * FROM intent_mandates ORDER BY created_at DESC")
        intents = [dict(row) for row in cursor.fetchall()]

        # Fetch all carts
        cursor.execute("SELECT * FROM cart_mandates ORDER BY created_at ASC")
        carts = [dict(row) for row in cursor.fetchall()]

        # Fetch all payments
        cursor.execute("SELECT * FROM payment_mandates ORDER BY created_at ASC")
        payments = [dict(row) for row in cursor.fetchall()]

        # Fetch all audit logs
        cursor.execute("SELECT * FROM audit_log ORDER BY created_at ASC")
        logs = [dict(row) for row in cursor.fetchall()]

        return {
            "intents": intents,
            "carts": carts,
            "payments": payments,
            "audit_logs": logs,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    print("Starting CartPilot Server...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
