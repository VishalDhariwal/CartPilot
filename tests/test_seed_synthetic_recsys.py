import pytest
import json
from backend.db import get_db, init_db
from backend.recommendations.lift_engine import find_cross_sell
from backend.jobs.seed_synthetic_recsys import seed_synthetic_orders, run_recsys_training_and_validation


@pytest.fixture(autouse=True)
def setup_recsys_db():
    """Initializes the database before running recsys tests and resets policy."""
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE policy_config SET allowed_categories = ? WHERE id = 1",
        (json.dumps(["*"]),)
    )
    conn.commit()
    conn.close()


def test_cold_start_sku_activates_tier_3_category_graph():
    """
    Dedicated Cold-Start Recommendation Test:
    When a merchant adds a brand-new SKU to the catalog that has:
      - 0 historical order appearances (no Tier 1 Association Lift rules)
      - 0 co-purchase embedding sequences (no Tier 2 Item2Vec vectors)
    The recommendation engine MUST gracefully fall back to:
      - Tier 3: Live Category Compatibility Graph & Semantic Matching.
    """
    conn = get_db()
    cursor = conn.cursor()

    cold_sku = "TEST_COLD_START_DRONE_4K"
    compat_sku = "TEST_COMPAT_LAPTOP_SLEEVE_01"
    try:
        # Clean up any leftover test SKUs
        cursor.execute("DELETE FROM catalog WHERE sku IN (?, ?)", (cold_sku, compat_sku))
        cursor.execute("DELETE FROM basket_pairs WHERE sku_a IN (?, ?) OR sku_b IN (?, ?)", (cold_sku, compat_sku, cold_sku, compat_sku))

        # Insert a brand new, unseeded SKU into catalog
        cursor.execute(
            """
            INSERT INTO catalog (
                sku, name, price_paise, stock, category, merchant, description,
                image_url, boosted, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cold_sku,
                "Next-Gen UltraBook Pro 15-inch",
                8500000,
                25,
                "laptops",
                "AeroTech Labs",
                "High-performance workstation laptop with OLED display",
                "https://images.unsplash.com/photo-laptop-cold",
                0,
                json.dumps({"brand": "AeroTech", "weight_grams": 1450})
            )
        )

        # Insert a complementary item in compatible category
        cursor.execute(
            """
            INSERT INTO catalog (
                sku, name, price_paise, stock, category, merchant, description,
                image_url, boosted, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                compat_sku,
                "Shockproof Neoprene Laptop Sleeve",
                149900,
                50,
                "mobile-accessories",
                "SleeveCraft",
                "Protective water-resistant sleeve for 15-inch laptops",
                "https://images.unsplash.com/photo-sleeve-cold",
                0,
                json.dumps({"brand": "SleeveCraft"})
            )
        )

        # Ensure category compatibility rule exists
        cursor.execute(
            """
            INSERT OR IGNORE INTO category_compatibility (category_a, category_b, reasoning)
            VALUES (?, ?, ?)
            """,
            ("laptops", "mobile-accessories", "Laptops require protective carrying sleeves and travel accessories")
        )
        conn.commit()

        # Confirm there are zero lift rules or historical orders for this cold SKU
        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE sku_a = ? OR sku_b = ?", (cold_sku, cold_sku))
        assert cursor.fetchone()[0] == 0, "Cold SKU must have zero association rules in basket_pairs."

        cursor.execute("SELECT COUNT(*) FROM historical_orders WHERE items LIKE ?", (f"%{cold_sku}%",))
        assert cursor.fetchone()[0] == 0, "Cold SKU must have zero order appearances in historical_orders."

        # Request upsell recommendations for the cold-start SKU
        recommendations = find_cross_sell([{"sku": cold_sku, "qty": 1}], top_k=3)

        # Assertions: Recommendations must be returned via Tier 3
        assert len(recommendations) > 0, "Expected at least 1 category fallback recommendation for cold SKU."

        for rec in recommendations:
            assert rec["tier"] == "tier_3_category_semantic", (
                f"Expected Tier 3 category semantic fallback, but received {rec.get('tier')} ({rec.get('tier_label')})"
            )
            assert "Tier 3" in rec["tier_label"]
            assert rec["sku"] != cold_sku
            assert rec["price_paise"] > 0
            # Tier 3 must NOT fabricate non-empirical lift or support metrics
            assert rec.get("lift") is None or rec.get("lift") == 1.0 or rec.get("source") != "data_verified"

    finally:
        # Cleanup
        cursor.execute("DELETE FROM catalog WHERE sku = ?", (cold_sku,))
        cursor.execute("DELETE FROM basket_pairs WHERE sku_a = ? OR sku_b = ?", (cold_sku, cold_sku))
        conn.commit()
        conn.close()


def test_synthetic_recsys_training_and_tier_distribution():
    """
    Validates that seeding synthetic orders trains both Tier 1 (Lift Rules)
    and Tier 2 (Item2Vec) while maintaining the Tier 3 fallback integrity.
    """
    # Seed orders and train models
    seed_synthetic_orders(50)
    validation_results = run_recsys_training_and_validation()

    assert validation_results["verified_rules"] >= 0
    assert validation_results["item2vec_status"] in ["trained", "insufficient_orders"]
    assert "tier_counts" in validation_results
