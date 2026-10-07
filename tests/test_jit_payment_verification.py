import pytest
from backend.db import get_db, init_db
from backend.engine.mandates import create_intent_mandate, create_cart_mandate
from backend.engine.payment_engine import execute_payment_mandate, JITInventoryError


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO catalog (sku, name, price_paise, stock, category, merchant)
        VALUES ('TEST-JIT-SKU', 'JIT Stock Item', 100000, 5, 'electronics', 'TestMerchant')
    """)
    cursor.execute("""
        UPDATE policy_config 
        SET spend_cap_paise = 1000000, 
            autonomy_threshold_paise = 500000,
            allowed_categories = '["electronics"]'
        WHERE id = 1
    """)
    conn.commit()
    conn.close()


def test_jit_inventory_drop_blocks_payment_execution():
    """
    Simulates inventory selling out between cart mandate approval and payment click.
    The PaymentEngine MUST catch this at JIT re-validation time and abort.
    """
    intent = create_intent_mandate("JIT test", "buy item", 200000)
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=[{"sku": "TEST-JIT-SKU", "name": "JIT Stock Item", "qty": 3, "price_paise": 100000}],
        total_paise=300000,
        status="approved",
        reason="Approved when stock was 5",
        reversible=True
    )

    # Simulate stock dropping to 1 before payment execution (requested 3)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET stock = 1 WHERE sku = 'TEST-JIT-SKU'")
    conn.commit()
    conn.close()

    with pytest.raises(JITInventoryError) as exc_info:
        execute_payment_mandate(cart["id"])

    assert "Insufficient stock" in str(exc_info.value)


def test_jit_price_change_blocks_payment_execution():
    """
    Simulates a merchant price change occurring while the cart mandate was pending.
    PaymentEngine MUST detect the price discrepancy and abort.
    """
    intent = create_intent_mandate("Price shift test", "buy item", 200000)
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=[{"sku": "TEST-JIT-SKU", "name": "JIT Stock Item", "qty": 1, "price_paise": 100000}],
        total_paise=100000,
        status="approved",
        reason="Approved at ₹1000",
        reversible=True
    )

    # Merchant raises price to ₹1,500
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET price_paise = 150000 WHERE sku = 'TEST-JIT-SKU'")
    conn.commit()
    conn.close()

    with pytest.raises(JITInventoryError) as exc_info:
        execute_payment_mandate(cart["id"])

    assert "Price changed" in str(exc_info.value)
