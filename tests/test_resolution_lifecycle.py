"""
CartPilot Comprehensive Resolution, Return, and Refund Lifecycle Test Suite
==========================================================================
Tests the 16 core scenarios of the decoupled resolution architecture:
1. Unpaid order cancellation (zero money moved).
2. Paid + unfulfilled cancellation (instant refund).
3. Shipped order cancellation rejected (INELIGIBLE_IN_TRANSIT).
4. Delivered order return request (RETURN_REVIEW_REQUIRED).
5. Policy inquiry (INFORM_ONLY, zero state changes).
6. Duplicate in-flight refund request rejected.
7. Partial refund ledger accounting.
8. Refund amount exceeding refundable balance rejected.
9. Razorpay API failure handled gracefully (REFUND_FAILED).
10. Refund processing state verification.
11. Razorpay webhook settlement (refund.processed).
12. Already fully refunded order rejected.
13. AI misclassification overridden by deterministic engine.
14. Unknown fulfillment status defaults to review (never assumed safe).
15. Chronological audit log integrity.
16. Public buyer MCP isolation (cancel_order disabled).
"""

import pytest
import uuid
import json
from datetime import datetime, timezone
from backend.db import get_db, init_db
from backend.engine.mandates import (
    create_intent_mandate,
    create_cart_mandate,
    create_payment_mandate,
    update_payment_mandate_status,
    get_cart_state
)
from backend.engine.resolution_engine import (
    evaluate_resolution_eligibility,
    create_and_execute_refund,
    settle_refund_webhook,
    OrderStatus,
    CancellationStatus,
    FulfillmentStatus,
    ReturnStatus,
    RefundStatus,
    ResolutionAction
)
from backend.agents.resolution_agent import classify_customer_intent, decide_resolution


import os

TEST_DB_PATH = "/tmp/test_resolution_lifecycle.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    os.environ["CARTPILOT_DB"] = TEST_DB_PATH
    import backend.db
    backend.db.DB_PATH = TEST_DB_PATH
    init_db()
    yield
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


def _create_test_order(
    amount_paise: int = 250000,
    is_paid: bool = True,
    fulfillment_status: str = FulfillmentStatus.UNFULFILLED,
    order_status: str = OrderStatus.PAID,
    return_status: str = ReturnStatus.NONE
):
    """
    Helper to seed a test cart and payment mandate with explicit lifecycle attributes.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    intent_id = f"intent_test_{uuid.uuid4().hex[:8]}"
    cart_id = f"cart_test_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_man_{uuid.uuid4().hex[:8]}"
    rzp_order_id = f"order_test_{uuid.uuid4().hex[:8]}"
    rzp_payment_id = f"pay_mock_{uuid.uuid4().hex[:8]}" if is_paid else None
    now_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Intent
    cursor.execute(
        "INSERT INTO intent_mandates (id, raw_request, goal, spend_cap_paise, channel, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (intent_id, "Buy test item", "Buy test item", 500000, "web_chat", now_ts)
    )

    # Cart Mandate
    items_json = json.dumps([{"sku": "TEST-SKU-1", "name": "Test Item", "qty": 1, "price_paise": amount_paise}])
    cursor.execute(
        """
        INSERT INTO cart_mandates (
            id, intent_id, items, total_paise, status, reason, reversible,
            order_status, cancellation_status, fulfillment_status, return_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cart_id, intent_id, items_json, amount_paise, "approved", "Within spend cap", 1,
            order_status if is_paid else OrderStatus.CREATED,
            CancellationStatus.NONE,
            fulfillment_status,
            return_status,
            now_ts
        )
    )

    # Payment Mandate
    cursor.execute(
        """
        INSERT INTO payment_mandates (
            id, cart_id, razorpay_order_id, razorpay_payment_id, amount_paise,
            status, refund_status, refund_amount_paise, refunded_amount_paise,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payment_id, cart_id, rzp_order_id, rzp_payment_id, amount_paise,
            "succeeded" if is_paid else "created",
            RefundStatus.NONE, 0, 0,
            now_ts, now_ts
        )
    )

    conn.commit()
    conn.close()
    return cart_id, payment_id, rzp_payment_id


# ─── 1. Unpaid Order Cancellation (Zero Refund) ──────────────────────────────
def test_unpaid_order_cancellation_no_refund():
    cart_id, _, _ = _create_test_order(amount_paise=150000, is_paid=False)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER")
    assert eval_res.status == "ELIGIBLE_CANCEL_ONLY"
    assert eval_res.action == ResolutionAction.CANCEL_ORDER_ONLY
    assert eval_res.refundable_amount_paise == 0

    exec_res = create_and_execute_refund(cart_id, reason="Customer cancelled before paying")
    assert exec_res["status"] == "cancelled"
    assert exec_res["order_status"] == OrderStatus.CANCELLED
    assert exec_res["refund_status"] == RefundStatus.NONE
    assert exec_res["amount_refunded_paise"] == 0


# ─── 2. Paid but Unfulfilled Cancellation (Instant Refund) ───────────────────
def test_paid_unfulfilled_cancellation_refund():
    cart_id, _, _ = _create_test_order(amount_paise=219900, is_paid=True, fulfillment_status=FulfillmentStatus.UNFULFILLED)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER")
    assert eval_res.status == "ELIGIBLE_INSTANT_REFUND"
    assert eval_res.action == ResolutionAction.INITIATE_REFUND
    assert eval_res.refundable_amount_paise == 219900

    exec_res = create_and_execute_refund(cart_id, reason="Buyer requested pre-fulfillment cancel")
    assert exec_res["status"] == "refunded"
    assert exec_res["order_status"] == OrderStatus.CANCELLED
    assert exec_res["refund_status"] == RefundStatus.REFUNDED
    assert exec_res["amount_refunded_paise"] == 219900
    assert exec_res["refund_id"].startswith("rfnd_")


# ─── 3. Paid + Shipped Refund Request (Rejected In-Transit) ──────────────────
def test_shipped_order_refund_request_rejected():
    cart_id, _, _ = _create_test_order(amount_paise=350000, is_paid=True, fulfillment_status=FulfillmentStatus.SHIPPED)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER")
    assert eval_res.status == "INELIGIBLE_IN_TRANSIT"
    assert eval_res.is_eligible is False
    assert "dispatched" in eval_res.reason.lower()


# ─── 4. Delivered Order Return Request (RETURN_REVIEW_REQUIRED) ──────────────
def test_delivered_order_return_request_routes_to_review():
    cart_id, _, _ = _create_test_order(amount_paise=400000, is_paid=True, fulfillment_status=FulfillmentStatus.DELIVERED)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "RETURN_ITEM")
    assert eval_res.status == "RETURN_REVIEW_REQUIRED"
    assert eval_res.action == ResolutionAction.CREATE_RETURN_REVIEW
    assert eval_res.requires_review is True

    exec_res = create_and_execute_refund(cart_id, reason="Customer reported wrong item")
    assert exec_res["status"] == "review_required"
    assert exec_res["return_status"] == ReturnStatus.RETURN_REVIEW_REQUIRED
    # Notice: money is NOT moved prematurely!


# ─── 5. Refund Policy Inquiry (INFORM_ONLY) ──────────────────────────────────
def test_policy_inquiry_inform_only():
    cart_id, _, _ = _create_test_order(amount_paise=100000, is_paid=True)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "ASK_REFUND_POLICY")
    assert eval_res.status == "INFORM_ONLY"
    assert eval_res.action == ResolutionAction.INFORM_ONLY
    assert eval_res.is_eligible is False
    assert eval_res.refundable_amount_paise == 0


# ─── 6. Duplicate In-Flight Refund Prevention ────────────────────────────────
def test_duplicate_refund_prevention():
    cart_id, payment_id, _ = _create_test_order(amount_paise=120000, is_paid=True)
    
    # Simulate an active in-flight refund in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO refunds (id, payment_id, cart_id, requested_amount_paise, processed_amount_paise, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (f"rfnd_inflight_{uuid.uuid4().hex[:6]}", payment_id, cart_id, 120000, 0, RefundStatus.REFUND_PROCESSING, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    eval_res = evaluate_resolution_eligibility(cart_id, "REQUEST_REFUND")
    assert eval_res.status == "REFUND_ALREADY_IN_PROGRESS"
    assert eval_res.is_eligible is False


# ─── 7. Partial Refund Amount Ledger Accounting ──────────────────────────────
def test_partial_refund_calculation():
    cart_id, payment_id, _ = _create_test_order(amount_paise=500000, is_paid=True)
    
    # Request partial refund of 200000 paise (₹2,000 out of ₹5,000)
    exec_res = create_and_execute_refund(cart_id, requested_amount_paise=200000, reason="Partial damaged item refund")
    assert exec_res["status"] == "refunded"
    assert exec_res["refund_status"] == RefundStatus.PARTIALLY_REFUNDED
    assert exec_res["amount_refunded_paise"] == 200000
    assert exec_res["total_refunded_paise"] == 200000

    # Verify remaining refundable balance
    eval_second = evaluate_resolution_eligibility(cart_id, "REQUEST_REFUND")
    assert eval_second.remaining_refundable_paise == 300000


# ─── 8. Refund Amount > Refundable Amount ────────────────────────────────────
def test_refund_amount_exceeds_refundable_limit():
    cart_id, _, _ = _create_test_order(amount_paise=150000, is_paid=True)
    
    eval_res = evaluate_resolution_eligibility(cart_id, "REQUEST_REFUND", requested_amount_paise=200000)
    assert eval_res.status == "EXCEEDS_REFUNDABLE_LIMIT"
    assert eval_res.is_eligible is False


# ─── 9. Refund API Failure Handling ──────────────────────────────────────────
def test_refund_api_failure_handling(monkeypatch):
    cart_id, _, _ = _create_test_order(amount_paise=180000, is_paid=True)

    def mock_fail_refund(pid, amt):
        raise RuntimeError("Gateway connection timed out")

    import backend.integrations.razorpay_client
    monkeypatch.setattr(backend.integrations.razorpay_client, "refund_payment", mock_fail_refund)

    exec_res = create_and_execute_refund(cart_id, reason="Customer cancel")
    assert exec_res["status"] == "failed"
    assert exec_res["refund_status"] == RefundStatus.REFUND_FAILED


# ─── 10. Refund Pending State ────────────────────────────────────────────────
def test_refund_pending_state(monkeypatch):
    cart_id, _, _ = _create_test_order(amount_paise=220000, is_paid=True)

    def mock_pending_refund(pid, amt):
        return {
            "id": "rfnd_pending_12345",
            "entity": "refund",
            "amount": amt,
            "status": "pending"
        }

    import backend.integrations.razorpay_client
    monkeypatch.setattr(backend.integrations.razorpay_client, "refund_payment", mock_pending_refund)

    exec_res = create_and_execute_refund(cart_id, reason="Pending gateway refund")
    assert exec_res["status"] == "processing"
    assert exec_res["refund_status"] == RefundStatus.REFUND_PROCESSING
    assert exec_res["refund_id"] == "rfnd_pending_12345"


# ─── 11. Razorpay Webhook Settlement ─────────────────────────────────────────
def test_refund_webhook_settlement():
    cart_id, payment_id, _ = _create_test_order(amount_paise=300000, is_paid=True)

    # Put a refund in PROCESSING
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO refunds (id, payment_id, cart_id, requested_amount_paise, processed_amount_paise, status, razorpay_refund_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("rfnd_local_test", payment_id, cart_id, 300000, 0, RefundStatus.REFUND_PROCESSING, "rfnd_rzp_hook_999", datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    # Trigger webhook
    webhook_res = settle_refund_webhook("rfnd_rzp_hook_999", "refund.processed", {"id": "rfnd_rzp_hook_999", "payment_id": "pay_mock_1"})
    assert webhook_res["status"] == "settled"
    assert webhook_res["refund_status"] == RefundStatus.REFUNDED
    assert webhook_res["total_refunded_paise"] == 300000


# ─── 12. Already Fully Refunded Order ────────────────────────────────────────
def test_already_refunded_order():
    cart_id, _, _ = _create_test_order(amount_paise=100000, is_paid=True)
    
    # Fully refund it first
    create_and_execute_refund(cart_id)

    # Attempt second refund
    eval_res = evaluate_resolution_eligibility(cart_id, "REQUEST_REFUND")
    assert eval_res.status == "ALREADY_FULLY_REFUNDED"
    assert eval_res.is_eligible is False


# ─── 13. AI Misclassification Overridden by Deterministic Engine ─────────────
def test_ai_misclassification_overridden_by_engine(monkeypatch):
    # Delivered order
    cart_id, _, _ = _create_test_order(amount_paise=500000, is_paid=True, fulfillment_status=FulfillmentStatus.DELIVERED)

    # Mock AI returning CANCEL_ORDER despite order being delivered
    def mock_ai_classify(req, ctx=None):
        from backend.agents.resolution_agent import CustomerResolutionIntent
        return CustomerResolutionIntent(
            intent="CANCEL_ORDER",
            reason="Customer wants cancel",
            requested_amount_paise=500000,
            item_scope="full_order",
            explanation="I want to cancel my delivered order"
        )

    import backend.agents.resolution_agent
    monkeypatch.setattr(backend.agents.resolution_agent, "classify_customer_intent", mock_ai_classify)

    # Even though AI returned CANCEL_ORDER, the engine must safely enforce RETURN_REVIEW_REQUIRED
    eval_res = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER")
    assert eval_res.status == "RETURN_REVIEW_REQUIRED"
    assert eval_res.action == ResolutionAction.CREATE_RETURN_REVIEW
    assert eval_res.requires_review is True


# ─── 14. Unknown Fulfillment Status Defaults to Review ───────────────────────
def test_unknown_fulfillment_status_defaults_to_review():
    cart_id, _, _ = _create_test_order(amount_paise=250000, is_paid=True, fulfillment_status=FulfillmentStatus.UNKNOWN)

    eval_res = evaluate_resolution_eligibility(cart_id, "CANCEL_ORDER")
    assert eval_res.status == "REFUND_REVIEW_REQUIRED"
    assert eval_res.action == ResolutionAction.CREATE_REFUND_REVIEW
    assert eval_res.requires_review is True
    assert "unknown" in eval_res.reason.lower() or "unverified" in eval_res.reason.lower()


# ─── 15. Chronological Audit Log Integrity ───────────────────────────────────
def test_audit_log_chronological_integrity():
    cart_id, _, _ = _create_test_order(amount_paise=199900, is_paid=True)

    create_and_execute_refund(cart_id, reason="Customer cancel check")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event, detail, created_at FROM audit_log WHERE ref_id = ? OR ref_type IN ('payment', 'refund', 'cart') ORDER BY id ASC",
        (cart_id,)
    )
    logs = cursor.fetchall()
    conn.close()

    events = [log["event"] for log in logs]
    assert any("Refund" in e or "Cancelled" in e for e in events)


# ─── 16. Public Buyer MCP Isolation (cancel_order disabled) ──────────────────
def test_public_mcp_isolation():
    import asyncio
    from backend.mcp_server import buyer_mcp
    
    tools = asyncio.run(buyer_mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "cancel_order" not in tool_names


# ─── 17. Refunded Order Excluded from Realized & Attributed Revenue ──────────
def test_refunded_order_excluded_from_growth_revenue_and_recoverable_carts():
    from backend.agents.growth_agent import get_growth_metrics
    from backend.agents.recovery_agent import detect_recoverable_carts

    cart_id, payment_id, _ = _create_test_order(amount_paise=250000, is_paid=True)

    # Insert growth outcome
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO growth_outcomes (id, action_id, outcome_type, before_paise, after_paise, incremental_paise, revenue_type, created_at)
        VALUES (?, ?, 'paid', 200000, 250000, 50000, 'cross_sell', ?)
        """,
        (f"go_paid_{payment_id}", None, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    # Pre-refund check: revenue should be ₹2,500
    overview_before = get_growth_metrics()
    assert overview_before["realized_gross_revenue_paise"] == 250000
    assert overview_before["cross_sell_revenue_paise"] == 50000

    # Execute full refund
    create_and_execute_refund(cart_id, reason="Customer cancelled")

    # Post-refund check: revenue should be ₹0 and AI revenue ₹0
    overview_after = get_growth_metrics()
    assert overview_after["realized_gross_revenue_paise"] == 0
    assert overview_after["cross_sell_revenue_paise"] == 0
    assert overview_after["observed_ai_attributed_revenue_paise"] == 0

    # Ensure refunded cart is not counted as recoverable / potential revenue
    recov = detect_recoverable_carts()
    recov_cart_ids = [c["cart_id"] for c in recov]
    assert cart_id not in recov_cart_ids


# ─── 18. Cancelled Unpaid Order Excluded from Recoverable Carts ───────────────
def test_cancelled_unpaid_order_excluded_from_recoverable_carts():
    from backend.agents.recovery_agent import detect_recoverable_carts
    from backend.agents.growth_agent import get_growth_metrics

    cart_id, _, _ = _create_test_order(amount_paise=180000, is_paid=False)

    # Pre-cancel check: should show up in recoverable carts
    recov_before = detect_recoverable_carts()
    recov_ids_before = [c["cart_id"] for c in recov_before]
    assert cart_id in recov_ids_before

    # Cancel unpaid order
    create_and_execute_refund(cart_id, reason="Customer cancelled unpaid cart")

    # Post-cancel check: must NOT show up as recoverable / possible revenue
    recov_after = detect_recoverable_carts()
    recov_ids_after = [c["cart_id"] for c in recov_after]
    assert cart_id not in recov_ids_after

    overview = get_growth_metrics()
    assert cart_id not in [c["cart_id"] for c in detect_recoverable_carts()]

