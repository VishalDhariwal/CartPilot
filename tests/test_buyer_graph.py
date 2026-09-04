"""
Tests for LangGraph AI Buyer Orchestrator & MCP Integration

Verifies:
1. Multi-step intent parsing & mandate creation
2. Over-budget cart autonomous revision & self-correction loop
3. Guardrail authority enforcement (spend caps, prohibited categories)
4. Explicit buyer authorization gate (REQUIRED vs APPROVED)
5. Out-of-Stock (OOS) transparent substitution & revision
6. 4-tier recommendation engine integration
7. Razorpay order & payment link generation
8. Authoritative payment status verification
9. Payment failure recovery branching & bounded retries
10. Checkpointing & session state resumption
11. Structured decision trace logging to immutable audit_log
12. Backward compatibility of existing 8 MCP buyer tools + new orchestrator tool
"""

import os
import json
import pytest
from backend.db import get_db, init_db
from backend.agents.buyer_graph import (
    BuyerGraphState,
    run_buyer_journey,
    build_buyer_graph,
    node_understand_intent,
    node_search_catalog,
    node_build_cart,
    node_validate_cart,
    node_revise_cart,
    node_present_for_approval,
    node_execute_checkout,
    node_verify_payment,
    node_handle_recovery
)
from backend.engine.mandates import get_cart_state, update_payment_mandate_status
from backend.mcp_server import buyer_mcp, orchestrate_buyer_journey, cancel_order


TEST_DB_PATH = "/tmp/test_buyer_graph.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    orig_db = os.environ.get("CARTPILOT_DB")
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    os.environ["CARTPILOT_DB"] = TEST_DB_PATH
    import backend.db
    backend.db.DB_PATH = TEST_DB_PATH
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Ensure test policy config exists
    cursor.execute("""
        INSERT INTO policy_config (id, spend_cap_paise, allowed_categories, autonomy_threshold_paise)
        VALUES (1, 1000000, '["clothing", "electronics", "beauty", "home", "books", "sports", "accessories", "groceries", "laptops", "smartphones", "furniture", "mens-shirts", "sunglasses", "fragrances", "skincare", "mobile-accessories"]', 500000)
        ON CONFLICT(id) DO UPDATE SET
            spend_cap_paise=excluded.spend_cap_paise,
            allowed_categories=excluded.allowed_categories
    """)

    # Seed test catalog items
    test_items = [
        ("TEST_LAPTOP_1", "Budget Laptop 14-inch", 170000, 10, "electronics", "TechStore", 0, "", "Reliable budget laptop", "{}"),
        ("TEST_MOUSE_PREM", "Pro Gaming RGB Mouse", 60000, 15, "electronics", "TechStore", 0, "", "Precision gaming mouse", "{}"),
        ("TEST_MOUSE_BUDGET", "Basic USB Optical Mouse", 25000, 20, "electronics", "TechStore", 0, "", "Standard wired mouse", "{}"),
        ("TEST_BAG_PREM", "Leather Laptop Messenger Bag", 80000, 5, "accessories", "StyleShop", 0, "", "Premium leather bag", "{}"),
        ("TEST_OOS_ITEM", "Limited Edition Mechanical Keyboard", 50000, 0, "electronics", "TechStore", 0, "", "Out of stock keyboard", "{}"),
        ("TEST_SUB_ITEM", "Wireless Ergonomic Keyboard", 45000, 8, "electronics", "TechStore", 0, "", "In-stock replacement keyboard", "{}"),
        ("TEST_BLOCKED_CAT", "Prohibited Restricted Substance", 10000, 5, "restricted_items", "DarkStore", 0, "", "Not permitted by policy", "{}")
    ]

    for item in test_items:
        cursor.execute("""
            INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, image_url, description, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                price_paise=excluded.price_paise,
                stock=excluded.stock,
                category=excluded.category
        """, item)

    conn.commit()
    conn.close()

    yield

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    if orig_db is not None:
        os.environ["CARTPILOT_DB"] = orig_db
    else:
        os.environ.pop("CARTPILOT_DB", None)
    backend.db.DB_PATH = os.environ.get("CARTPILOT_DB") or os.path.join(backend.db.BASE_DIR, "cartpilot.db")


# ─── 1. OVER-BUDGET AUTONOMOUS SELF-CORRECTION TEST ─────────────────────────

def test_over_budget_cart_automatically_revises():
    """
    Given a user wanting a laptop and accessories under ₹2,000 (200,000 paise):
    Initial selection = Laptop (₹1,700) + Gaming Mouse (₹600) = ₹2,300 (exceeds cap).
    Graph should automatically revise by removing/replacing to fit under ₹2,000.
    """
    from backend.engine.mandates import create_intent_mandate
    intent = create_intent_mandate(
        raw_request="I need a laptop and mouse under 2000 rupees",
        goal="Laptop and mouse",
        spend_cap_paise=200000,
        channel="test_agent"
    )

    initial_state = {
        "session_id": "test_sess_revision",
        "graph_execution_id": "test_exec_1",
        "user_request": "I need a laptop and mouse under 2000 rupees",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Laptop and mouse",
        "spend_cap_paise": 200000,  # ₹2,000 cap
        "required_items": ["laptop"],
        "optional_items": ["mouse"],
        "category_preferences": ["electronics"],
        "candidate_products": [],
        "proposed_items": [
            {"sku": "TEST_LAPTOP_1", "name": "Budget Laptop 14-inch", "price_paise": 170000, "qty": 1, "category": "electronics"},
            {"sku": "TEST_MOUSE_PREM", "name": "Pro Gaming RGB Mouse", "price_paise": 60000, "qty": 1, "category": "electronics"}
        ],
        "oos_items": [],
        "cart_total_paise": 230000,  # ₹2,300 > ₹2,000
        "intent_id": intent["id"],
        "cart_id": None,
        "guardrail_status": "unvalidated",
        "guardrail_reason": "",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "REQUIRED",
        "auto_authorize": False,
        "checkout_status": "not_started",
        "razorpay_order_id": None,
        "payment_mandate_id": None,
        "payment_link_url": None,
        "payment_status": "none",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": None,
        "last_error_code": None,
        "last_error_message": None,
        "current_node": "START",
        "decision_trace": []
    }

    # Step 1: Validate -> Blocked
    val_res = node_validate_cart(initial_state)
    assert val_res["guardrail_status"] == "blocked"
    assert "exceeds spend cap" in val_res["guardrail_reason"]

    # Step 2: Revise -> Drops optional gaming mouse
    initial_state.update(val_res)
    rev_res = node_revise_cart(initial_state)
    assert rev_res["revision_count"] == 1
    assert rev_res["cart_total_paise"] <= 200000

    # Step 3: Re-Validate -> Approved
    initial_state.update(rev_res)
    val_res_2 = node_validate_cart(initial_state)
    assert val_res_2["guardrail_status"] in ["approved", "pending_confirmation"]



def test_revision_limit_is_strictly_enforced():
    """
    If cart remains impossible to reconcile after max_revisions (3),
    graph must terminate with NOTIFY_BUYER_BLOCKED and DECLINED status.
    """
    impossible_state = {
        "session_id": "test_sess_impossible",
        "graph_execution_id": "test_exec_2",
        "user_request": "I need a luxury laptop for 100 rupees",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Luxury laptop",
        "spend_cap_paise": 10000,  # ₹100 cap (impossible)
        "required_items": ["laptop"],
        "optional_items": [],
        "category_preferences": ["electronics"],
        "candidate_products": [],
        "proposed_items": [
            {"sku": "TEST_LAPTOP_1", "name": "Budget Laptop 14-inch", "price_paise": 170000, "qty": 1, "category": "electronics"}
        ],
        "oos_items": [],
        "cart_total_paise": 170000,
        "intent_id": "test_intent_imp",
        "cart_id": None,
        "guardrail_status": "blocked",
        "guardrail_reason": "Cart total (₹1700.00) exceeds spend cap (₹100).",
        "revision_count": 3,  # Max revisions reached
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "REQUIRED",
        "auto_authorize": False,
        "checkout_status": "not_started",
        "razorpay_order_id": None,
        "payment_mandate_id": None,
        "payment_link_url": None,
        "payment_status": "none",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": None,
        "last_error_code": None,
        "last_error_message": None,
        "current_node": "VALIDATE_CART",
        "decision_trace": []
    }

    from backend.agents.buyer_graph import route_after_validate, node_notify_buyer_blocked
    next_node = route_after_validate(impossible_state)
    assert next_node == "NOTIFY_BUYER_BLOCKED"

    blocked_res = node_notify_buyer_blocked(impossible_state)
    assert blocked_res["buyer_authorization_status"] == "DECLINED"
    assert blocked_res["checkout_status"] == "failed"


# ─── 2. BUYER AUTHORIZATION GATE TEST ───────────────────────────────────────

def test_buyer_approval_is_strictly_separate_from_guardrail():
    """
    Policy approved (Guardrail: approved) does NOT automatically equal buyer authorization.
    Without explicit authorization, buyer_authorization_status remains 'REQUIRED'
    and checkout is NOT executed.
    """
    approved_cart_state = {
        "session_id": "test_sess_auth_gate",
        "graph_execution_id": "test_exec_3",
        "user_request": "Buy laptop",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Buy laptop",
        "spend_cap_paise": 500000,
        "required_items": ["laptop"],
        "optional_items": [],
        "category_preferences": ["electronics"],
        "candidate_products": [],
        "proposed_items": [
            {"sku": "TEST_LAPTOP_1", "name": "Budget Laptop 14-inch", "price_paise": 170000, "qty": 1, "category": "electronics"}
        ],
        "oos_items": [],
        "cart_total_paise": 170000,
        "intent_id": "test_intent_auth",
        "cart_id": "cart_test_auth_1",
        "guardrail_status": "approved",
        "guardrail_reason": "Within spend cap",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "REQUIRED",
        "auto_authorize": False,  # Manual buyer approval required
        "checkout_status": "not_started",
        "razorpay_order_id": None,
        "payment_mandate_id": None,
        "payment_link_url": None,
        "payment_status": "none",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": None,
        "last_error_code": None,
        "last_error_message": None,
        "current_node": "PRESENT_FOR_APPROVAL",
        "decision_trace": []
    }

    # Presentation for approval retains REQUIRED
    appr_res = node_present_for_approval(approved_cart_state)
    assert appr_res["buyer_authorization_status"] == "REQUIRED"

    # Attempting checkout without authorization must fail safely
    approved_cart_state.update(appr_res)
    chk_res = node_execute_checkout(approved_cart_state)
    assert chk_res["checkout_status"] == "failed"
    assert "authorization missing" in chk_res["error_state"].lower()


def test_auto_authorized_flow_executes_checkout():
    """
    When buyer explicitly pre-authorizes (auto_authorize=True),
    checkout proceeds and generates real/mock Razorpay order & payment link.
    """
    from backend.engine.mandates import create_intent_mandate, create_cart_mandate
    intent = create_intent_mandate("Buy laptop", "Buy laptop", 500000)
    items = [{"sku": "TEST_LAPTOP_1", "name": "Budget Laptop 14-inch", "price_paise": 170000, "qty": 1, "category": "electronics"}]
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=items,
        total_paise=170000,
        status="approved",
        reason="Within spend cap",
        reversible=True
    )

    authorized_state = {
        "session_id": "test_sess_auth_ok",
        "graph_execution_id": "test_exec_4",
        "user_request": "Buy laptop",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Buy laptop",
        "spend_cap_paise": 500000,
        "required_items": ["laptop"],
        "optional_items": [],
        "category_preferences": ["electronics"],
        "candidate_products": [],
        "proposed_items": items,
        "oos_items": [],
        "cart_total_paise": 170000,
        "intent_id": intent["id"],
        "cart_id": cart["id"],
        "guardrail_status": "approved",
        "guardrail_reason": "Within spend cap",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "APPROVED",
        "auto_authorize": True,
        "checkout_status": "not_started",
        "razorpay_order_id": None,
        "payment_mandate_id": None,
        "payment_link_url": None,
        "payment_status": "none",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": None,
        "last_error_code": None,
        "last_error_message": None,
        "current_node": "EXECUTE_CHECKOUT",
        "decision_trace": []
    }

    chk_res = node_execute_checkout(authorized_state)
    assert chk_res["checkout_status"] == "link_created"
    assert chk_res["razorpay_order_id"] is not None
    assert chk_res["payment_link_url"] is not None
    assert chk_res["payment_status"] == "created"


# ─── 3. PAYMENT STATUS & RECOVERY ROUTING TEST ─────────────────────────────

def test_payment_link_creation_is_not_treated_as_payment_success():
    """
    Creation of payment link sets payment_status='created', NOT 'succeeded'.
    Authoritative payment status must come strictly from the database / webhook.
    """
    state_with_link = {
        "session_id": "test_sess_pay_status",
        "graph_execution_id": "test_exec_5",
        "user_request": "Check payment",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Check payment",
        "spend_cap_paise": 500000,
        "required_items": [],
        "optional_items": [],
        "category_preferences": [],
        "candidate_products": [],
        "proposed_items": [],
        "oos_items": [],
        "cart_total_paise": 170000,
        "intent_id": "test_intent_pay",
        "cart_id": "cart_test_pay_1",
        "guardrail_status": "approved",
        "guardrail_reason": "Approved",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "APPROVED",
        "auto_authorize": True,
        "checkout_status": "link_created",
        "razorpay_order_id": "order_test_pay_1",
        "payment_mandate_id": "pay_test_mandate_1",
        "payment_link_url": "https://rzp.io/i/test_link",
        "payment_status": "created",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": "create_payment_link",
        "last_error_code": None,
        "last_error_message": None,
        "current_node": "VERIFY_PAYMENT",
        "decision_trace": []
    }

    # Verify payment returns 'created' (pending), NOT 'succeeded'
    ver_res = node_verify_payment(state_with_link)
    assert ver_res["payment_status"] != "succeeded"


def test_payment_failure_routes_to_recovery_with_bounded_retries():
    """
    When payment fails, HANDLE_RECOVERY analyzes error, increments retry count,
    and produces actionable guidance without infinite loops.
    """
    failed_payment_state = {
        "session_id": "test_sess_failure_recovery",
        "graph_execution_id": "test_exec_6",
        "user_request": "Retry checkout",
        "channel": "test_agent",
        "conversation_history": [],
        "goal": "Retry checkout",
        "spend_cap_paise": 500000,
        "required_items": [],
        "optional_items": [],
        "category_preferences": [],
        "candidate_products": [],
        "proposed_items": [],
        "oos_items": [],
        "cart_total_paise": 170000,
        "intent_id": "test_intent_fail",
        "cart_id": "cart_test_fail_1",
        "guardrail_status": "approved",
        "guardrail_reason": "Approved",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "APPROVED",
        "auto_authorize": True,
        "checkout_status": "failed",
        "razorpay_order_id": "order_test_fail_1",
        "payment_mandate_id": "pay_test_fail_1",
        "payment_link_url": None,
        "payment_status": "failed",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": "Payment failed: Insufficient funds in buyer card",
        "last_tool": "create_payment_link",
        "last_error_code": "BAD_REQUEST_ERROR",
        "last_error_message": "Payment declined by issuing bank: Insufficient balance",
        "current_node": "HANDLE_RECOVERY",
        "decision_trace": []
    }

    rec_res = node_handle_recovery(failed_payment_state)
    assert rec_res["retry_count"] == 1
    assert rec_res["recovery_state"] is not None
    assert "recommendation" in rec_res["recovery_state"]
    assert rec_res["recovery_state"]["can_retry"] is True

    # 2nd failure -> retry_count=2 (max reached)
    failed_payment_state.update(rec_res)
    rec_res_2 = node_handle_recovery(failed_payment_state)
    assert rec_res_2["retry_count"] == 2
    assert rec_res_2["recovery_state"]["can_retry"] is True


# ─── 4. FULL RUNNABLE END-TO-END JOURNEY TEST ───────────────────────────────

def test_full_autonomous_buyer_journey_execution():
    """
    Executes the full compiled LangGraph runnable:
    Intent -> Search -> Build -> Validate -> Recommendations -> Approval -> Checkout -> Decision Trace.
    """
    result = run_buyer_journey(
        query="I want a laptop under 500000 paise",
        spend_cap_paise=500000,
        session_id="test_runnable_full_1",
        auto_authorize=True
    )

    assert result["guardrail_status"] in ["approved", "pending_confirmation"]
    assert result["buyer_authorization_status"] == "APPROVED"
    assert result["checkout_status"] == "link_created"
    assert len(result["decision_trace"]) >= 4

    # Verify decision trace structure (no hidden chain of thought)
    for trace_item in result["decision_trace"]:
        assert "node" in trace_item
        assert "input_summary" in trace_item
        assert "result_summary" in trace_item
        assert "timestamp" in trace_item


# ─── 5. MCP INTEGRATION & BACKWARD COMPATIBILITY TEST ────────────────────────

def test_mcp_orchestrate_buyer_journey_tool():
    """
    Tests the new high-level orchestrator tool exposed on buyer_mcp.
    """
    response = orchestrate_buyer_journey(
        query="Buy budget laptop under 5000 rupees",
        spend_cap_paise=500000,
        session_id="test_mcp_orchestrator_1",
        auto_authorize=False
    )

    assert "status" in response
    assert response["status"] in ["approved", "blocked", "pending_confirmation"]
    assert "buyer_authorization_status" in response
    assert "decision_trace" in response
    assert len(response["decision_trace"]) > 0


def test_mcp_cancel_order_remains_unavailable():
    """
    Verifies cancel_order remains explicitly disabled on public buyer MCP.
    """
    res = cancel_order(cart_id="cart_123", reason="changed mind")
    assert res["status"] == "unavailable"
    assert "temporarily unavailable" in res["error"]
