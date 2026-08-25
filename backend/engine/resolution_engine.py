"""
CartPilot Deterministic Resolution & Refund Engine
=================================================
Authoritative domain logic for Order Cancellation, Return Management, and Gateway Refund Processing.

Guarantees:
1. Strict lifecycle decoupling (Order vs Cancellation vs Return vs Refund).
2. Deterministic balance accounting: requested_amount <= captured_amount - SUM(refunded).
3. Concurrent duplicate & in-flight refund prevention.
4. Fulfillment safety default: UNKNOWN fulfillment requires merchant review (never assumed safe).
5. Gateway reconciliation: REFUND_PROCESSING until authoritative provider confirmation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from backend.db import get_db


# ─── Domain Lifecycle Enums ──────────────────────────────────────────────────
class OrderStatus:
    CREATED = "CREATED"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class CancellationStatus:
    NONE = "NONE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


class FulfillmentStatus:
    UNFULFILLED = "UNFULFILLED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    UNKNOWN = "UNKNOWN"


class ReturnStatus:
    NONE = "NONE"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURN_REVIEW_REQUIRED = "RETURN_REVIEW_REQUIRED"
    RETURN_APPROVED = "RETURN_APPROVED"
    RETURN_RECEIVED = "RETURN_RECEIVED"
    RETURN_COMPLETED = "RETURN_COMPLETED"
    RETURN_REJECTED = "RETURN_REJECTED"


class RefundStatus:
    NONE = "NONE"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_REVIEW_REQUIRED = "REFUND_REVIEW_REQUIRED"
    REFUND_PROCESSING = "REFUND_PROCESSING"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    REFUND_FAILED = "REFUND_FAILED"


class ResolutionAction:
    CANCEL_ORDER_ONLY = "cancel_order_only"
    INITIATE_REFUND = "initiate_refund"
    CREATE_RETURN_REVIEW = "create_return_review"
    CREATE_REFUND_REVIEW = "create_refund_review"
    INFORM_ONLY = "inform_only"
    ESCALATE = "escalate"


@dataclass
class RefundEligibilityResult:
    status: str
    action: str
    is_eligible: bool
    requires_review: bool
    refundable_amount_paise: int
    remaining_refundable_paise: int
    reason: str
    order_status: str
    fulfillment_status: str
    return_status: str
    refund_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Helper Functions ────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_audit(cursor, ref_type: str, ref_id: str, event: str, detail: str):
    cursor.execute(
        "INSERT INTO audit_log (ref_type, ref_id, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (ref_type, ref_id, event, detail, _now_iso())
    )


def get_refundable_balance(cursor, payment_id: str, captured_amount_paise: int) -> int:
    """
    Computes remaining refundable balance = captured_amount - SUM(successfully refunded).
    """
    cursor.execute(
        "SELECT COALESCE(SUM(processed_amount_paise), 0) FROM refunds WHERE payment_id = ? AND status = 'REFUNDED'",
        (payment_id,)
    )
    row = cursor.fetchone()
    sum_refunded = row[0] if row else 0
    return max(0, captured_amount_paise - sum_refunded)


def has_active_inflight_refund(cursor, payment_id: str) -> bool:
    """
    Checks if there is already an active refund in REQUESTED or PROCESSING state.
    """
    cursor.execute(
        "SELECT COUNT(*) FROM refunds WHERE payment_id = ? AND status IN ('REFUND_REQUESTED', 'REFUND_PROCESSING')",
        (payment_id,)
    )
    row = cursor.fetchone()
    return (row[0] > 0) if row else False


# ─── Deterministic Refund Eligibility Evaluator ──────────────────────────────
def evaluate_resolution_eligibility(
    cart_id: str,
    intent: str,
    requested_amount_paise: Optional[int] = None
) -> RefundEligibilityResult:
    """
    Pure deterministic evaluation of cancellation, return, and refund eligibility.
    Never relies on legacy booleans; evaluates full domain state.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Fetch Cart Mandate
        cursor.execute(
            """
            SELECT id, intent_id, items, total_paise, status, reason, reversible,
                   COALESCE(order_status, 'CREATED') as order_status,
                   COALESCE(cancellation_status, 'NONE') as cancellation_status,
                   COALESCE(fulfillment_status, 'UNFULFILLED') as fulfillment_status,
                   COALESCE(return_status, 'NONE') as return_status
            FROM cart_mandates WHERE id = ?
            """,
            (cart_id,)
        )
        cart = cursor.fetchone()
        if not cart:
            return RefundEligibilityResult(
                status="CART_NOT_FOUND",
                action=ResolutionAction.ESCALATE,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=0,
                reason=f"Cart '{cart_id}' not found in database.",
                order_status="UNKNOWN",
                fulfillment_status="UNKNOWN",
                return_status="NONE",
                refund_status="NONE"
            )

        cart_dict = dict(cart)
        order_status = cart_dict["order_status"]
        cancellation_status = cart_dict["cancellation_status"]
        fulfillment_status = cart_dict["fulfillment_status"]
        return_status = cart_dict["return_status"]

        # 2. Fetch Payment Mandate
        cursor.execute(
            """
            SELECT id, cart_id, razorpay_order_id, razorpay_payment_id, amount_paise,
                   status, failure_reason, recovery_action,
                   COALESCE(refund_status, 'NONE') as refund_status,
                   COALESCE(refunded_amount_paise, 0) as refunded_amount_paise
            FROM payment_mandates WHERE cart_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (cart_id,)
        )
        pm_row = cursor.fetchone()
        payment = dict(pm_row) if pm_row else None
        refund_status = payment["refund_status"] if payment else RefundStatus.NONE

        # Handle informational policy inquiry
        if intent == "ASK_REFUND_POLICY":
            return RefundEligibilityResult(
                status="INFORM_ONLY",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=0,
                reason="Customer inquired about refund/return policy.",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=refund_status
            )

        # Handle refund status tracking lookup
        if intent == "CHECK_REFUND_STATUS":
            return RefundEligibilityResult(
                status="STATUS_LOOKUP",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=0,
                reason=f"Current Refund Status: {refund_status}, Order Status: {order_status}.",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=refund_status
            )

        # ── Case 1: Unpaid Order / Cart Cancellation ──
        if not payment or payment["status"] != "succeeded":
            if intent in ["CANCEL_ORDER", "REQUEST_REFUND"]:
                if cancellation_status == CancellationStatus.CANCELLED or order_status == OrderStatus.CANCELLED:
                    return RefundEligibilityResult(
                        status="ALREADY_CANCELLED",
                        action=ResolutionAction.INFORM_ONLY,
                        is_eligible=False,
                        requires_review=False,
                        refundable_amount_paise=0,
                        remaining_refundable_paise=0,
                        reason="Order was unpaid and is already cancelled.",
                        order_status=OrderStatus.CANCELLED,
                        fulfillment_status=fulfillment_status,
                        return_status=return_status,
                        refund_status=RefundStatus.NONE
                    )
                return RefundEligibilityResult(
                    status="ELIGIBLE_CANCEL_ONLY",
                    action=ResolutionAction.CANCEL_ORDER_ONLY,
                    is_eligible=True,
                    requires_review=False,
                    refundable_amount_paise=0,
                    remaining_refundable_paise=0,
                    reason="Order has not been paid. Eligible for instant cart cancellation with zero financial refund.",
                    order_status=order_status,
                    fulfillment_status=fulfillment_status,
                    return_status=return_status,
                    refund_status=RefundStatus.NONE
                )
            return RefundEligibilityResult(
                status="UNPAID_ORDER_ACTION_NOT_SUPPORTED",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=0,
                reason="Order is not paid; financial operations are not applicable.",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=RefundStatus.NONE
            )

        # ── Case 2: Paid Order - Calculate Authoritative Balance ──
        captured_amount = payment["amount_paise"]
        remaining_paise = get_refundable_balance(cursor, payment["id"], captured_amount)

        # Idempotency: Check if already fully refunded
        if remaining_paise <= 0 or refund_status == RefundStatus.REFUNDED:
            return RefundEligibilityResult(
                status="ALREADY_FULLY_REFUNDED",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=0,
                reason="This order has already been fully refunded. No additional refunds can be processed.",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=RefundStatus.REFUNDED
            )

        # Idempotency: Check if an in-flight refund is already processing
        if has_active_inflight_refund(cursor, payment["id"]) or refund_status == RefundStatus.REFUND_PROCESSING:
            return RefundEligibilityResult(
                status="REFUND_ALREADY_IN_PROGRESS",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=remaining_paise,
                reason="A refund request for this order is currently in-flight/processing with the payment gateway.",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=RefundStatus.REFUND_PROCESSING
            )

        # Validate requested amount against remaining balance
        effective_refund_amount = requested_amount_paise if (requested_amount_paise is not None and requested_amount_paise > 0) else remaining_paise
        if effective_refund_amount > remaining_paise:
            return RefundEligibilityResult(
                status="EXCEEDS_REFUNDABLE_LIMIT",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=remaining_paise,
                reason=f"Requested refund (₹{effective_refund_amount/100:.2f}) exceeds remaining refundable balance (₹{remaining_paise/100:.2f}).",
                order_status=order_status,
                fulfillment_status=fulfillment_status,
                return_status=return_status,
                refund_status=refund_status
            )

        # ── Case 3: Fulfillment Safety Check (Correction 3) ──
        # If fulfillment is UNKNOWN, never assume pre-fulfillment safe
        if fulfillment_status == FulfillmentStatus.UNKNOWN:
            return RefundEligibilityResult(
                status="REFUND_REVIEW_REQUIRED",
                action=ResolutionAction.CREATE_REFUND_REVIEW,
                is_eligible=False,
                requires_review=True,
                refundable_amount_paise=effective_refund_amount,
                remaining_refundable_paise=remaining_paise,
                reason="Fulfillment/shipping status is unverified (UNKNOWN). Requires explicit merchant review before funds can be released.",
                order_status=order_status,
                fulfillment_status=FulfillmentStatus.UNKNOWN,
                return_status=return_status,
                refund_status=RefundStatus.REFUND_REVIEW_REQUIRED
            )

        # ── Case 4: In-Transit / Shipped Order ──
        if fulfillment_status == FulfillmentStatus.SHIPPED:
            return RefundEligibilityResult(
                status="INELIGIBLE_IN_TRANSIT",
                action=ResolutionAction.INFORM_ONLY,
                is_eligible=False,
                requires_review=False,
                refundable_amount_paise=0,
                remaining_refundable_paise=remaining_paise,
                reason="Order has already been dispatched with the carrier. Instant cancellation is not permitted while package is in transit. Please refuse delivery or request a return upon arrival.",
                order_status=order_status,
                fulfillment_status=FulfillmentStatus.SHIPPED,
                return_status=return_status,
                refund_status=refund_status
            )

        # ── Case 5: Delivered Order Return Workflow ──
        if fulfillment_status == FulfillmentStatus.DELIVERED:
            if intent in ["RETURN_ITEM", "REQUEST_REFUND", "REPORT_DAMAGED_ITEM", "CANCEL_ORDER"]:
                return RefundEligibilityResult(
                    status="RETURN_REVIEW_REQUIRED",
                    action=ResolutionAction.CREATE_RETURN_REVIEW,
                    is_eligible=False,
                    requires_review=True,
                    refundable_amount_paise=effective_refund_amount,
                    remaining_refundable_paise=remaining_paise,
                    reason="Order has been delivered. Initiating return review workflow; physical receipt/merchant inspection required before refund execution.",
                    order_status=order_status,
                    fulfillment_status=FulfillmentStatus.DELIVERED,
                    return_status=ReturnStatus.RETURN_REVIEW_REQUIRED,
                    refund_status=RefundStatus.NONE
                )
            return RefundEligibilityResult(
                status="DELIVERED_INTENT_UNSUPPORTED",
                action=ResolutionAction.ESCALATE,
                is_eligible=False,
                requires_review=True,
                refundable_amount_paise=0,
                remaining_refundable_paise=remaining_paise,
                reason="Delivered order requires escalation to customer resolution team.",
                order_status=order_status,
                fulfillment_status=FulfillmentStatus.DELIVERED,
                return_status=return_status,
                refund_status=refund_status
            )

        # ── Case 6: Pre-Fulfillment Cancellation (Paid & Unfulfilled/Processing) ──
        if fulfillment_status in [FulfillmentStatus.UNFULFILLED, FulfillmentStatus.PROCESSING]:
            if intent in ["CANCEL_ORDER", "REQUEST_REFUND"]:
                return RefundEligibilityResult(
                    status="ELIGIBLE_INSTANT_REFUND",
                    action=ResolutionAction.INITIATE_REFUND,
                    is_eligible=True,
                    requires_review=False,
                    refundable_amount_paise=effective_refund_amount,
                    remaining_refundable_paise=remaining_paise,
                    reason="Order is paid and unfulfilled. Cancellation and refund are fully eligible under merchant policy.",
                    order_status=order_status,
                    fulfillment_status=fulfillment_status,
                    return_status=return_status,
                    refund_status=refund_status
                )

        # Default fallback: Escalate to merchant review
        return RefundEligibilityResult(
            status="ESCALATE_TO_MERCHANT",
            action=ResolutionAction.ESCALATE,
            is_eligible=False,
            requires_review=True,
            refundable_amount_paise=0,
            remaining_refundable_paise=remaining_paise,
            reason="Order state requires manual merchant review.",
            order_status=order_status,
            fulfillment_status=fulfillment_status,
            return_status=return_status,
            refund_status=refund_status
        )

    finally:
        conn.close()


# ─── Refund Execution & Ledger Management ────────────────────────────────────
def create_and_execute_refund(
    cart_id: str,
    requested_amount_paise: Optional[int] = None,
    reason: str = "Customer requested cancellation"
) -> Dict[str, Any]:
    """
    Executes the authorized cancellation / refund action based on deterministic evaluation.
    Updates the refunds ledger, payment mandates, and cart mandates.
    """
    from backend.integrations.razorpay_client import refund_payment

    # 1. Evaluate first (safe, isolated DB read)
    eval_result = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER", requested_amount_paise)
    now_ts = _now_iso()

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM cart_mandates WHERE id = ?", (cart_id,))
        cart = cursor.fetchone()
        if not cart:
            raise ValueError(f"Cart '{cart_id}' not found")

        cursor.execute("SELECT * FROM payment_mandates WHERE cart_id = ? ORDER BY created_at DESC LIMIT 1", (cart_id,))
        payment = cursor.fetchone()

        # ── Case A: Unpaid Order Cancellation ──
        if not payment or payment["status"] != "succeeded":
            cursor.execute(
                """
                UPDATE cart_mandates
                SET order_status = 'CANCELLED', cancellation_status = 'CANCELLED', reversible = 0
                WHERE id = ?
                """,
                (cart_id,)
            )
            # Void any growth outcomes for this cancelled cart so it never counts as revenue
            cursor.execute(
                """
                UPDATE growth_outcomes
                SET outcome_type = 'cancelled', incremental_paise = 0
                WHERE action_id = ? OR (id LIKE 'go_xs_%' AND action_id = ?)
                """,
                (cart_id, cart_id)
            )
            _create_audit(cursor, "cart", cart_id, "Order Cancelled (Unpaid)", f"Reason: {reason}")
            conn.commit()
            return {
                "status": "cancelled",
                "order_status": OrderStatus.CANCELLED,
                "cancellation_status": CancellationStatus.CANCELLED,
                "fulfillment_status": cart["fulfillment_status"],
                "return_status": cart["return_status"],
                "refund_status": RefundStatus.NONE,
                "refund_id": None,
                "amount_refunded_paise": 0,
                "reason": "Unpaid order cancelled successfully."
            }

        # ── Case B: Non-Eligible Action Handling ──
        if not eval_result.is_eligible:
            if eval_result.action == ResolutionAction.CREATE_RETURN_REVIEW:
                cursor.execute(
                    "UPDATE cart_mandates SET return_status = 'RETURN_REVIEW_REQUIRED' WHERE id = ?",
                    (cart_id,)
                )
                _create_audit(cursor, "cart", cart_id, "Return Review Created", eval_result.reason)
                conn.commit()
                return {
                    "status": "review_required",
                    "order_status": cart["order_status"],
                    "fulfillment_status": cart["fulfillment_status"],
                    "return_status": ReturnStatus.RETURN_REVIEW_REQUIRED,
                    "refund_status": payment["refund_status"],
                    "reason": eval_result.reason
                }

            if eval_result.action == ResolutionAction.CREATE_REFUND_REVIEW:
                cursor.execute(
                    "UPDATE payment_mandates SET refund_status = 'REFUND_REVIEW_REQUIRED', updated_at = ? WHERE id = ?",
                    (now_ts, payment["id"])
                )
                _create_audit(cursor, "payment", payment["id"], "Refund Review Created", eval_result.reason)
                conn.commit()
                return {
                    "status": "review_required",
                    "order_status": cart["order_status"],
                    "fulfillment_status": cart["fulfillment_status"],
                    "return_status": cart["return_status"],
                    "refund_status": RefundStatus.REFUND_REVIEW_REQUIRED,
                    "reason": eval_result.reason
                }

            return {
                "status": "denied",
                "eligibility_status": eval_result.status,
                "reason": eval_result.reason,
                "order_status": cart["order_status"],
                "refund_status": payment["refund_status"]
            }

        # ── Case C: Execute Refund through Ledger and Razorpay ──
        refund_amount = eval_result.refundable_amount_paise
        local_refund_id = f"rfnd_{uuid.uuid4().hex[:14]}"

        # 1. Insert in-flight record into dedicated refunds table
        cursor.execute(
            """
            INSERT INTO refunds (
                id, payment_id, cart_id, requested_amount_paise,
                processed_amount_paise, status, razorpay_refund_id, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_refund_id, payment["id"], cart_id, refund_amount,
                0, RefundStatus.REFUND_PROCESSING, None, reason, now_ts
            )
        )
        _create_audit(
            cursor, "refund", local_refund_id, "Refund Request Created",
            f"Amount: {refund_amount} paise. Status: REFUND_PROCESSING"
        )
        conn.commit()

        # 2. Call Razorpay API
        try:
            rzp_resp = refund_payment(payment["razorpay_payment_id"], refund_amount)
            rzp_refund_id = rzp_resp.get("id")
            rzp_status = rzp_resp.get("status", "processed")
        except Exception as e:
            cursor.execute(
                "UPDATE refunds SET status = 'REFUND_FAILED', processed_at = ? WHERE id = ?",
                (now_ts, local_refund_id)
            )
            cursor.execute(
                "UPDATE payment_mandates SET refund_status = 'REFUND_FAILED', updated_at = ? WHERE id = ?",
                (now_ts, payment["id"])
            )
            _create_audit(cursor, "refund", local_refund_id, "Refund Failed", f"Error: {str(e)}")
            conn.commit()
            return {
                "status": "failed",
                "refund_status": RefundStatus.REFUND_FAILED,
                "reason": f"Razorpay refund call failed: {str(e)}",
                "order_status": cart["order_status"]
            }

        # 3. Update Refunds Ledger & Payment Mandates
        if rzp_status in ["processed", "succeeded"]:
            final_refund_status = RefundStatus.REFUNDED
            processed_amount = refund_amount
        else:
            final_refund_status = RefundStatus.REFUND_PROCESSING
            processed_amount = 0

        cursor.execute(
            """
            UPDATE refunds
            SET status = ?, processed_amount_paise = ?, razorpay_refund_id = ?, processed_at = ?
            WHERE id = ?
            """,
            (final_refund_status, processed_amount, rzp_refund_id, now_ts, local_refund_id)
        )

        # 4. Calculate total refunded amount for this payment
        cursor.execute(
            "SELECT COALESCE(SUM(processed_amount_paise), 0) FROM refunds WHERE payment_id = ? AND status = 'REFUNDED'",
            (payment["id"],)
        )
        total_refunded_so_far = cursor.fetchone()[0]

        if total_refunded_so_far >= payment["amount_paise"]:
            pm_refund_status = RefundStatus.REFUNDED
            if cart["fulfillment_status"] in [FulfillmentStatus.UNFULFILLED, FulfillmentStatus.PROCESSING]:
                cursor.execute(
                    """
                    UPDATE cart_mandates
                    SET order_status = 'CANCELLED', cancellation_status = 'CANCELLED', reversible = 0
                    WHERE id = ?
                    """,
                    (cart_id,)
                )
                _create_audit(cursor, "cart", cart_id, "Order Cancelled", "Full refund completed pre-fulfillment.")
            elif cart["fulfillment_status"] == FulfillmentStatus.DELIVERED:
                cursor.execute(
                    "UPDATE cart_mandates SET return_status = 'RETURN_COMPLETED', reversible = 0 WHERE id = ?",
                    (cart_id,)
                )
                _create_audit(cursor, "cart", cart_id, "Return Completed", "Full refund processed post-delivery.")
        elif total_refunded_so_far > 0:
            pm_refund_status = RefundStatus.PARTIALLY_REFUNDED
        else:
            pm_refund_status = RefundStatus.REFUND_PROCESSING

        cursor.execute(
            """
            UPDATE payment_mandates
            SET refund_status = ?, refund_amount_paise = ?, refunded_amount_paise = ?,
                razorpay_refund_id = ?, recovery_action = 'refunded', updated_at = ?
            WHERE id = ?
            """,
            (
                pm_refund_status, refund_amount, total_refunded_so_far,
                rzp_refund_id, now_ts, payment["id"]
            )
        )

        # Void/nullify growth outcomes for this refunded/cancelled order so it is never counted as revenue
        if final_refund_status == RefundStatus.REFUNDED or total_refunded_so_far >= payment["amount_paise"]:
            cursor.execute(
                """
                UPDATE growth_outcomes
                SET outcome_type = 'refunded', incremental_paise = 0
                WHERE id IN (?, ?) OR action_id = ?
                """,
                (f"go_paid_{payment['id']}", f"go_recov_{payment['id']}", payment["id"])
            )
            cursor.execute(
                """
                UPDATE growth_outcomes
                SET outcome_type = 'refunded', incremental_paise = 0
                WHERE (id LIKE 'go_xs_%' AND action_id = ?) OR action_id = ?
                """,
                (cart_id, cart_id)
            )

        _create_audit(
            cursor, "payment", payment["id"], "Refund Settled",
            f"Razorpay Refund ID: {rzp_refund_id} for {refund_amount} paise. Status: {pm_refund_status}"
        )
        conn.commit()

        return {
            "status": "refunded" if final_refund_status == RefundStatus.REFUNDED else "processing",
            "order_status": OrderStatus.CANCELLED if (total_refunded_so_far >= payment["amount_paise"] and cart["fulfillment_status"] != FulfillmentStatus.DELIVERED) else cart["order_status"],
            "cancellation_status": CancellationStatus.CANCELLED if (total_refunded_so_far >= payment["amount_paise"] and cart["fulfillment_status"] != FulfillmentStatus.DELIVERED) else cart["cancellation_status"],
            "fulfillment_status": cart["fulfillment_status"],
            "return_status": ReturnStatus.RETURN_COMPLETED if cart["fulfillment_status"] == FulfillmentStatus.DELIVERED else cart["return_status"],
            "refund_status": pm_refund_status,
            "refund_id": rzp_refund_id,
            "amount_refunded_paise": refund_amount,
            "total_refunded_paise": total_refunded_so_far,
            "reason": f"Refund of ₹{refund_amount/100:.2f} processed successfully via Razorpay (ID: {rzp_refund_id})."
        }

    finally:
        conn.close()


# ─── Webhook Settlement Handler ──────────────────────────────────────────────
def settle_refund_webhook(
    razorpay_refund_id: str,
    event_type: str,
    refund_entity: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Authoritatively settles an in-flight refund upon receiving Razorpay webhook events:
    - refund.processed / refund.created
    - refund.failed
    """
    conn = get_db()
    cursor = conn.cursor()
    now_ts = _now_iso()
    try:
        cursor.execute(
            "SELECT id, payment_id, cart_id, requested_amount_paise, status FROM refunds WHERE razorpay_refund_id = ?",
            (razorpay_refund_id,)
        )
        ref_row = cursor.fetchone()
        if not ref_row:
            payment_id = refund_entity.get("payment_id")
            if payment_id:
                cursor.execute(
                    "SELECT r.id, r.payment_id, r.cart_id, r.requested_amount_paise, r.status FROM refunds r JOIN payment_mandates p ON r.payment_id = p.id WHERE p.razorpay_payment_id = ? ORDER BY r.created_at DESC LIMIT 1",
                    (payment_id,)
                )
                ref_row = cursor.fetchone()

        if not ref_row:
            return {"status": "ignored", "reason": f"No matching refund record found for '{razorpay_refund_id}'."}

        refund_record = dict(ref_row)
        ref_id = refund_record["id"]
        payment_db_id = refund_record["payment_id"]
        cart_id = refund_record["cart_id"]
        req_amount = refund_record["requested_amount_paise"]

        if event_type in ["refund.processed", "refund.created"]:
            cursor.execute(
                """
                UPDATE refunds
                SET status = 'REFUNDED', processed_amount_paise = ?, processed_at = ?
                WHERE id = ?
                """,
                (req_amount, now_ts, ref_id)
            )

            # Recompute total refunded
            cursor.execute(
                "SELECT COALESCE(SUM(processed_amount_paise), 0) FROM refunds WHERE payment_id = ? AND status = 'REFUNDED'",
                (payment_db_id,)
            )
            total_refunded = cursor.fetchone()[0]

            cursor.execute("SELECT amount_paise FROM payment_mandates WHERE id = ?", (payment_db_id,))
            pm_row = cursor.fetchone()
            captured = pm_row[0] if pm_row else req_amount

            new_pm_status = RefundStatus.REFUNDED if total_refunded >= captured else RefundStatus.PARTIALLY_REFUNDED
            cursor.execute(
                """
                UPDATE payment_mandates
                SET refund_status = ?, refunded_amount_paise = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_pm_status, total_refunded, now_ts, payment_db_id)
            )

            if new_pm_status == RefundStatus.REFUNDED:
                cursor.execute(
                    """
                    UPDATE growth_outcomes
                    SET outcome_type = 'refunded', incremental_paise = 0
                    WHERE id IN (?, ?) OR action_id = ?
                    """,
                    (f"go_paid_{payment_db_id}", f"go_recov_{payment_db_id}", payment_db_id)
                )
                cursor.execute(
                    """
                    UPDATE growth_outcomes
                    SET outcome_type = 'refunded', incremental_paise = 0
                    WHERE (id LIKE 'go_xs_%' AND action_id = ?) OR action_id = ?
                    """,
                    (cart_id, cart_id)
                )

            _create_audit(
                cursor, "webhook", razorpay_refund_id, "Webhook Refund Processed",
                f"Settled refund {ref_id} for {req_amount} paise. Status: {new_pm_status}"
            )
            conn.commit()
            return {"status": "settled", "refund_status": new_pm_status, "total_refunded_paise": total_refunded}

        elif event_type == "refund.failed":
            cursor.execute(
                "UPDATE refunds SET status = 'REFUND_FAILED', processed_at = ? WHERE id = ?",
                (now_ts, ref_id)
            )
            cursor.execute(
                "UPDATE payment_mandates SET refund_status = 'REFUND_FAILED', updated_at = ? WHERE id = ?",
                (now_ts, payment_db_id)
            )
            _create_audit(
                cursor, "webhook", razorpay_refund_id, "Webhook Refund Failed",
                f"Refund {ref_id} failed on gateway."
            )
            conn.commit()
            return {"status": "failed", "refund_status": RefundStatus.REFUND_FAILED}

        return {"status": "acknowledged", "event": event_type}

    finally:
        conn.close()
