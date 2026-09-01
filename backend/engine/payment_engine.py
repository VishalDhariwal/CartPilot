import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from backend.db import get_db
from backend.engine.mandates import create_audit_log, update_payment_mandate_status
from backend.integrations import razorpay_client


class CartAlreadyConsumedError(Exception):
    """Raised when an approved cart mandate has already been consumed by a prior payment."""
    pass


class CartMandateExpiredError(Exception):
    """Raised when a cart mandate has exceeded its time-to-live (TTL)."""
    pass


class CartMandateNotApprovedError(Exception):
    """Raised when a payment is attempted against an unapproved or blocked cart mandate."""
    pass


class JITInventoryError(Exception):
    """Raised when inventory or catalog prices have drifted since cart mandate creation."""
    pass


def execute_payment_mandate(
    cart_id: str,
    description: str = "CartPilot Order",
    notes: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Authoritative Payment Choke Point:
    The ONLY approved system component permitted to interact with the Razorpay API.
    
    Enforces the following strict invariant chain:
      1. Verifies cart existence and status == 'approved'.
      2. Enforces mandate expiration (expires_at > now).
      3. Performs Just-In-Time (JIT) stock and price validation against live catalog.
      4. Executes SQLite-native atomic single-use check-and-set on cart_mandates.consumed_at.
      5. Generates Razorpay Order & Payment Link via razorpay_client.
      6. Inserts payment_mandates record (protected by UNIQUE(cart_id) database constraint).
      7. Records cryptographically hash-chained audit trail entry in the same transaction.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"

        # 1. Fetch Cart Mandate
        cursor.execute(
            "SELECT id, intent_id, items, total_paise, status, reason, expires_at, consumed_at FROM cart_mandates WHERE id = ?",
            (cart_id,)
        )
        cart = cursor.fetchone()
        if not cart:
            raise ValueError(f"Cart mandate '{cart_id}' not found.")

        # 2. Check Mandate Approvals & Expiry
        if cart["status"] != "approved":
            raise CartMandateNotApprovedError(
                f"Cannot create payment for cart '{cart_id}' with status '{cart['status']}'. Reason: {cart['reason']}"
            )

        if cart["consumed_at"]:
            raise CartAlreadyConsumedError(
                f"Cart mandate '{cart_id}' was already consumed at {cart['consumed_at']}."
            )

        if cart["expires_at"] and cart["expires_at"] <= now_iso:
            raise CartMandateExpiredError(
                f"Cart mandate '{cart_id}' expired at {cart['expires_at']} (current time: {now_iso}). Please re-validate your cart."
            )

        # 3. JIT Inventory & Price Re-check
        items_raw = cart["items"]
        cart_items = json.loads(items_raw) if isinstance(items_raw, str) else (items_raw or [])
        
        for it in cart_items:
            sku = it.get("sku")
            qty = it.get("qty", 1)
            cursor.execute("SELECT name, price_paise, stock FROM catalog WHERE sku = ?", (sku,))
            cat_row = cursor.fetchone()
            if not cat_row:
                raise JITInventoryError(f"SKU '{sku}' was removed from the catalog before checkout could complete.")
            if cat_row["stock"] < qty:
                raise JITInventoryError(
                    f"Insufficient stock for '{cat_row['name']}' ({sku}) at payment execution: available {cat_row['stock']}, requested {qty}."
                )
            if cat_row["price_paise"] != it.get("price_paise"):
                raise JITInventoryError(
                    f"Price changed for '{cat_row['name']}' ({sku}) from ₹{it.get('price_paise', 0)/100:.2f} to ₹{cat_row['price_paise']/100:.2f}."
                )

        # 4. Atomic Check-and-Set: Consume the mandate
        cursor.execute(
            """
            UPDATE cart_mandates
            SET consumed_at = ?
            WHERE id = ? 
              AND consumed_at IS NULL 
              AND status = 'approved' 
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (now_iso, cart_id, now_iso)
        )
        if cursor.rowcount == 0:
            raise CartAlreadyConsumedError(
                f"Concurrent transaction detected: Cart mandate '{cart_id}' was consumed or expired during checkout."
            )

        # 5. Call Razorpay API
        total_paise = cart["total_paise"]
        order_notes = notes or {}
        order_notes["cart_id"] = cart_id
        order_notes["intent_id"] = cart["intent_id"]

        receipt_id = f"rcpt_{cart_id[-10:]}"
        rzp_order = razorpay_client.create_order(
            amount_paise=total_paise,
            receipt_id=receipt_id,
            notes=order_notes
        )
        razorpay_order_id = rzp_order["id"]

        rzp_link = razorpay_client.create_payment_link(
            amount_paise=total_paise,
            order_id=razorpay_order_id,
            cart_id=cart_id,
            description=description
        )
        payment_link_url = rzp_link.get("short_url") or f"https://rzp.io/i/mock_{uuid.uuid4().hex[:8]}"

        # 6. Insert Payment Mandate (Unique constraint on cart_id protects against race conditions)
        pay_id = f"pay_{uuid.uuid4().hex}"
        try:
            cursor.execute(
                """
                INSERT INTO payment_mandates 
                (id, cart_id, razorpay_order_id, amount_paise, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'created', ?, ?)
                """,
                (pay_id, cart_id, razorpay_order_id, total_paise, now_iso, now_iso)
            )
        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or "unique" in str(e).lower():
                raise CartAlreadyConsumedError(f"Duplicate payment prevented: cart '{cart_id}' already has a payment mandate.")
            raise

        # Link consumed payment ID on cart mandate
        cursor.execute(
            "UPDATE cart_mandates SET consumed_by_payment_id = ? WHERE id = ?",
            (pay_id, cart_id)
        )

        # 7. Record Hash-Chained Audit Log
        create_audit_log(
            cursor,
            "payment",
            pay_id,
            "Payment Mandate Created",
            f"Razorpay Order '{razorpay_order_id}' created for cart '{cart_id}' (₹{total_paise/100:.2f}). Checkout link: {payment_link_url}"
        )

        conn.commit()

        return {
            "success": True,
            "payment_mandate_id": pay_id,
            "cart_id": cart_id,
            "razorpay_order_id": razorpay_order_id,
            "payment_link_url": payment_link_url,
            "amount_paise": total_paise,
            "amount_rupees": round(total_paise / 100, 2),
            "status": "created",
            "created_at": now_iso
        }
    finally:
        conn.close()


def execute_refund_payment(payment_id: str, amount_paise: int) -> dict:
    """
    Authoritative Refund Gateway Choke Point:
    Invokes Razorpay refund API via payment_engine.
    """
    return razorpay_client.refund_payment(payment_id, amount_paise)


def sync_payment_status_from_gateway(cart_id: str, order_id: str) -> tuple[str, Optional[str]]:
    """
    Proactively checks gateway status for a pending order and synchronizes payment mandates.
    Returns (status, payment_id).
    """
    if razorpay_client.is_bypass_mode() or str(order_id).startswith("order_mock_"):
        mock_payment_id = f"pay_mock_{uuid.uuid4().hex[:14]}"
        update_payment_mandate_status(
            razorpay_order_id=order_id,
            cart_id=cart_id,
            status="succeeded",
            payment_id=mock_payment_id
        )
        return "succeeded", mock_payment_id
    elif razorpay_client.client:
        try:
            payments_resp = razorpay_client.client.order.payments(order_id)
            items = payments_resp.get("items", [])

            if not items:
                recent = razorpay_client.client.payment.all({"count": 10})
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
                    return "succeeded", p_id
                elif p_status == "failed":
                    err_desc = p.get("error_description", "Payment failed at gateway.")
                    update_payment_mandate_status(
                        razorpay_order_id=order_id,
                        cart_id=cart_id,
                        status="failed",
                        failure_reason=err_desc,
                        payment_id=p_id
                    )
                    return "failed", p_id
        except Exception as e:
            print(f"⚠️ Proactive payment sync check failed: {e}")

    return "created", None


