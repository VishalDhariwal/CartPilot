import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import init_db, get_db


@pytest.fixture(autouse=True)
def setup_test_environment():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO catalog (sku, name, price_paise, stock, category, merchant)
        VALUES 
        ('MOCK-MOTORCYCLE', 'Classic 350 Motorcycle', 20000000, 10, 'motorcycle', 'TestMerchant'),
        ('MOCK-SUNGLASSES', 'Aviator Polarized Sunglasses', 150000, 50, 'sunglasses', 'TestMerchant')
    """)
    conn.commit()
    conn.close()


def test_external_buyer_agent_api_flow():
    client = TestClient(app)

    # 1. Discover catalog
    cat_resp = client.get("/catalog")
    assert cat_resp.status_code == 200
    catalog = cat_resp.json()
    assert len(catalog) >= 2

    # 2. Submit checkout query
    checkout_payload = {
        "query": "buy aviator polarized sunglasses",
        "spend_cap_paise": 500000
    }
    agent_resp = client.post("/checkout/agent-checkout", json=checkout_payload)
    assert agent_resp.status_code == 200
    data = agent_resp.json()
    cart_id = data.get("cart_id")
    assert cart_id is not None
    assert data.get("status") in ["approved", "upsell_offered"]

    # 3. Finalize Cart and obtain Razorpay Checkout Link
    final_payload = {
        "cart_id": cart_id,
        "accept_upsell": False
    }
    final_resp = client.post("/checkout/finalize", json=final_payload)
    assert final_resp.status_code == 200
    pay_data = final_resp.json()
    assert pay_data.get("status") == "approved"
    assert pay_data.get("payment_url") is not None
    assert pay_data.get("payment_mandate_id") is not None

    # 4. Check cart status
    status_resp = client.get(f"/checkout/cart/{cart_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data.get("found") is True
