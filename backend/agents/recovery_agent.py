import os
import json
import uuid
from datetime import datetime
from pydantic import BaseModel
from backend.db import get_db
from backend.engine.payment_engine import execute_payment_mandate
from backend.engine.mandates import create_audit_log, append_audit_log

class RecoveryMessage(BaseModel):
    message: str

def analyze_failure(raw_error_reason: str) -> dict:
    """
    Translates raw payment errors into friendly, actionable recovery messages using LLM.
    """
    from backend.engine.llm import generate_structured
    
    system_instruction = f"""
    You are an AI Payment Recovery Agent for an e-commerce store.
    A user's payment just failed. The raw error reason from the payment gateway is:
    "{raw_error_reason}"
    
    Your job is to translate this technical error into a short, friendly, and actionable 1-2 sentence message for the user.
    Do not use technical jargon. Tell them exactly what they should do next (e.g. try a different card, check balance, etc).
    """
    try:
        data = generate_structured(
            prompt="Generate the friendly recovery message.",
            schema=RecoveryMessage,
            system_prompt=system_instruction
        )
        return {"recommendation": data.message}
    except Exception:
        return {"recommendation": "Payment could not be completed. Please verify your payment details and retry checkout."}


def detect_recoverable_carts(limit: int = 50) -> list[dict]:
    """
    Dynamically scans the database for recoverable revenue opportunities:
    1. Carts approved by policy where no payment mandate was ever completed (abandoned checkout).
    2. Payment mandates in 'created' or 'failed' status for > 15 minutes.
    
    Returns structured list of recoverable opportunities with transparent heuristic scores.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now = datetime.utcnow()
        recoverable = []

        # Bucket 1: Approved carts with non-empty items and total_paise > 0, no successful payment, non-cancelled AND no recovery link sent
        cursor.execute("""
            SELECT cm.id, cm.items, cm.total_paise, cm.created_at, cm.reason
            FROM cart_mandates cm
            WHERE cm.status = 'approved'
            AND cm.total_paise > 0
            AND cm.items IS NOT NULL
            AND cm.items != '[]'
            AND cm.items != ''
            AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
            AND COALESCE(cm.cancellation_status, 'NONE') != 'CANCELLED'
            AND NOT EXISTS (
                SELECT 1 FROM payment_mandates pm 
                WHERE pm.cart_id = cm.id AND (
                    pm.status = 'succeeded' 
                    OR pm.recovery_action IN ('recovery_link_sent', 'refunded')
                    OR COALESCE(pm.refund_status, 'NONE') IN ('REFUNDED', 'PARTIALLY_REFUNDED', 'REFUND_REQUESTED', 'REFUND_PROCESSING')
                )
            )
            ORDER BY cm.created_at DESC
        """)
        rows = cursor.fetchall()

        for r in rows:
            cart_id = r["id"]
            total_paise = r["total_paise"]
            created_at_str = r["created_at"]
            items_raw = r["items"]
            
            # Check existing payment status if any
            cursor.execute("SELECT status, razorpay_order_id FROM payment_mandates WHERE cart_id = ?", (cart_id,))
            pm_row = cursor.fetchone()
            pay_status = pm_row["status"] if pm_row else "no_payment_initiated"

            # Parse items summary
            items_list = []
            try:
                items_list = json.loads(items_raw) if items_raw else []
            except Exception:
                pass

            if not items_list or total_paise <= 0:
                continue

            item_names = [it.get("name") or it.get("sku", "Item") for it in items_list]
            item_skus = [it.get("sku") for it in items_list if "sku" in it]
            if not item_skus:
                continue
            items_summary = ", ".join(item_names[:3]) + (f" +{len(item_names)-3} more" if len(item_names) > 3 else "")

            # Check stock for items in cart
            in_stock = True
            for sku in item_skus:
                cursor.execute("SELECT stock FROM catalog WHERE sku = ?", (sku,))
                stock_row = cursor.fetchone()
                if stock_row and stock_row["stock"] <= 0:
                    in_stock = False
                    break

            if not in_stock:
                continue  # Skip OOS items

            # Calculate time elapsed and heuristic recovery probability
            try:
                clean_time = created_at_str.replace("Z", "+00:00") if "Z" in created_at_str else created_at_str
                created_dt = datetime.fromisoformat(clean_time)
                # handle naive dt
                if created_dt.tzinfo is not None:
                    created_dt = created_dt.replace(tzinfo=None)
                hours_since = max(0.1, (now - created_dt).total_seconds() / 3600.0)
            except Exception:
                hours_since = 1.0

            # Heuristic time-decay model: benchmark base 38% recovery decaying over 48h
            base_rate = 0.38
            decay = max(0.15, 1.0 - (hours_since / 48.0))
            p_success = round(base_rate * decay, 3)
            confidence = round(min(0.75, max(0.20, p_success * 1.5)), 2)

            if pay_status == "no_payment_initiated":
                rec_title = f"Abandoned Cart (₹{total_paise/100:.2f})"
                rec_reason = f"Cart with {len(items_list)} items was approved by buyer agent but payment was never initiated."
            elif pay_status == "created":
                rec_title = f"Unfinished Checkout (₹{total_paise/100:.2f})"
                rec_reason = f"Payment link was generated {hours_since:.1f}h ago but buyer has not completed capture."
            elif pay_status == "failed":
                rec_title = f"Failed Payment Recovery (₹{total_paise/100:.2f})"
                rec_reason = "Payment failed at gateway. Customer requires reissued checkout link to complete."
            else:
                continue

            recoverable.append({
                "cart_id": cart_id,
                "title": rec_title,
                "explanation": rec_reason,
                "total_paise": total_paise,
                "total_rupees": round(total_paise / 100, 2),
                "items_count": len(items_list),
                "items_summary": items_summary,
                "pay_status": pay_status,
                "created_at": created_at_str,
                "hours_since": round(hours_since, 1),
                "p_success": p_success,
                "confidence": confidence,
                "est_revenue_paise": total_paise,
                "score_label": f"Heuristic: {round(p_success*100, 1)}% time-decay estimate ({hours_since:.1f}h idle)",
                "recommended_action": "Send payment reminder link via Razorpay test rails."
            })

        # Sort by total value descending
        recoverable.sort(key=lambda x: x["total_paise"], reverse=True)
        return recoverable[:limit]
    finally:
        conn.close()


def create_recovery_payment_link(cart_id: str) -> dict:
    """
    Prepares a clean Razorpay test-mode Payment Link for a recoverable cart.
    Reuses existing PaymentEngine choke point.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if an existing payment mandate exists
        cursor.execute("SELECT id, razorpay_order_id, amount_paise FROM payment_mandates WHERE cart_id = ?", (cart_id,))
        pm_row = cursor.fetchone()
        if pm_row:
            pay_id = pm_row["id"]
            razorpay_order_id = pm_row["razorpay_order_id"]
            total_paise = pm_row["amount_paise"]
            payment_url = f"https://rzp.io/i/mock_{pay_id[-8:]}"
            now_str = datetime.utcnow().isoformat() + "Z"
            cursor.execute(
                "UPDATE payment_mandates SET recovery_action = 'recovery_link_sent', updated_at = ? WHERE id = ?",
                (now_str, pay_id)
            )
            create_audit_log(
                cursor,
                "payment",
                pay_id,
                "Cart Recovery Link Reissued",
                f"Reissued existing Razorpay checkout link {payment_url} for abandoned cart {cart_id} (₹{total_paise/100:.2f})"
            )
            conn.commit()
            return {
                "success": True,
                "cart_id": cart_id,
                "payment_id": pay_id,
                "razorpay_order_id": razorpay_order_id,
                "payment_link": payment_url,
                "amount_paise": total_paise,
                "amount_rupees": round(total_paise / 100, 2),
                "message": "Payment recovery reminder link reissued successfully."
            }

        # Otherwise execute fresh payment mandate through PaymentEngine
        pay_res = execute_payment_mandate(
            cart_id=cart_id,
            description="CartPilot Payment Recovery Reminder",
            notes={"cart_id": cart_id, "source": "ai_growth_recovery"}
        )
        return {
            "success": True,
            "cart_id": cart_id,
            "payment_id": pay_res["payment_mandate_id"],
            "razorpay_order_id": pay_res["razorpay_order_id"],
            "payment_link": pay_res["payment_link_url"],
            "amount_paise": pay_res["amount_paise"],
            "amount_rupees": pay_res["amount_rupees"],
            "message": "Payment recovery reminder link created successfully."
        }
    finally:
        conn.close()


def execute_recovery(cart_id: str) -> dict:
    """
    Executes the RECOVER_CART Next Best Action:
    1. Reissues payment link via Razorpay
    2. Writes a growth_actions record marking the action as 'executing'
    3. Records audit log
    """
    link_res = create_recovery_payment_link(cart_id)
    
    # Save to growth_actions
    conn = get_db()
    cursor = conn.cursor()
    try:
        action_id = f"ga_recov_{uuid.uuid4().hex[:10]}"
        now_str = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute("""
            INSERT INTO growth_actions (
                id, action_type, status, opportunity_type, title, explanation,
                affected_ref, est_revenue_paise, confidence, recommended_action,
                execution_ref, mode, created_at, executed_at, notes
            ) VALUES (?, 'RECOVER_CART', 'executing', 'abandoned_cart', ?, ?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?)
        """, (
            action_id,
            f"Recover Cart {cart_id[-8:]}",
            f"Generated payment recovery link {link_res['payment_link']} for ₹{link_res['amount_rupees']}",
            json.dumps({"cart_id": cart_id, "payment_id": link_res["payment_id"]}),
            link_res["amount_paise"],
            0.55,
            "Payment link generated and dispatched to buyer.",
            link_res["payment_id"],
            now_str,
            now_str,
            f"Razorpay Order: {link_res['razorpay_order_id']}"
        ))

        create_audit_log(
            cursor,
            "growth_action",
            action_id,
            "Growth Action Executed",
            f"Executed RECOVER_CART for cart {cart_id}. Link: {link_res['payment_link']}"
        )

        conn.commit()
    finally:
        conn.close()

    return {
        "action_id": action_id,
        "action_type": "RECOVER_CART",
        "status": "executing",
        **link_res
    }

