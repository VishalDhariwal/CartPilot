import os
import uuid
import pytest
import time
from datetime import datetime, timedelta
from backend.db import get_db, init_db
from backend.engine.mandates import create_intent_mandate, create_cart_mandate
from backend.engine.payment_engine import (
    execute_payment_mandate,
    CartAlreadyConsumedError,
    CartMandateExpiredError,
    CartMandateNotApprovedError
)

TEST_DB_PATH = "/tmp/test_mandate_lifecycle.db"


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
    cursor.execute("""
        INSERT OR REPLACE INTO catalog (sku, name, price_paise, stock, category, merchant)
        VALUES ('TEST-SKU-01', 'Test Product', 50000, 100, 'electronics', 'TestMerchant')
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


def test_cart_mandate_ttl_and_atomic_consumption():
    # 1. Create intent and approved cart mandate
    intent = create_intent_mandate("test purchase", "buy test product", 100000)
    items = [{"sku": "TEST-SKU-01", "name": "Test Product", "qty": 1, "price_paise": 50000}]
    
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=items,
        total_paise=50000,
        status="approved",
        reason="Within spend cap",
        reversible=True,
        ttl_minutes=15
    )

    assert cart["expires_at"] is not None
    t_exp = datetime.fromisoformat(cart["expires_at"].replace("Z", "+00:00"))
    t_now = datetime.now(t_exp.tzinfo)
    # Expiration is in ~15 mins
    assert (t_exp - t_now).total_seconds() > 800

    # 2. First payment execution should succeed
    pay_res = execute_payment_mandate(cart["id"])
    assert pay_res["success"] is True
    assert pay_res["payment_mandate_id"] is not None

    # Verify consumed_at was set in database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT consumed_at, consumed_by_payment_id FROM cart_mandates WHERE id = ?", (cart["id"],))
    c_row = cursor.fetchone()
    conn.close()
    assert c_row["consumed_at"] is not None
    assert c_row["consumed_by_payment_id"] == pay_res["payment_mandate_id"]

    # 3. Second payment execution on the SAME cart MUST fail with CartAlreadyConsumedError (No Double Spend)
    with pytest.raises(CartAlreadyConsumedError):
        execute_payment_mandate(cart["id"])


def test_expired_cart_mandate_is_rejected():
    intent = create_intent_mandate("expired test", "buy expired", 100000)
    items = [{"sku": "TEST-SKU-01", "name": "Test Product", "qty": 1, "price_paise": 50000}]
    
    # Create mandate already expired 5 minutes ago
    conn = get_db()
    cursor = conn.cursor()
    cart_id = f"cart_expired_{uuid.uuid4().hex[:8]}"
    now_dt = datetime.utcnow()
    created_at = (now_dt - timedelta(minutes=20)).isoformat() + "Z"
    expires_at = (now_dt - timedelta(minutes=5)).isoformat() + "Z"
    
    cursor.execute(
        "INSERT INTO cart_mandates (id, intent_id, items, total_paise, status, reason, reversible, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cart_id, intent["id"], '[{"sku": "TEST-SKU-01", "qty": 1, "price_paise": 50000}]', 50000, "approved", "Approved earlier", 1, expires_at, created_at)
    )
    conn.commit()
    conn.close()

    # Attempt payment on expired mandate
    with pytest.raises(CartMandateExpiredError):
        execute_payment_mandate(cart_id)


def test_unapproved_cart_mandate_cannot_pay():
    intent = create_intent_mandate("blocked test", "buy blocked", 100000)
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=[{"sku": "TEST-SKU-01", "qty": 1, "price_paise": 50000}],
        total_paise=50000,
        status="blocked",
        reason="Category restricted by policy",
        reversible=True
    )

    with pytest.raises(CartMandateNotApprovedError):
        execute_payment_mandate(cart["id"])
