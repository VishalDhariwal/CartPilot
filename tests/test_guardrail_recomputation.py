import pytest
import json
from backend.db import get_db, init_db
from backend.engine.guardrail import (
    recompute_and_sanitize_cart,
    classify_reversibility,
    validate_cart,
    IRREVERSIBLE_AUTONOMY_RATIO,
    IRREVERSIBLE_HARD_BLOCK_CAP_PAISE
)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    # Ensure test items exist
    cursor.execute("""
        INSERT OR REPLACE INTO catalog (sku, name, price_paise, stock, category, merchant)
        VALUES 
        ('TEST-REV-01', 'Reversible Cotton Shirt', 100000, 50, 'mens-shirts', 'TestMerchant'),
        ('TEST-IRREV-01', 'Digital Gift Card 1000', 100000, 100, 'gift-cards', 'TestMerchant'),
        ('TEST-IRREV-EXPENSIVE', 'Custom Clearance Item', 600000, 10, 'clearance', 'TestMerchant'),
        ('TEST-OOS-01', 'Out of Stock Shoes', 200000, 0, 'mens-shoes', 'TestMerchant')
    """)
    # Set standard policy
    cursor.execute("""
        UPDATE policy_config 
        SET spend_cap_paise = 1000000, 
            autonomy_threshold_paise = 500000,
            allowed_categories = '["mens-shirts", "mens-shoes", "gift-cards", "clearance"]'
        WHERE id = 1
    """)
    conn.commit()
    conn.close()


def test_zero_trust_guardrail_ignores_llm_price_tampering():
    """
    Simulates an LLM or prompt injection attempting to pass a fake price_paise of ₹1
    for a ₹1,000 product. The guardrail MUST recompute using the catalog price.
    """
    raw_llm_items = [
        {"sku": "TEST-REV-01", "qty": 2, "price_paise": 100, "name": "Fake Cheap Shirt"}
    ]
    
    sanitized, total_paise, errors = recompute_and_sanitize_cart(raw_llm_items)
    
    assert not errors
    assert len(sanitized) == 1
    # Real catalog price is 100000 paise (₹1,000), for qty 2 = 200000 paise (₹2,000)
    assert sanitized[0]["price_paise"] == 100000
    assert sanitized[0]["item_total_paise"] == 200000
    assert total_paise == 200000


def test_out_of_stock_rejection_at_guardrail():
    raw_items = [{"sku": "TEST-OOS-01", "qty": 1}]
    sanitized, total_paise, errors = recompute_and_sanitize_cart(raw_items)
    assert len(errors) > 0
    assert "insufficient stock" in errors[0].lower()


def test_irreversible_3_tier_outcomes():
    """
    Tests the 3 distinct irreversible decision states:
      1. Auto-Approved (<= ₹1,500)
      2. Held for Review / Pending Confirmation (₹1,500 < Total <= ₹5,000)
      3. Hard-Blocked (> ₹5,000)
    """
    # Tier 1: ₹1,000 digital gift card -> Auto-Approved
    res_tier1 = validate_cart(None, [{"sku": "TEST-IRREV-01", "qty": 1}])
    assert res_tier1["status"] == "approved"
    assert res_tier1["reversible"] is False

    # Tier 2: 3x digital gift card = ₹3,000 (> ₹1,500 auto ceiling but <= ₹5,000) -> Pending Confirmation
    res_tier2 = validate_cart(None, [{"sku": "TEST-IRREV-01", "qty": 3}])
    assert res_tier2["status"] == "pending_confirmation"
    assert res_tier2["reversible"] is False
    assert "strict autonomy threshold" in res_tier2["reason"]

    # Tier 3: Custom clearance item = ₹6,000 (> ₹5,000 hard block ceiling) -> Hard Blocked
    res_tier3 = validate_cart(None, [{"sku": "TEST-IRREV-EXPENSIVE", "qty": 1}])
    assert res_tier3["status"] == "blocked"
    assert res_tier3["reversible"] is False
    assert "exceeds maximum permitted irreversible ceiling" in res_tier3["reason"]


def test_reversible_standard_autonomy_threshold():
    # 2x shirt = ₹2,000 (below ₹5,000 standard autonomy threshold) -> Auto-Approved
    res_approved = validate_cart(None, [{"sku": "TEST-REV-01", "qty": 2}])
    assert res_approved["status"] == "approved"
    assert res_approved["reversible"] is True

    # 6x shirt = ₹6,000 (above ₹5,000 standard autonomy threshold) -> Pending Confirmation
    res_pending = validate_cart(None, [{"sku": "TEST-REV-01", "qty": 6}])
    assert res_pending["status"] == "pending_confirmation"
    assert res_pending["reversible"] is True
