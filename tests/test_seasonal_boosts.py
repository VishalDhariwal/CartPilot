import os
import json
import pytest
from datetime import datetime
from backend.db import get_db, init_db
from backend.agents.growth_agent import apply_seasonal_boosts


TEST_DB_PATH = "/tmp/test_seasonal_boosts.db"


@pytest.fixture(autouse=True)
def setup_seasonal_test_db():
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

    # Seed test items
    test_skus = [
        ("TEST_RAIN_POUCH", "Waterproof Mobile Pouch", 49900, 40, "mobile-accessories", "GearLab", 0, 1.0, "system", ""),
        ("TEST_SUNGLASSES_01", "Polarized Aviator Sunglasses", 199900, 25, "sunglasses", "SunStyle", 0, 1.0, "system", ""),
        ("TEST_MANUAL_BOOSTED_ITEM", "Handcrafted Silk Shirt", 349900, 15, "mens-shirts", "RoyalFab", 1, 1.75, "manual", "Merchant VIP Promotion")
    ]

    for sku, name, price, stock, cat, merch, boosted, b_weight, b_source, b_reason in test_skus:
        cursor.execute(
            """
            INSERT INTO catalog (
                sku, name, price_paise, stock, category, merchant, boosted,
                boost_weight, boost_source, boost_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sku, name, price, stock, cat, merch, boosted, b_weight, b_source, b_reason)
        )

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


def test_apply_seasonal_boosts_and_manual_protection():
    """
    Verifies that:
    1. Seasonal elevations (monsoon -> mobile-accessories) and penalties (monsoon -> sunglasses)
       are written with dynamic boost weights.
    2. Items manually boosted by the merchant (boost_source='manual') are strictly protected.
    """
    simulated_context = {
        "timestamp": "2026-07-20T12:00:00Z",
        "season": "monsoon",
        "season_label": "Peak Monsoon",
        "commercial_week": 29,
        "weather": {"city": "Delhi", "condition": "rain", "temp_celsius": 27.5},
        "upcoming_festivals": [],
        "category_boosts": {
            "mobile-accessories": {
                "multiplier": 1.6,
                "reason": "Monsoon Season: Heavy rain drives waterproof accessory demand",
                "signals": ["season", "live_weather"]
            },
            "sunglasses": {
                "multiplier": 0.5,
                "reason": "Monsoon Season: Overcast weather reduces sun protection demand",
                "signals": ["season"]
            }
        }
    }

    result = apply_seasonal_boosts(context=simulated_context)
    assert result["status"] == "applied"
    assert result["manual_protected_skus"] == 1
    assert result["elevated_skus"] >= 1
    assert result["penalized_skus"] >= 1

    conn = get_db()
    cursor = conn.cursor()

    # 1. Verify in-season elevated item
    cursor.execute("SELECT boost_weight, boost_reason, boost_source, boosted FROM catalog WHERE sku = 'TEST_RAIN_POUCH'")
    rain_row = cursor.fetchone()
    assert rain_row["boost_weight"] == 1.6
    assert "Monsoon Season" in rain_row["boost_reason"]
    assert rain_row["boost_source"] == "agent"
    assert rain_row["boosted"] == 1

    # 2. Verify out-of-season penalized item
    cursor.execute("SELECT boost_weight, boost_reason, boost_source, boosted FROM catalog WHERE sku = 'TEST_SUNGLASSES_01'")
    sun_row = cursor.fetchone()
    assert sun_row["boost_weight"] == 0.5
    assert "Overcast weather" in sun_row["boost_reason"]
    assert sun_row["boost_source"] == "agent"
    assert sun_row["boosted"] == 0

    # 3. Verify manual merchant boost protection (MUST NOT BE OVERWRITTEN)
    cursor.execute("SELECT boost_weight, boost_reason, boost_source, boosted FROM catalog WHERE sku = 'TEST_MANUAL_BOOSTED_ITEM'")
    manual_row = cursor.fetchone()
    assert manual_row["boost_source"] == "manual"
    assert manual_row["boost_weight"] == 1.75
    assert manual_row["boost_reason"] == "Merchant VIP Promotion"
    assert manual_row["boosted"] == 1

    conn.close()
