import json
import sqlite3
from backend.db import get_db, init_db
from backend.recommendations.embedding_engine import find_substitutes, precompute_catalog_embeddings
from backend.recommendations.lift_engine import compute_lift_pairs, find_cross_sell
from backend.agents.substitution_agent import find_substitute
from backend.agents.growth_agent import generate_upsell
from backend.engine.mandates import update_payment_mandate_status, create_intent_mandate, create_cart_mandate, create_payment_mandate

def run_tests():
    print("==================================================")
    print("CARTPILOT RECOMMENDATION ENGINE E2E VERIFICATION")
    print("==================================================")

    # 1. Verify Catalog Embeddings
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(embedding) FROM catalog")
    tot_items, tot_emb = cursor.fetchone()
    print(f"\n1. CATALOG EMBEDDINGS:")
    print(f"   Total items: {tot_items} | With Embeddings: {tot_emb}")
    assert tot_items == tot_emb, "All catalog items must have embeddings"

    # 2. Test Substitution Engine (Embedding Similarity)
    print(f"\n2. SEMANTIC SUBSTITUTION ENGINE TEST:")
    subs = find_substitutes("Vintage Leather Jacket", top_k=3)
    print(f"   Query: 'Vintage Leather Jacket'")
    for i, s in enumerate(subs, 1):
        print(f"   Candidate {i}: {s['name']} ({s['sku']}) | Category: {s['category']} | Sim: {s['similarity_score']:.3f} | Score: {s['final_score']:.3f} | Price: ₹{s['price_paise']/100:.0f}")
    assert len(subs) > 0, "Should return ranked candidates"
    assert all(s["category"] == "fashion" for s in subs), "Should return fashion items for a jacket query"

    # Test Substitution Agent with LLM selection
    sub_agent_res = find_substitute({"name": "Almond Butter Creamy", "sku": "MISSING-SKU-999"}, budget_remaining_paise=50000)
    print(f"\n   Substitution Agent LLM selection for missing item 'Almond Butter Creamy':")
    if sub_agent_res:
        print(f"   Chosen SKU: {sub_agent_res['sku']} ({sub_agent_res['name']})")
        print(f"   Reason: {sub_agent_res['reason']}")
        print(f"   Similarity: {sub_agent_res.get('similarity_score', 0):.3f}")

    # 3. Test Market Basket Lift Engine
    print(f"\n3. MARKET BASKET LIFT ANALYSIS TEST:")
    cursor.execute("SELECT COUNT(*), SUM(is_synthetic), SUM(1 - is_synthetic) FROM historical_orders")
    tot_ord, syn_ord, real_ord = cursor.fetchone()
    print(f"   Historical Orders: {tot_ord} (Synthetic: {syn_ord}, Real: {real_ord or 0})")
    
    cursor.execute("SELECT COUNT(*), AVG(lift), MAX(lift) FROM basket_pairs")
    tot_pairs, avg_lift, max_lift = cursor.fetchone()
    print(f"   Computed Basket Pairs: {tot_pairs} | Avg Lift: {avg_lift:.2f}x | Max Lift: {max_lift:.2f}x")
    assert tot_pairs > 0, "Should have computed association pairs"

    # Test Cross-Sell Engine
    print(f"\n4. CROSS-SELL RECOMMENDATION TEST:")
    cart_items = [
        {"sku": "BOO-GRO-0359", "name": "Bread Essential 123", "price_paise": 4500, "qty": 1, "category": "grocery"}
    ]
    upsell_res = generate_upsell(cart_items)
    print(f"   Cart: Bread Essential")
    if upsell_res:
        print(f"   Recommended: {upsell_res['name']} ({upsell_res['sku']}) | ₹{upsell_res['price_paise']/100:.0f}")
        print(f"   Lift: {upsell_res.get('lift', 1.0):.2f}x affinity")
        print(f"   Reason: {upsell_res['reason']}")

    # 5. Test Real Order Lifecycle & Dynamic Self-Updating
    print(f"\n5. DYNAMIC SELF-UPDATING PIPELINE TEST:")
    intent = create_intent_mandate("i want milk and bread", "grocery purchase", 500000)
    cart = create_cart_mandate(
        intent_id=intent["id"],
        items=[
            {"sku": "BOO-GRO-0359", "name": "Bread Essential", "price_paise": 4500, "qty": 1, "category": "grocery"},
            {"sku": "SNE-GRO-0290", "name": "Milk Plus 473", "price_paise": 9000, "qty": 1, "category": "grocery"}
        ],
        total_paise=13500,
        status="approved",
        reason="Within spend cap",
        reversible=True
    )
    payment = create_payment_mandate(
        cart_id=cart["id"],
        amount_paise=13500,
        razorpay_order_id="order_test_real_999"
    )
    
    # Simulate payment success
    update_payment_mandate_status(
        razorpay_order_id="order_test_real_999",
        cart_id=cart["id"],
        status="succeeded",
        payment_id="pay_test_real_999"
    )

    # Verify real order was added to historical_orders with is_synthetic = 0
    cursor.execute("SELECT order_id, items, is_synthetic FROM historical_orders WHERE is_synthetic = 0")
    real_rows = cursor.fetchall()
    print(f"   Real Orders in historical_orders: {len(real_rows)}")
    for r in real_rows:
        print(f"   -> ID: {r['order_id']} | Items: {r['items']} | is_synthetic: {r['is_synthetic']}")
    assert len(real_rows) >= 1, "Real completed order must be recorded in historical_orders"

    conn.close()
    print("\n==================================================")
    print("✅ ALL RECOMMENDATION ENGINE E2E TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
