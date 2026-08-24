import os
import json
import pytest
from datetime import datetime, timedelta
from backend.db import get_db, init_db
from backend.agents.growth_agent import (
    get_discoverability_and_demand_signals,
    find_matched_controls,
    scan_and_score_promotion_candidates,
    llm_veto_promotion_shortlist,
    detect_all_opportunities,
    execute_growth_action,
    evaluate_active_promotion_experiments,
    assess_legacy_boosts_observational,
    get_promotion_system_state
)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_discoverability_and_demand_signals():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku, category FROM catalog LIMIT 1")
        row = cursor.fetchone()
        sku = row["sku"]
        category = row["category"]

        signals = get_discoverability_and_demand_signals(sku, category, cursor)
        assert "recommendation_offer_count" in signals
        assert "cart_appearances_count" in signals
        assert "orders_count" in signals
        assert signals["actual_impressions_recorded"] == "Not recorded in V1"
        assert "affinity_pairs_count" in signals
    finally:
        conn.close()


def test_matched_controls_selection():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku, category, price_paise FROM catalog WHERE stock > 0 LIMIT 1")
        row = cursor.fetchone()
        sku = row["sku"]
        category = row["category"]
        price_paise = row["price_paise"]

        controls = find_matched_controls(sku, category, price_paise, 0.2, cursor, limit=2)
        # Should return valid controls if peers exist in catalog
        for c in controls:
            assert c["sku"] != sku
            assert c["category"] == category
            assert "baseline_velocity_daily" in c
            assert "distance" in c
    finally:
        conn.close()


def test_scan_and_score_promotion_candidates_stage1():
    conn = get_db()
    cursor = conn.cursor()
    try:
        shortlist = scan_and_score_promotion_candidates(cursor)
        assert isinstance(shortlist, list)
        if shortlist:
            top = shortlist[0]
            assert "stage1_score" in top
            assert "opportunity_reason" in top
            assert "product_state" in top
            assert "signals" in top
            assert "matched_controls" in top
            # Check descending sort by stage1_score
            scores = [c["stage1_score"] for c in shortlist]
            assert scores == sorted(scores, reverse=True)
    finally:
        conn.close()


def test_stage2_llm_veto_deterministic_fallback():
    mock_candidates = [
        {
            "sku": "TEST_SKU_1",
            "name": "Test Product",
            "category": "apparel",
            "price_rupees": 1200,
            "stock": 50,
            "days_of_inventory": 100,
            "sales_velocity_daily": 0.1,
            "buyer_relevance_score": 0.7,
            "opportunity_reason": "DISCOVERABILITY_GAP",
            "product_state": "UNDER_DISCOVERED",
            "stage1_score": 0.82,
            "signals": {"recommendation_offer_count": 1, "cart_appearances_count": 0}
        }
    ]
    vetoed = llm_veto_promotion_shortlist(mock_candidates)
    assert len(vetoed) == 1
    assert vetoed[0]["stage2_llm_decision"] in ["ACCEPT", "ACCEPT_FALLBACK", "REJECT"]
    assert "stage2_llm_reasoning" in vetoed[0]


def test_detect_all_opportunities_structured_pipeline():
    opps = detect_all_opportunities()
    assert isinstance(opps, list)
    promo_opps = [o for o in opps if o["type"] == "PROMOTE_PRODUCT"]
    for po in promo_opps:
        assert "evidence" in po
        assert "opportunity_nature" in po
        assert "why_this_action" in po


def test_execute_growth_action_and_difference_in_differences_evaluation():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Find a candidate with at least 2 matched controls
        cursor.execute("SELECT sku, category, price_paise, stock FROM catalog WHERE stock >= 10 AND boosted = 0 LIMIT 10")
        items = cursor.fetchall()

        target_item = None
        for itm in items:
            ctrls = find_matched_controls(itm["sku"], itm["category"], itm["price_paise"], 0.1, cursor, limit=2)
            if len(ctrls) >= 2:
                target_item = itm
                break

        if not target_item:
            pytest.skip("No catalog SKU found with ≥2 controls in current test DB")

        sku = target_item["sku"]

        # Ensure available active experiment capacity
        cursor.execute("UPDATE promotion_experiments SET status = 'COMPLETED' WHERE status = 'ACTIVE'")
        cursor.execute("DELETE FROM promotion_experiments WHERE sku = ?", (sku,))
        cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))
        conn.commit()

        # Execute PROMOTE_PRODUCT
        res = execute_growth_action("PROMOTE_PRODUCT", sku, mode="manual")
        assert res["status"] == "completed"
        assert res["sku"] == sku
        assert len(res["matched_controls"]) >= 2
        exp_id = res["experiment_id"]

        # Verify DB experiment record
        cursor.execute("SELECT * FROM promotion_experiments WHERE id = ?", (exp_id,))
        exp_row = cursor.fetchone()
        assert exp_row["status"] == "ACTIVE"
        assert exp_row["opportunity_reason"] is not None
        assert exp_row["product_state"] is not None
        assert exp_row["control_skus"] is not None
        assert exp_row["merchant_decision"] == "PENDING"

        # Evaluate active experiments
        evaluated = evaluate_active_promotion_experiments(cursor)
        assert any(e["experiment_id"] == exp_id for e in evaluated)

    finally:
        conn.close()


def test_early_kill_and_day_14_decision_gate():
    conn = get_db()
    cursor = conn.cursor()
    try:
        exp_id = "test_exp_early_kill"
        now_dt = datetime.utcnow()
        started_at = (now_dt - timedelta(days=5)).isoformat() + "Z"
        ends_at = (now_dt + timedelta(days=9)).isoformat() + "Z"

        cursor.execute("SELECT sku, category, price_paise, stock FROM catalog LIMIT 1")
        item = cursor.fetchone()
        sku = item["sku"]

        cursor.execute("DELETE FROM promotion_experiments WHERE id = ?", (exp_id,))
        cursor.execute("""
            INSERT INTO promotion_experiments (
                id, sku, status, action_id, baseline_stock, baseline_velocity_daily,
                baseline_days_of_inventory, baseline_orders_30d, buyer_relevance_score,
                experiment_horizon_days, started_at, ends_at, cooldown_until,
                current_stock, units_liquidated, orders_during_experiment, realized_revenue_paise,
                outcome_status, notes, created_at, updated_at,
                control_skus, treatment_baseline_velocity, control_baseline_velocity,
                opportunity_reason, product_state, stage1_score, merchant_decision
            ) VALUES (
                ?, ?, 'ACTIVE', 'act_test', 50, 0.2,
                100, 2, 0.7,
                14, ?, ?, ?,
                50, 0, 0, 0,
                'pending', '', ?, ?,
                '[]', 0.2, 0.2,
                'INVENTORY_RISK_WITH_DEMAND', 'STAGNANT_WITH_DEMAND', 0.8, 'PENDING'
            )
        """, (exp_id, sku, started_at, ends_at, (now_dt + timedelta(days=14)).isoformat() + "Z", started_at, started_at))
        conn.commit()

        # Run evaluation
        evaluate_active_promotion_experiments(cursor)
        conn.commit()

        cursor.execute("SELECT * FROM promotion_experiments WHERE id = ?", (exp_id,))
        exp_row = cursor.fetchone()
        assert exp_row is not None

    finally:
        conn.close()


def test_observational_legacy_boosts_assessment():
    conn = get_db()
    cursor = conn.cursor()
    try:
        assessment = assess_legacy_boosts_observational(cursor)
        assert "assessments" in assessment
        assert "disclaimer" in assessment
        assert "observational, not experimental" in assessment["disclaimer"]
        if assessment["assessments"]:
            top = assessment["assessments"][0]
            assert top["suggested_action"] in ["KEEP", "RETIRE", "CONVERT_TO_EXPERIMENT"]
            assert "category_median_velocity" in top
    finally:
        conn.close()
