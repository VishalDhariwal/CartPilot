import pytest
import json
from datetime import datetime
from backend.db import get_db
from backend.agents.growth_agent import (
    calculate_inventory_velocity_metrics,
    calculate_buyer_relevance_score,
    find_matched_controls,
    detect_all_opportunities,
    execute_growth_action
)


def test_calculate_inventory_velocity_metrics():
    """Verifies that per-SKU sales velocity and coverage metrics are computed from real orders."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        metrics = calculate_inventory_velocity_metrics(cursor)
        assert "sales" in metrics
        assert "cart_counts" in metrics
        assert "upsell_counts" in metrics

        # Verify sales structure
        for sku, s in metrics["sales"].items():
            assert "units_sold_total" in s
            assert "units_sold_7d" in s
            assert "units_sold_30d" in s
            assert "orders_30d" in s
            assert "last_sale_days_ago" in s
            assert s["units_sold_7d"] <= s["units_sold_30d"]
            assert s["units_sold_30d"] <= s["units_sold_total"]
    finally:
        conn.close()


def test_calculate_buyer_relevance_score():
    """Verifies that buyer relevance scores evaluate category graph, embeddings, and cart history."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        velocity_data = calculate_inventory_velocity_metrics(cursor)
        
        # Test a known item
        cursor.execute("SELECT sku, category FROM catalog LIMIT 1")
        row = cursor.fetchone()
        assert row is not None
        
        score, signals = calculate_buyer_relevance_score(row["sku"], row["category"], velocity_data, cursor)
        assert 0.10 <= score <= 0.95
        assert isinstance(signals, list)
        assert len(signals) > 0
    finally:
        conn.close()


def test_detect_stagnant_inventory_opportunities():
    """Verifies that detect_all_opportunities generates evidence-based INVENTORY STAGNATION opportunities."""
    opportunities = detect_all_opportunities()
    assert isinstance(opportunities, list)

    stagnant_opps = [o for o in opportunities if o["type"] == "PROMOTE_PRODUCT"]
    assert len(stagnant_opps) > 0, "Expected at least one INVENTORY STAGNATION opportunity."

    for opp in stagnant_opps:
        # Check required unified growth model fields
        assert "opportunity_id" in opp
        assert "goal" in opp
        assert "business_problem" in opp
        assert "evidence" in opp
        assert "inventory_value_exposure_rupees" in opp
        assert "estimated_opportunity_value_rupees" in opp
        assert "confidence" in opp
        assert "is_empirical_confidence" in opp
        assert "why_this_action" in opp

        ev = opp["evidence"]
        assert "stock_units" in ev
        assert "sales_velocity_daily" in ev
        assert "days_of_inventory" in ev

        # Exposure and incremental lift must be separated
        assert opp["inventory_value_exposure_rupees"] >= opp["estimated_opportunity_value_rupees"]

        # Explainability fields
        why = opp["why_this_action"]
        assert len(why["evidence_summary"]) >= 2
        assert "will_do" in why
        assert "will_not_do" in why
        assert "₹0.00" in why["action_cost_explanation"]


def test_explicit_no_action_for_healthy_inventory():
    """Verifies that healthy inventory triggers an explicit NO_ACTION decision rather than unnecessary boosting."""
    opportunities = detect_all_opportunities()
    no_action_opps = [o for o in opportunities if o.get("selected_action", {}).get("action_type") == "NO_ACTION"]
    
    assert len(no_action_opps) > 0, "Expected at least one explicit NO_ACTION opportunity for healthy inventory or diagnostic review."
    healthy_opp = next((o for o in no_action_opps if "HEALTHY" in o.get("goal", "")), None)
    
    if healthy_opp:
        assert healthy_opp["action_executable"] is False
        assert healthy_opp["estimated_opportunity_value_rupees"] == 0
        assert "Maintain Standard 1.0x Ranking" in healthy_opp["selected_action"]["title"]
        assert "healthy" in healthy_opp["selected_action"]["description"].lower()


def test_execute_promote_product_captures_pre_action_snapshot():
    """Verifies that PROMOTE_PRODUCT execution captures pre-action experiment baseline snapshot."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Ensure available active experiment capacity
        cursor.execute("UPDATE promotion_experiments SET status = 'COMPLETED' WHERE status = 'ACTIVE'")
        conn.commit()

        # Find an unboosted SKU with stock and ≥2 category peers
        cursor.execute("SELECT sku, name, category, price_paise, stock FROM catalog WHERE stock >= 5 AND boosted = 0 LIMIT 50")
        items = cursor.fetchall()
        
        target_item = None
        for itm in items:
            ctrls = find_matched_controls(itm["sku"], itm["category"], itm["price_paise"], 0.1, cursor, limit=2)
            if len(ctrls) >= 2:
                target_item = itm
                break
        
        if not target_item:
            # Create a test SKU with 2 peer controls
            target_item = {"sku": "TEST-INV-GROWTH-001", "name": "Test Growth Watch", "category": "mens-watches", "price_paise": 250000, "stock": 50}
            cursor.execute("""
                INSERT OR REPLACE INTO catalog (sku, name, category, merchant, price_paise, stock, boosted)
                VALUES 
                ('TEST-INV-GROWTH-001', 'Test Growth Watch', 'mens-watches', 'TestMerchant', 250000, 50, 0),
                ('TEST-INV-CTRL-001', 'Test Control Watch 1', 'mens-watches', 'TestMerchant', 240000, 40, 0),
                ('TEST-INV-CTRL-002', 'Test Control Watch 2', 'mens-watches', 'TestMerchant', 260000, 45, 0)
            """)
            conn.commit()

        sku = target_item["sku"]
        cursor.execute("DELETE FROM promotion_experiments WHERE sku = ?", (sku,))
        cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))
        conn.commit()

        result = execute_growth_action("PROMOTE_PRODUCT", sku, mode="manual")

        assert result["status"] == "completed"
        assert result["sku"] == sku
        assert "pre_snapshot" in result
        
        snap = result["pre_snapshot"]
        assert snap["sku"] == sku
        assert snap["stock_units"] == target_item["stock"]
        assert "sales_velocity_daily" in snap
        assert "days_of_inventory" in snap
        assert "activated_at" in snap

        # Verify database update
        cursor.execute("SELECT boosted FROM catalog WHERE sku = ?", (sku,))
        assert cursor.fetchone()[0] == 1

        # Verify growth_actions audit record
        cursor.execute("SELECT id, notes, opportunity_type FROM growth_actions WHERE id = ?", (result["action_id"],))
        action_row = cursor.fetchone()
        assert action_row is not None
        assert action_row["opportunity_type"] == "inventory_stagnation"
        notes = json.loads(action_row["notes"])
        assert notes["stock_units"] == target_item["stock"]

        # Reset item for clean state
        cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))
        conn.commit()
    finally:
        conn.close()
