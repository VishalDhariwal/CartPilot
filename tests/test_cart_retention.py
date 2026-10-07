"""
Tests for Multi-Turn Shopping Cart Retention and Cumulative Ordering

Verifies:
1. Multi-turn additive purchases: adding shoes after a shirt preserves both items and accumulates total.
2. Duplicate product addition: increments quantity instead of creating duplicate line items.
3. Conversational and informational turns: greetings, how-tos, recipes do not wipe out active cart.
4. Itemized cart view: 'what is in my cart' reports all active items and total.
5. Selective item removal: 'remove silk shirt' drops the specified item from current cart.
6. Explicit cart clearing: 'clear cart' resets the cart to empty.
"""

import os
import pytest
from backend.db import get_db, init_db
from backend.agents.buyer_graph import run_buyer_journey

TEST_DB_PATH = "/tmp/test_cart_retention.db"


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
        INSERT INTO policy_config (id, spend_cap_paise, allowed_categories, autonomy_threshold_paise)
        VALUES (1, 1000000, '["clothing", "electronics", "beauty", "home", "books", "sports", "accessories", "groceries", "mens-shirts", "shoes", "womens-shoes"]', 500000)
        ON CONFLICT(id) DO UPDATE SET
            spend_cap_paise=excluded.spend_cap_paise,
            allowed_categories=excluded.allowed_categories
    """)

    test_items = [
        ("SKU_SHIRT_1", "Handcrafted Silk Shirt", 349900, 10, "mens-shirts", "FashionStore", 0, "", "Silk shirt", "{}"),
        ("SKU_SHIRT_2", "Man Plaid Shirt", 3499, 20, "mens-shirts", "FashionStore", 0, "", "Plaid shirt", "{}"),
        ("SKU_SHOES_1", "Pampi Shoes", 2999, 15, "shoes", "FootwearHub", 0, "", "Classic shoes", "{}"),
        ("SKU_WATCH_1", "Chronograph Wrist Watch", 899900, 5, "accessories", "TimePiece", 0, "", "Luxury watch", "{}")
    ]

    for item in test_items:
        cursor.execute("""
            INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted, image_url, description, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                price_paise=excluded.price_paise,
                stock=excluded.stock,
                category=excluded.category
        """, item)

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


def test_additive_multi_turn_cart_retention():
    """Turn 1 adds a shirt; Turn 2 adds shoes. Both must be present in the returned cart."""
    # Turn 1: Buy a shirt
    res1 = run_buyer_journey(
        query="buy me a shirt",
        spend_cap_paise=1000000,
        current_cart=[]
    )
    assert res1["guardrail_status"] == "approved"
    assert len(res1["proposed_items"]) == 1
    shirt_item = res1["proposed_items"][0]
    assert "shirt" in shirt_item["name"].lower()

    # User manually adds Man Plaid Shirt as well
    current_cart = [
        shirt_item,
        {"sku": "SKU_SHIRT_2", "name": "Man Plaid Shirt", "price_paise": 3499, "qty": 1, "category": "mens-shirts"}
    ]

    # Turn 2: User says "also buy shoes for me"
    res2 = run_buyer_journey(
        query="also buy shoes for me",
        spend_cap_paise=1000000,
        current_cart=current_cart
    )
    assert res2["guardrail_status"] == "approved"
    proposed_skus = [it["sku"] for it in res2["proposed_items"]]

    # Both previous items must be retained!
    assert shirt_item["sku"] in proposed_skus
    assert "SKU_SHIRT_2" in proposed_skus
    # New shoes must be added!
    assert any("shoe" in it["name"].lower() for it in res2["proposed_items"])
    assert len(res2["proposed_items"]) == 3

    # Total must be the sum of all 3 items
    expected_total = shirt_item["price_paise"] + 3499 + res2["proposed_items"][2]["price_paise"]
    assert res2["cart_total_paise"] == expected_total

    # Assistant message should acknowledge the newly added item and report 3 total items
    assert "3 items" in res2["assistant_message"] or "added" in res2["assistant_message"].lower()


def test_duplicate_item_increments_quantity():
    """Requesting an item already in cart increments quantity rather than adding duplicate line."""
    initial_cart = [
        {"sku": "SKU_SHOES_1", "name": "Pampi Shoes", "price_paise": 2999, "qty": 1, "category": "shoes"}
    ]
    res = run_buyer_journey(
        query="buy Pampi Shoes",
        spend_cap_paise=1000000,
        current_cart=initial_cart
    )
    assert res["guardrail_status"] == "approved"
    assert len(res["proposed_items"]) == 1
    assert res["proposed_items"][0]["sku"] == "SKU_SHOES_1"
    assert res["proposed_items"][0]["qty"] == 2
    assert res["cart_total_paise"] == 2999 * 2


def test_conversational_and_informational_queries_preserve_cart():
    """Informational, greeting, and help questions must not wipe out the cart."""
    active_cart = [
        {"sku": "SKU_SHIRT_1", "name": "Handcrafted Silk Shirt", "price_paise": 349900, "qty": 1, "category": "mens-shirts"},
        {"sku": "SKU_SHOES_1", "name": "Pampi Shoes", "price_paise": 2999, "qty": 1, "category": "shoes"}
    ]
    expected_total = 349900 + 2999

    # 1. Recipe / how-to question
    res_info = run_buyer_journey(
        query="how to cook eggs",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res_info["proposed_items"]) == 2
    assert res_info["cart_total_paise"] == expected_total
    assert "egg" in res_info["assistant_message"].lower()

    # 2. Greeting
    res_greet = run_buyer_journey(
        query="hello",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res_greet["proposed_items"]) == 2
    assert res_greet["cart_total_paise"] == expected_total

    # 3. Help / identity
    res_help = run_buyer_journey(
        query="who are you",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res_help["proposed_items"]) == 2
    assert res_help["cart_total_paise"] == expected_total


def test_cart_view_summarizes_active_items():
    """'what is in my cart' provides itemized list of all items and accurate total."""
    active_cart = [
        {"sku": "SKU_SHIRT_1", "name": "Handcrafted Silk Shirt", "price_paise": 349900, "qty": 1, "category": "mens-shirts"},
        {"sku": "SKU_SHOES_1", "name": "Pampi Shoes", "price_paise": 2999, "qty": 1, "category": "shoes"}
    ]
    res = run_buyer_journey(
        query="what is in my cart",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res["proposed_items"]) == 2
    assert "Handcrafted Silk Shirt" in res["assistant_message"]
    assert "Pampi Shoes" in res["assistant_message"]
    assert "3528.99" in res["assistant_message"]


def test_item_removal_drops_target_product():
    """'remove silk shirt' removes the matched item and updates cart total."""
    active_cart = [
        {"sku": "SKU_SHIRT_1", "name": "Handcrafted Silk Shirt", "price_paise": 349900, "qty": 1, "category": "mens-shirts"},
        {"sku": "SKU_SHOES_1", "name": "Pampi Shoes", "price_paise": 2999, "qty": 1, "category": "shoes"}
    ]
    res = run_buyer_journey(
        query="remove silk shirt",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res["proposed_items"]) == 1
    assert res["proposed_items"][0]["sku"] == "SKU_SHOES_1"
    assert res["cart_total_paise"] == 2999
    assert "removed" in res["assistant_message"].lower()


def test_cart_clear_resets_to_empty():
    """'clear cart' returns empty proposed_items and zero total."""
    active_cart = [
        {"sku": "SKU_SHIRT_1", "name": "Handcrafted Silk Shirt", "price_paise": 349900, "qty": 1, "category": "mens-shirts"},
        {"sku": "SKU_SHOES_1", "name": "Pampi Shoes", "price_paise": 2999, "qty": 1, "category": "shoes"}
    ]
    res = run_buyer_journey(
        query="clear cart",
        spend_cap_paise=1000000,
        current_cart=active_cart
    )
    assert len(res["proposed_items"]) == 0
    assert res["cart_total_paise"] == 0
    assert "cleared" in res["assistant_message"].lower()
