import os
import json
import pytest
from backend.db import get_db, init_db
from backend.recommendations.lift_engine import find_cross_sell


TEST_DB_PATH = "/tmp/test_seasonal_recsys.db"


@pytest.fixture(autouse=True)
def setup_seasonal_recsys_db():
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

    # Ensure open policy
    cursor.execute("UPDATE policy_config SET allowed_categories = ? WHERE id = 1", (json.dumps(["*"]),))

    # Insert Category compatibility rules
    cursor.execute("""
        INSERT OR IGNORE INTO category_compatibility (category_a, category_b, reasoning, created_at)
        VALUES 
            ('smartphones', 'mobile-accessories', 'Phones require protective cases and charging gear', '2026-01-01T00:00:00Z'),
            ('smartphones', 'home-decoration', 'Smart living devices complement home ambient aesthetics', '2026-01-01T00:00:00Z')
    """)

    # Seed trigger smartphone
    cursor.execute(
        """
        INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason)
        VALUES ('TEST_PHONE_X', 'Flagship 5G Smartphone', 5999900, 20, 'smartphones', 'TechDepot', 0, 1.0, 'system', '')
        """
    )

    # Seed Candidate 1: In-season monsoon waterproof case (Elevated 1.6x)
    cursor.execute(
        """
        INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason)
        VALUES ('TEST_WATERPROOF_CASE', 'Rugged Waterproof Smartphone Case', 129900, 50, 'mobile-accessories', 'ShieldGear', 1, 1.6, 'agent', 'Monsoon: Waterproof protection elevated')
        """
    )

    # Seed Candidate 2: Neutral / Out-of-season item (Penalized 0.6x)
    cursor.execute(
        """
        INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason)
        VALUES ('TEST_OUTDOOR_FLAG', 'Summer Garden Decorative Banner', 129900, 30, 'home-decoration', 'HomeLux', 0, 0.6, 'agent', 'Monsoon: Outdoor garden decor demand reduced')
        """
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


def test_seasonal_boost_weight_elevates_cross_sell_ranking():
    """
    Verifies that the recommendation engine uses the dynamic seasonal boost_weight
    to rank in-season products significantly higher than out-of-season products.
    """
    recs = find_cross_sell([{"sku": "TEST_PHONE_X", "qty": 1}], top_k=3)
    assert len(recs) >= 2, "Expected both candidate items to be considered"

    top_rec = recs[0]
    # The in-season waterproof case must rank #1 due to its 1.6x multiplier
    assert top_rec["sku"] == "TEST_WATERPROOF_CASE"
    assert top_rec["boost_weight"] == 1.6
    assert "Seasonal merchandising" in top_rec["reason"] or "Monsoon" in top_rec["reason"]

    # Verify second candidate has lower score and shows its penalty reason
    second_rec = recs[1]
    assert second_rec["sku"] == "TEST_OUTDOOR_FLAG"
    assert second_rec["boost_weight"] == 0.6
    assert top_rec["final_score"] > second_rec["final_score"]
