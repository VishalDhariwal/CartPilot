import json
from datetime import datetime
import uuid
from backend.db import get_db

def create_audit_log(cursor, ref_type: str, ref_id: str, event: str, detail: str):
    cursor.execute(
        "INSERT INTO audit_log (ref_type, ref_id, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (ref_type, ref_id, event, detail, datetime.utcnow().isoformat() + "Z")
    )

def create_intent_mandate(raw_request: str, goal: str, spend_cap_paise: int, channel: str = "web_chat") -> dict:
    conn = get_db()
    cursor = conn.cursor()
    try:
        intent_id = f"intent_{uuid.uuid4().hex}"
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute(
            "INSERT INTO intent_mandates (id, raw_request, goal, spend_cap_paise, channel, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (intent_id, raw_request, goal, spend_cap_paise, channel, created_at)
        )
        create_audit_log(cursor, "intent", intent_id, "Intent Created", f"Goal: {goal}, Cap: {spend_cap_paise} paise, Channel: {channel}")
        
        conn.commit()
        return {
            "id": intent_id,
            "raw_request": raw_request,
            "goal": goal,
            "spend_cap_paise": spend_cap_paise,
            "channel": channel,
            "created_at": created_at
        }
    finally:
        conn.close()

def create_cart_mandate(intent_id: str, items: list, total_paise: int, status: str, reason: str, reversible: bool) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cart_id = f"cart_{uuid.uuid4().hex}"
        created_at = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute(
            "INSERT INTO cart_mandates (id, intent_id, items, total_paise, status, reason, reversible, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cart_id, intent_id, json.dumps(items), total_paise, status, reason, 1 if reversible else 0, created_at)
        )
        
        event_name = "Cart Approved" if status == "approved" else "Cart Blocked"
        create_audit_log(cursor, "cart", cart_id, event_name, reason)
        
        conn.commit()
        return {
            "id": cart_id,
            "intent_id": intent_id,
            "items": items,
            "total_paise": total_paise,
            "status": status,
            "reason": reason,
            "reversible": reversible,
            "created_at": created_at
        }
    finally:
        conn.close()

def create_payment_mandate(cart_id: str, razorpay_order_id: str, amount_paise: int) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    try:
        pay_id = f"pay_{uuid.uuid4().hex}"
        created_at = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute(
            "INSERT INTO payment_mandates (id, cart_id, razorpay_order_id, amount_paise, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pay_id, cart_id, razorpay_order_id, amount_paise, "created", created_at, created_at)
        )
        
        create_audit_log(cursor, "payment", pay_id, "Payment Mandate Created", f"Order ID: {razorpay_order_id}, Amount: {amount_paise}")
        
        conn.commit()
        return {
            "id": pay_id,
            "cart_id": cart_id,
            "razorpay_order_id": razorpay_order_id,
            "amount_paise": amount_paise,
            "status": "created",
            "created_at": created_at
        }
    finally:
        conn.close()

def update_payment_mandate_status(razorpay_order_id: str = None, cart_id: str = None, status: str = "succeeded", failure_reason: str = None, payment_id: str = None, recovery_action: str = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        row = None
        if razorpay_order_id:
            cursor.execute("SELECT id, cart_id, status FROM payment_mandates WHERE razorpay_order_id = ?", (razorpay_order_id,))
            row = cursor.fetchone()
        if not row and cart_id:
            cursor.execute("SELECT id, cart_id, status FROM payment_mandates WHERE cart_id = ?", (cart_id,))
            row = cursor.fetchone()
            
        if not row:
            return None
        
        pay_id = row["id"]
        associated_cart_id = row["cart_id"]

        # If already in desired status with same payment_id, don't duplicate audit log
        if row["status"] == status and status == "succeeded":
            return pay_id
            
        updated_at = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute(
            "UPDATE payment_mandates SET status = ?, failure_reason = ?, razorpay_payment_id = COALESCE(?, razorpay_payment_id), recovery_action = COALESCE(?, recovery_action), updated_at = ? WHERE id = ?",
            (status, failure_reason, payment_id, recovery_action, updated_at, pay_id)
        )
        
        event_name = f"Payment {status.capitalize()}"
        detail = failure_reason if failure_reason else f"Payment succeeded with ID {payment_id}"
        create_audit_log(cursor, "payment", pay_id, event_name, detail)
        
        # When payment succeeds, feed real order data into historical_orders (is_synthetic = 0)
        if status == "succeeded" and associated_cart_id:
            try:
                cursor.execute("SELECT items FROM cart_mandates WHERE id = ?", (associated_cart_id,))
                cart_row = cursor.fetchone()
                if cart_row and cart_row["items"]:
                    cart_items = json.loads(cart_row["items"])
                    skus = [item["sku"] for item in cart_items if "sku" in item]
                    if len(skus) >= 1:
                        cursor.execute(
                            """INSERT OR REPLACE INTO historical_orders (order_id, items, is_synthetic, created_at)
                               VALUES (?, ?, 0, ?)""",
                            (f"real_{pay_id}", json.dumps(skus), updated_at)
                        )
            except Exception as e:
                print(f"Error logging real order to historical_orders: {e}")

        conn.commit()

        # Recompute lift pairs with newly added real order data
        if status == "succeeded":
            try:
                from backend.recommendations.lift_engine import compute_lift_pairs
                compute_lift_pairs()
            except Exception as e:
                print(f"Error recomputing lift pairs: {e}")

        return pay_id
    finally:
        conn.close()



def get_cart_state(cart_id: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM cart_mandates WHERE id = ?", (cart_id,))
        cart = cursor.fetchone()
        if not cart:
            return None
            
        cursor.execute("SELECT * FROM intent_mandates WHERE id = ?", (cart["intent_id"],))
        intent = cursor.fetchone()

        cursor.execute("SELECT * FROM payment_mandates WHERE cart_id = ?", (cart_id,))
        payment = cursor.fetchone()
        
        return {
            "intent": dict(intent) if intent else None,
            "cart": dict(cart),
            "payment": dict(payment) if payment else None
        }
    finally:
        conn.close()

def get_recovery_message(cart_id: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, failure_reason, recovery_action FROM payment_mandates WHERE cart_id = ?", (cart_id,))
        payment = cursor.fetchone()
        if not payment:
            return None
        return dict(payment)
    finally:
        conn.close()

def append_audit_log(ref_type: str, ref_id: str, event_name: str, detail: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        create_audit_log(cursor, ref_type, ref_id, event_name, detail)
        conn.commit()
    finally:
        conn.close()

def execute_refund(cart_id: str) -> dict:
    """
    Validates state and executes the Razorpay refund, then updates DB.
    """
    from backend.integrations.razorpay_client import refund_payment
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Get current state
        state = get_cart_state(cart_id)
        if not state or not state["payment"]:
            raise ValueError("Cart or Payment Mandate not found")
            
        cart = state["cart"]
        payment = state["payment"]
        
        if not cart["reversible"]:
            raise ValueError("Cart is no longer reversible")
            
        if payment["status"] != "succeeded" or not payment["razorpay_payment_id"]:
            raise ValueError("Payment is not in a refundable state (must be succeeded with a payment ID)")
            
        if payment["recovery_action"] == "refunded":
            raise ValueError("Payment is already refunded")
            
        # Call Razorpay
        refund_response = refund_payment(payment["razorpay_payment_id"], payment["amount_paise"])
        
        # Update Database
        updated_at = datetime.utcnow().isoformat() + "Z"
        
        # 1. Update Payment Mandate
        cursor.execute(
            "UPDATE payment_mandates SET recovery_action = ?, updated_at = ? WHERE id = ?",
            ("refunded", updated_at, payment["id"])
        )
        
        # 2. Update Cart Mandate
        cursor.execute(
            "UPDATE cart_mandates SET reversible = 0 WHERE id = ?",
            (cart["id"],)
        )
        
        # 3. Log it
        create_audit_log(cursor, "payment", payment["id"], "Payment Refunded", f"Refund ID: {refund_response.get('id')} for {payment['amount_paise']} paise")
        create_audit_log(cursor, "cart", cart["id"], "Cart Cancelled", "Reversible flipped to false due to refund")
        
        conn.commit()
        return refund_response
    finally:
        conn.close()
