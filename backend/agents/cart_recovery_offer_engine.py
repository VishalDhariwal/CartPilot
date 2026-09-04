import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from backend.db import get_db
from backend.engine.mandates import create_audit_log


def calculate_recovery_incentive(total_paise: int, idle_hours: float = 1.0) -> Tuple[int, int, str]:
    """
    Computes a smart, tiered recovery discount percentage and savings in paise.
    Strategy:
      - <= ₹500: 10% (high price elasticity on small orders)
      - ₹500 - ₹2,000: 8%
      - ₹2,000 - ₹5,000: 7% (e.g. ₹4,760 cart saves ₹333.20)
      - > ₹5,000: 5% (high basket value, protects merchant margins)
      - If idle > 6 hours: +2% urgency boost (capped at 15%)
    """
    if total_paise <= 50000:
        base_pct = 10
        bracket_label = "micro-basket (<₹500)"
    elif total_paise <= 200000:
        base_pct = 8
        bracket_label = "standard basket (₹500–₹2,000)"
    elif total_paise <= 500000:
        base_pct = 7
        bracket_label = "premium basket (₹2,000–₹5,000)"
    else:
        base_pct = 5
        bracket_label = "high-value basket (>₹5,000)"

    extra_pct = 2 if idle_hours >= 6.0 else 0
    final_pct = min(15, base_pct + extra_pct)
    discount_paise = int(total_paise * (final_pct / 100.0))

    reason = (
        f"Smart Tiered Incentive: {final_pct}% off ({bracket_label}"
        f"{' + 2% idle re-engagement boost' if extra_pct else ''}) saving ₹{discount_paise/100:.2f}"
    )
    return final_pct, discount_paise, reason


def expire_stale_offers() -> int:
    """
    Housekeeping: marks active recovery offers that have passed expires_at as 'expired'.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            "UPDATE cart_recovery_offers SET status = 'expired' WHERE status = 'active' AND expires_at <= ?",
            (now_str,)
        )
        expired_count = cursor.rowcount
        conn.commit()
        return expired_count
    finally:
        conn.close()


def generate_recovery_offer(cart_id: str, mode: str = "autonomous", duration_hours: int = 2) -> Dict[str, Any]:
    """
    Generates a personalized, time-limited cart recovery incentive offer.
    Decoupled from Razorpay payment links.
    Stores offer in cart_recovery_offers, creates a growth_action record, and logs to SHA-256 ledger.
    """
    expire_stale_offers()

    conn = get_db()
    cursor = conn.cursor()
    try:
        now = datetime.utcnow()
        now_str = now.isoformat() + "Z"
        expires_at_str = (now + timedelta(hours=duration_hours)).isoformat() + "Z"

        # 1. Check idempotency: does an active offer already exist for this cart?
        cursor.execute(
            """
            SELECT id, coupon_code, discount_pct, discount_paise, original_total_paise,
                   discounted_total_paise, items_summary, reason, ai_nudge_message,
                   status, created_at, expires_at
            FROM cart_recovery_offers
            WHERE cart_id = ? AND status = 'active' AND expires_at > ?
            """,
            (cart_id, now_str)
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "success": True,
                "is_duplicate": True,
                "message": f"Active recovery offer {existing['coupon_code']} already exists for cart {cart_id[-8:]}",
                "offer_id": existing["id"],
                "coupon_code": existing["coupon_code"],
                "discount_pct": existing["discount_pct"],
                "discount_paise": existing["discount_paise"],
                "discount_rupees": round(existing["discount_paise"] / 100, 2),
                "original_total_rupees": round(existing["original_total_paise"] / 100, 2),
                "discounted_total_rupees": round(existing["discounted_total_paise"] / 100, 2),
                "ai_nudge_message": existing["ai_nudge_message"],
                "expires_at": existing["expires_at"]
            }

        # 2. Fetch cart details
        cursor.execute("SELECT id, intent_id, items, total_paise, created_at FROM cart_mandates WHERE id = ?", (cart_id,))
        cart_row = cursor.fetchone()
        if not cart_row:
            raise ValueError(f"Cart '{cart_id}' not found in cart_mandates.")

        total_paise = cart_row["total_paise"]
        items_raw = cart_row["items"]
        created_at_str = cart_row["created_at"]
        intent_id = cart_row["intent_id"]

        items_list = []
        try:
            items_list = json.loads(items_raw) if items_raw else []
        except Exception:
            pass

        item_names = [it.get("name") or it.get("sku", "Item") for it in items_list]
        items_summary = ", ".join(item_names[:2]) + (f" +{len(item_names)-2} more" if len(item_names) > 2 else "")

        # Compute idle time
        try:
            clean_time = created_at_str.replace("Z", "+00:00") if "Z" in created_at_str else created_at_str
            created_dt = datetime.fromisoformat(clean_time)
            if created_dt.tzinfo is not None:
                created_dt = created_dt.replace(tzinfo=None)
            idle_hours = max(0.1, (now - created_dt).total_seconds() / 3600.0)
        except Exception:
            idle_hours = 1.0

        # 3. Calculate smart incentive
        discount_pct, discount_paise, reason = calculate_recovery_incentive(total_paise, idle_hours)
        discounted_total_paise = max(0, total_paise - discount_paise)
        original_rupees = round(total_paise / 100, 2)
        savings_rupees = round(discount_paise / 100, 2)
        discounted_rupees = round(discounted_total_paise / 100, 2)

        # 4. Generate unique coupon code
        code_suffix = uuid.uuid4().hex[:4].upper()
        coupon_code = f"SAVE{discount_pct}_{code_suffix}"
        offer_id = f"offer_recov_{uuid.uuid4().hex[:10]}"

        # 5. Look up potential session_id from chat_sessions or intent
        session_id = None
        if intent_id:
            cursor.execute("SELECT raw_request FROM intent_mandates WHERE id = ?", (intent_id,))

        # 6. Compose conversational AI nudge message
        ai_nudge_message = (
            f"You left ₹{original_rupees:.2f} in your cart ({items_summary}). "
            f"I have unlocked a personalized {discount_pct}% discount (saves you ₹{savings_rupees:.2f}) "
            f"with code {coupon_code} — valid for the next {duration_hours} hours. "
            f"Would you like me to complete your checkout now for only ₹{discounted_rupees:.2f}?"
        )

        # 7. Insert into cart_recovery_offers
        cursor.execute(
            """
            INSERT INTO cart_recovery_offers (
                id, cart_id, coupon_code, discount_pct, discount_paise,
                original_total_paise, discounted_total_paise, session_id,
                items_summary, reason, ai_nudge_message, status,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                offer_id, cart_id, coupon_code, discount_pct, discount_paise,
                total_paise, discounted_total_paise, session_id,
                items_summary, reason, ai_nudge_message,
                now_str, expires_at_str
            )
        )

        # 8. Record in growth_actions with action_type = 'OFFER_RECOVERY_INCENTIVE'
        action_id = f"ga_recov_{uuid.uuid4().hex[:10]}"
        cursor.execute(
            """
            INSERT INTO growth_actions (
                id, action_type, status, opportunity_type, title, explanation,
                affected_ref, est_revenue_paise, confidence, recommended_action,
                execution_ref, mode, created_at, executed_at, notes
            ) VALUES (?, 'OFFER_RECOVERY_INCENTIVE', 'executing', 'abandoned_cart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                f"Offer {discount_pct}% Cart Recovery Discount (Cart {cart_id[-8:]})",
                f"Created personalized recovery incentive code {coupon_code} saving ₹{savings_rupees:.2f} on ₹{original_rupees:.2f} cart. AI Buyer will proactively present offer on next customer session.",
                json.dumps({"cart_id": cart_id, "offer_id": offer_id, "coupon_code": coupon_code}),
                discounted_total_paise,
                0.68,  # Higher confidence due to tangible incentive
                f"Apply code {coupon_code} for {discount_pct}% off when buyer engages in chat.",
                cart_id,  # Set execution_ref directly to cart_id for clean idempotency!
                mode,
                now_str,
                now_str,
                f"Expires at {expires_at_str}. Discount: {discount_pct}% (₹{savings_rupees:.2f})"
            )
        )

        # 9. Cryptographic SHA-256 Audit Log
        create_audit_log(
            cursor,
            "growth_action",
            action_id,
            "Recovery Incentive Offer Dispatched",
            f"Generated {discount_pct}% discount offer ({coupon_code}, saves ₹{savings_rupees:.2f}) for cart {cart_id}. Injected into Buyer AI session context with {duration_hours}h validity."
        )

        conn.commit()

        return {
            "success": True,
            "is_duplicate": False,
            "offer_id": offer_id,
            "action_id": action_id,
            "action_type": "OFFER_RECOVERY_INCENTIVE",
            "cart_id": cart_id,
            "coupon_code": coupon_code,
            "discount_pct": discount_pct,
            "discount_paise": discount_paise,
            "discount_rupees": savings_rupees,
            "original_total_rupees": original_rupees,
            "discounted_total_rupees": discounted_rupees,
            "ai_nudge_message": ai_nudge_message,
            "reason": reason,
            "expires_at": expires_at_str,
            "status": "active"
        }
    finally:
        conn.close()


def get_active_offer_for_cart(cart_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns the active, non-expired recovery offer for a cart if one exists.
    """
    expire_stale_offers()
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            """
            SELECT id, cart_id, coupon_code, discount_pct, discount_paise,
                   original_total_paise, discounted_total_paise, items_summary,
                   reason, ai_nudge_message, status, created_at, expires_at
            FROM cart_recovery_offers
            WHERE cart_id = ? AND status = 'active' AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (cart_id, now_str)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "offer_id": row["id"],
            "cart_id": row["cart_id"],
            "coupon_code": row["coupon_code"],
            "discount_pct": row["discount_pct"],
            "discount_paise": row["discount_paise"],
            "discount_rupees": round(row["discount_paise"] / 100, 2),
            "original_total_paise": row["original_total_paise"],
            "original_total_rupees": round(row["original_total_paise"] / 100, 2),
            "discounted_total_paise": row["discounted_total_paise"],
            "discounted_total_rupees": round(row["discounted_total_paise"] / 100, 2),
            "items_summary": row["items_summary"],
            "reason": row["reason"],
            "ai_nudge_message": row["ai_nudge_message"],
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"]
        }
    finally:
        conn.close()


def get_active_offer_for_session(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Finds the most recent active recovery offer for a buyer session.
    """
    expire_stale_offers()
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        if session_id:
            cursor.execute(
                """
                SELECT id, cart_id, coupon_code, discount_pct, discount_paise,
                       original_total_paise, discounted_total_paise, items_summary,
                       reason, ai_nudge_message, status, created_at, expires_at
                FROM cart_recovery_offers
                WHERE session_id = ? AND status = 'active' AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id, now_str)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "offer_id": row["id"],
                    "cart_id": row["cart_id"],
                    "coupon_code": row["coupon_code"],
                    "discount_pct": row["discount_pct"],
                    "discount_paise": row["discount_paise"],
                    "discount_rupees": round(row["discount_paise"] / 100, 2),
                    "original_total_rupees": round(row["original_total_paise"] / 100, 2),
                    "discounted_total_rupees": round(row["discounted_total_paise"] / 100, 2),
                    "items_summary": row["items_summary"],
                    "ai_nudge_message": row["ai_nudge_message"],
                    "expires_at": row["expires_at"]
                }

        # Fallback: get the latest active unredeemed offer overall
        cursor.execute(
            """
            SELECT id, cart_id, coupon_code, discount_pct, discount_paise,
                   original_total_paise, discounted_total_paise, items_summary,
                   reason, ai_nudge_message, status, created_at, expires_at
            FROM cart_recovery_offers
            WHERE status = 'active' AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (now_str,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "offer_id": row["id"],
            "cart_id": row["cart_id"],
            "coupon_code": row["coupon_code"],
            "discount_pct": row["discount_pct"],
            "discount_paise": row["discount_paise"],
            "discount_rupees": round(row["discount_paise"] / 100, 2),
            "original_total_rupees": round(row["original_total_paise"] / 100, 2),
            "discounted_total_rupees": round(row["discounted_total_paise"] / 100, 2),
            "items_summary": row["items_summary"],
            "ai_nudge_message": row["ai_nudge_message"],
            "expires_at": row["expires_at"]
        }
    finally:
        conn.close()


def apply_offer_at_checkout(cart_id: str, offer_code_or_id: Optional[str] = None, payment_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Validates and marks a recovery offer as redeemed upon successful checkout.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        query = "SELECT id, coupon_code, discount_pct, discount_paise, original_total_paise, discounted_total_paise, status, expires_at FROM cart_recovery_offers WHERE cart_id = ? AND status = 'active'"
        params = [cart_id]

        if offer_code_or_id:
            query += " AND (id = ? OR coupon_code = ?)"
            params.extend([offer_code_or_id, offer_code_or_id])

        query += " ORDER BY created_at DESC LIMIT 1"
        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return {"applied": False, "reason": "No active recovery offer found for this cart."}

        if row["expires_at"] <= now_str:
            cursor.execute("UPDATE cart_recovery_offers SET status = 'expired' WHERE id = ?", (row["id"],))
            conn.commit()
            return {"applied": False, "reason": f"Offer {row['coupon_code']} has expired."}

        # Mark redeemed
        cursor.execute(
            """
            UPDATE cart_recovery_offers
            SET status = 'redeemed', redeemed_at = ?, redeemed_by_payment_id = ?
            WHERE id = ?
            """,
            (now_str, payment_id or "pending", row["id"])
        )

        # Update growth_actions outcome to completed
        cursor.execute(
            """
            UPDATE growth_actions
            SET status = 'completed', notes = ?
            WHERE affected_ref LIKE ? AND action_type = 'OFFER_RECOVERY_INCENTIVE'
            """,
            (f"Redeemed with payment {payment_id}", f"%{cart_id}%")
        )

        create_audit_log(
            cursor,
            "growth_action",
            row["id"],
            "Recovery Incentive Redeemed",
            f"Buyer successfully redeemed recovery code {row['coupon_code']} for cart {cart_id}. Discount: {row['discount_pct']}% (saved ₹{row['discount_paise']/100:.2f})."
        )

        conn.commit()

        return {
            "applied": True,
            "offer_id": row["id"],
            "coupon_code": row["coupon_code"],
            "discount_pct": row["discount_pct"],
            "discount_paise": row["discount_paise"],
            "discount_rupees": round(row["discount_paise"] / 100, 2),
            "discounted_total_paise": row["discounted_total_paise"],
            "discounted_total_rupees": round(row["discounted_total_paise"] / 100, 2)
        }
    finally:
        conn.close()


def list_recovery_offers(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns all recovery offers for the merchant dashboard.
    """
    expire_stale_offers()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, cart_id, coupon_code, discount_pct, discount_paise,
                   original_total_paise, discounted_total_paise, session_id,
                   items_summary, reason, ai_nudge_message, status,
                   created_at, expires_at, redeemed_at, redeemed_by_payment_id
            FROM cart_recovery_offers
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        offers = []
        for r in rows:
            offers.append({
                "id": r["id"],
                "cart_id": r["cart_id"],
                "coupon_code": r["coupon_code"],
                "discount_pct": r["discount_pct"],
                "discount_paise": r["discount_paise"],
                "discount_rupees": round(r["discount_paise"] / 100, 2),
                "original_total_paise": r["original_total_paise"],
                "original_total_rupees": round(r["original_total_paise"] / 100, 2),
                "discounted_total_paise": r["discounted_total_paise"],
                "discounted_total_rupees": round(r["discounted_total_paise"] / 100, 2),
                "items_summary": r["items_summary"],
                "reason": r["reason"],
                "ai_nudge_message": r["ai_nudge_message"],
                "status": r["status"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "redeemed_at": r["redeemed_at"],
                "redeemed_by_payment_id": r["redeemed_by_payment_id"]
            })
        return offers
    finally:
        conn.close()
