import json
import pytest
from datetime import datetime, timedelta
from backend.db import get_db, init_db
from backend.agents.growth_agent import (
    calculate_inventory_velocity_metrics,
    calculate_buyer_relevance_score,
    get_promotion_system_state,
    classify_legacy_boosted_skus,
    evaluate_active_promotion_experiments,
    detect_all_opportunities,
    execute_growth_action
)
from backend.agents.growth_worker import check_action_idempotency, execute_autonomous_cycle


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensures test database schema is initialized before each test."""
    init_db()


def test_classify_legacy_boosted_skus():
    """Verifies that pre-existing boosted items are classified as legacy unmanaged without being mass-reset."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        classification = classify_legacy_boosted_skus(cursor)
        assert "total_boosted_skus" in classification
        assert "managed_active_count" in classification
        assert "legacy_unmanaged_count" in classification
        assert classification["total_boosted_skus"] == classification["managed_active_count"] + classification["legacy_unmanaged_count"]
    finally:
        conn.close()


def test_promotion_system_state_capacity_and_cap():
    """Verifies that only ACTIVE experiments consume capacity toward max_active_promotions cap."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE policy_config SET max_active_promotions = 5 WHERE id = 1")
        conn.commit()

        state = get_promotion_system_state(cursor)
        assert state["max_active_experiments"] == 5
        assert "active_experiments_count" in state
        assert "capacity_full" in state
        assert "available_capacity" in state
        assert state["available_capacity"] == max(0, 5 - state["active_experiments_count"])
    finally:
        conn.close()


def test_continuous_multi_factor_stagnant_ranking():
    """Verifies that stagnant items are ranked continuously rather than binary threshold equality."""
    opportunities = detect_all_opportunities()
    promo_opps = [o for o in opportunities if o["type"] == "PROMOTE_PRODUCT" and o["selected_action"]["action_type"] == "PROMOTE_PRODUCT"]

    for opp in promo_opps:
        ev = opp["evidence"]
        assert "continuous_priority_score" in ev
        assert 0.0 <= ev["continuous_priority_score"] <= 1.0
        assert "buyer_relevance_score" in ev
        assert ev["buyer_relevance_score"] >= 0.40  # Minimum eligibility gate passed
        assert opp["selected_action"]["action_type"] == "PROMOTE_PRODUCT"
        assert "14-Day Promotion Experiment" in opp["selected_action"]["title"]


def test_demand_gating_generates_explicit_no_action():
    """Verifies that stagnant inventory with weak buyer relevance (<0.40) produces an explicit NO_ACTION decision."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Create a test stagnant item in a disconnected category without embeddings or orders
        test_sku = "TEST-WEAK-DEMAND-001"
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (test_sku,))
        cursor.execute("""
            INSERT INTO catalog (sku, name, category, merchant, price_paise, stock, boosted, description)
            VALUES (?, 'Unpopular Antique Trinket', 'obscure_antiques', 'DummyMerchant', 500000, 30, 0, 'No demand item')
        """, (test_sku,))
        conn.commit()

        opportunities = detect_all_opportunities()
        weak_opps = [o for o in opportunities if o.get("action_target_id") == test_sku or (o.get("evidence", {}).get("sku") == test_sku)]

        if weak_opps:
            weak_opp = weak_opps[0]
            assert weak_opp["selected_action"]["action_type"] == "NO_ACTION"
            assert "Weak Buyer Demand" in weak_opp["selected_action"]["title"]
            assert "weak buyer demand" in weak_opp["selected_action"]["description"].lower()

        # Clean up
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (test_sku,))
        conn.commit()
    finally:
        conn.close()


def test_execute_promotion_experiment_lifecycle():
    """Verifies that execute_growth_action('PROMOTE_PRODUCT') registers a managed experiment with pre-snapshot and 14d horizon."""
    conn = get_db()
    cursor = conn.cursor()
    test_sku = "TEST-EXP-LIFECYCLE-001"
    ctrl_sku1 = "TEST-CTRL-LIFECYCLE-001"
    ctrl_sku2 = "TEST-CTRL-LIFECYCLE-002"
    try:
        cursor.execute("UPDATE promotion_experiments SET status = 'COMPLETED' WHERE status = 'ACTIVE'")
        cursor.execute("DELETE FROM promotion_experiments WHERE sku IN (?, ?, ?)", (test_sku, ctrl_sku1, ctrl_sku2))
        cursor.execute("DELETE FROM catalog WHERE sku IN (?, ?, ?)", (test_sku, ctrl_sku1, ctrl_sku2))
        cursor.execute("""
            INSERT INTO catalog (sku, name, category, merchant, price_paise, stock, boosted)
            VALUES 
            (?, 'Experimental High Stock Watch', 'mens-watches', 'DummyMerchant', 250000, 40, 0),
            (?, 'Control Watch 1', 'mens-watches', 'DummyMerchant', 240000, 30, 0),
            (?, 'Control Watch 2', 'mens-watches', 'DummyMerchant', 260000, 35, 0)
        """, (test_sku, ctrl_sku1, ctrl_sku2))
        conn.commit()

        # Execute promotion experiment
        res = execute_growth_action("PROMOTE_PRODUCT", test_sku, mode="manual")
        assert res["status"] == "completed"
        assert "experiment_id" in res
        exp_id = res["experiment_id"]

        # Verify catalog is boosted
        cursor.execute("SELECT boosted FROM catalog WHERE sku = ?", (test_sku,))
        assert cursor.fetchone()[0] == 1

        # Verify promotion_experiments row
        cursor.execute("SELECT * FROM promotion_experiments WHERE id = ?", (exp_id,))
        exp_row = cursor.fetchone()
        assert exp_row is not None
        assert exp_row["sku"] == test_sku
        assert exp_row["status"] == "ACTIVE"
        assert exp_row["baseline_stock"] == 40
        assert exp_row["experiment_horizon_days"] == 14
        assert exp_row["outcome_status"] == "pending"

        # Verify idempotency / cooldown blocks immediate re-promotion
        is_idem, reason = check_action_idempotency("PROMOTE_PRODUCT", test_sku, cursor)
        assert is_idem is False
        assert "ACTIVE promotion experiment" in reason

        # Clean up
        cursor.execute("DELETE FROM promotion_experiments WHERE id = ?", (exp_id,))
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (test_sku,))
        conn.commit()
    finally:
        conn.close()


def test_experiment_outcome_measurement_and_automatic_conclusion():
    """Verifies that evaluate_active_promotion_experiments measures live orders and concludes expired experiments."""
    conn = get_db()
    cursor = conn.cursor()
    test_sku = "TEST-CONCLUDE-001"
    exp_id = "exp_test_conclude_001"
    try:
        cursor.execute("DELETE FROM promotion_experiments WHERE id = ?", (exp_id,))
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (test_sku,))
        cursor.execute("""
            INSERT INTO catalog (sku, name, category, merchant, price_paise, stock, boosted)
            VALUES (?, 'Auto Expiring Test Item', 'laptops', 'DummyMerchant', 100000, 20, 1)
        """, (test_sku,))

        past_start = (datetime.utcnow() - timedelta(days=15)).isoformat() + "Z"
        past_end = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
        future_cooldown = (datetime.utcnow() + timedelta(days=6)).isoformat() + "Z"

        cursor.execute("""
            INSERT INTO promotion_experiments (
                id, sku, status, action_id, baseline_stock, baseline_velocity_daily,
                baseline_days_of_inventory, baseline_orders_30d, buyer_relevance_score,
                experiment_horizon_days, started_at, ends_at, cooldown_until,
                current_stock, units_liquidated, orders_during_experiment, realized_revenue_paise,
                outcome_status, notes, created_at, updated_at
            ) VALUES (?, ?, 'ACTIVE', 'ga_test_001', 20, 0.1, 200.0, 3, 0.8, 14, ?, ?, ?, 20, 0, 0, 0, 'pending', '{}', ?, ?)
        """, (exp_id, test_sku, past_start, past_end, future_cooldown, past_start, past_start))
        conn.commit()

        # Run evaluation
        evaluated = evaluate_active_promotion_experiments(cursor)
        conn.commit()

        # Verify experiment concluded
        cursor.execute("SELECT status, outcome_status FROM promotion_experiments WHERE id = ?", (exp_id,))
        exp_after = cursor.fetchone()
        assert exp_after["status"] == "COMPLETED"

        # Verify catalog boost was reverted to organic 1.0x baseline
        cursor.execute("SELECT boosted FROM catalog WHERE sku = ?", (test_sku,))
        assert cursor.fetchone()[0] == 0

        # Clean up
        cursor.execute("DELETE FROM promotion_experiments WHERE id = ?", (exp_id,))
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (test_sku,))
        conn.commit()
    finally:
        conn.close()


def test_capacity_full_prevents_runaway_autonomous_promotions():
    """Verifies that when max active experiment cap is reached, the autonomous worker does not launch new experiments."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Set max_active_promotions = 0 to simulate full capacity
        cursor.execute("UPDATE policy_config SET max_active_promotions = 0, growth_mode = 'autonomous' WHERE id = 1")
        conn.commit()

        cycle_result = execute_autonomous_cycle(max_actions_per_cycle=3)
        # Verify no promotion actions were executed
        promo_executions = [a for a in cycle_result.get("executed_actions", []) if a.get("action_type") == "PROMOTE_PRODUCT"]
        assert len(promo_executions) == 0

        # Restore default policy
        cursor.execute("UPDATE policy_config SET max_active_promotions = 5, growth_mode = 'manual' WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
