import json
from collections import defaultdict
from datetime import datetime
from backend.db import get_db

def compute_lift_pairs(min_support_count: int = 2, min_lift: float = 1.0) -> int:
    """
    Computes market basket association rules (Support, Confidence, Lift)
    across all orders in historical_orders and saves pairs with lift >= min_lift
    to the basket_pairs table.

    Returns the number of association rules generated.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT items FROM historical_orders")
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return 0

    total_orders = len(rows)
    item_counts = defaultdict(int)
    pair_counts = defaultdict(int)

    for row in rows:
        try:
            items = json.loads(row["items"]) if isinstance(row["items"], str) else row["items"]
            # Deduplicate items in the basket
            unique_items = sorted(list(set(items)))

            for item in unique_items:
                item_counts[item] += 1

            for i in range(len(unique_items)):
                for j in range(len(unique_items)):
                    if i != j:
                        pair_counts[(unique_items[i], unique_items[j])] += 1
        except Exception as e:
            continue

    now = datetime.utcnow().isoformat() + "Z"
    pairs_to_insert = []

    for (sku_a, sku_b), pair_freq in pair_counts.items():
        if pair_freq < min_support_count:
            continue

        support_a = item_counts[sku_a] / total_orders
        support_b = item_counts[sku_b] / total_orders
        support_ab = pair_freq / total_orders

        if support_a == 0 or support_b == 0:
            continue

        confidence = support_ab / support_a
        lift = confidence / support_b

        if lift >= min_lift:
            pairs_to_insert.append((
                sku_a,
                sku_b,
                round(lift, 4),
                round(support_ab, 4),
                now
            ))

    # Clear and replace basket_pairs
    cursor.execute("DELETE FROM basket_pairs")
    cursor.executemany(
        """INSERT OR REPLACE INTO basket_pairs (sku_a, sku_b, lift, support, computed_at)
           VALUES (?, ?, ?, ?, ?)""",
        pairs_to_insert
    )
    conn.commit()
    conn.close()

    print(f"📊 Market Basket Analysis computed {len(pairs_to_insert)} high-lift association rules from {total_orders} orders.")
    return len(pairs_to_insert)


def find_cross_sell(cart_items: list, top_k: int = 3) -> list[dict]:
    """
    Given items currently in a cart, finds the top ranked cross-sell candidates
    using computed market basket lift metrics with catalog boost weighting.

    Returns a list of ranked dicts:
      [
        {
          "sku": "...",
          "name": "...",
          "price_paise": 1234,
          "category": "...",
          "lift": 3.42,
          "support": 0.08,
          "final_score": 3.93,
          "trigger_sku": "...",
          "trigger_name": "...",
          "reason": "..."
        },
        ...
      ]
    """
    if not cart_items:
        return []

    conn = get_db()
    cursor = conn.cursor()

    cart_skus = [item["sku"] for item in cart_items if "sku" in item]
    if not cart_skus:
        conn.close()
        return []

    # Map cart SKUs to names for explainability
    cursor.execute(
        f"SELECT sku, name FROM catalog WHERE sku IN ({','.join(['?'] * len(cart_skus))})",
        cart_skus
    )
    cart_sku_names = {row["sku"]: row["name"] for row in cursor.fetchall()}

    # Query basket_pairs for all SKUs in the cart
    placeholders = ','.join(['?'] * len(cart_skus))
    sql = f"""
    SELECT 
        bp.sku_a,
        bp.sku_b,
        bp.lift,
        bp.support,
        c.name AS candidate_name,
        c.price_paise AS candidate_price,
        c.category AS candidate_category,
        c.stock AS candidate_stock,
        c.boosted AS candidate_boosted,
        c.image_url AS candidate_image_url,
        c.description AS candidate_description,
        c.metadata AS candidate_metadata
    FROM basket_pairs bp
    JOIN catalog c ON c.sku = bp.sku_b
    WHERE bp.sku_a IN ({placeholders})
      AND c.stock > 0
      AND bp.sku_b NOT IN ({placeholders})
      AND (bp.muted IS NULL OR bp.muted = 0)
    ORDER BY bp.lift DESC
    """

    cursor.execute(sql, cart_skus + cart_skus)
    rows = cursor.fetchall()

    candidates_by_sku = {}

    for row in rows:
        sku_b = row["sku_b"]
        lift = row["lift"]
        boosted = row["candidate_boosted"] or 0
        boost_multiplier = 1.35 if boosted else 1.0
        final_score = round(lift * boost_multiplier, 4)

        trigger_sku = row["sku_a"]
        trigger_name = cart_sku_names.get(trigger_sku, trigger_sku)

        # Build an explainable reason grounded in the co-occurrence data
        reason = f"Frequently bought together with {trigger_name} (affinity {lift:.1f}x higher than average)."
        if boosted:

            reason += " Featured partner recommendation."

        meta_obj = {}
        if row["candidate_metadata"]:
            try:
                meta_obj = json.loads(row["candidate_metadata"])
            except Exception:
                meta_obj = {}

        candidate = {
            "sku": sku_b,
            "name": row["candidate_name"],
            "price_paise": row["candidate_price"],
            "category": row["candidate_category"],
            "image_url": row["candidate_image_url"] or "",
            "description": row["candidate_description"] or "",
            "metadata": meta_obj,
            "lift": lift,
            "support": row["support"],
            "final_score": final_score,
            "boosted": bool(boosted),
            "trigger_sku": trigger_sku,
            "trigger_name": trigger_name,
            "reason": reason
        }

        # Deduplicate candidates across multi-item carts, keeping highest final_score
        if sku_b not in candidates_by_sku or final_score > candidates_by_sku[sku_b]["final_score"]:
            candidates_by_sku[sku_b] = candidate

    # Sort by final_score descending
    sorted_candidates = sorted(candidates_by_sku.values(), key=lambda x: x["final_score"], reverse=True)

    # Fallback: if no basket pairs exist (e.g. rare combo), provide in-stock category complements
    if not sorted_candidates:
        cart_categories = list({item.get("category") for item in cart_items if item.get("category")})
        cat_filter = f"category IN ({','.join(['?']*len(cart_categories))})" if cart_categories else "1=1"
        
        cursor.execute(
            f"""SELECT sku, name, price_paise, category, boosted, image_url, description, metadata 
               FROM catalog 
               WHERE stock > 0 
                 AND sku NOT IN ({placeholders}) 
                 AND ({cat_filter})
               ORDER BY boosted DESC, price_paise ASC 
               LIMIT ?""",
            cart_skus + (cart_categories if cart_categories else []) + [top_k]
        )
        for row in cursor.fetchall():
            meta_obj = {}
            if row["metadata"]:
                try:
                    meta_obj = json.loads(row["metadata"])
                except Exception:
                    meta_obj = {}
            sorted_candidates.append({
                "sku": row["sku"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "category": row["category"],
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "metadata": meta_obj,
                "lift": 1.2,
                "support": 0.05,
                "final_score": 1.38 if row["boosted"] else 1.2,
                "boosted": bool(row["boosted"]),
                "trigger_sku": cart_skus[0] if cart_skus else "",
                "trigger_name": "your cart",
                "reason": f"Popular complementary {row['category']} item for your order."
            })


    conn.close()
    return sorted_candidates[:top_k]

