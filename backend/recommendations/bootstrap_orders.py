import json
import random
import sqlite3
from datetime import datetime, timedelta
from backend.db import get_db

def generate_synthetic_orders(num_orders: int = 350):
    """
    Generates realistic synthetic shopping baskets across the catalog items
    and seeds the historical_orders table with is_synthetic = 1.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Query SKUs grouped by category and sub-keywords
    cursor.execute("SELECT sku, name, category, price_paise FROM catalog WHERE stock > 0")
    all_items = [dict(row) for row in cursor.fetchall()]

    if not all_items:
        print("No items found in catalog to generate synthetic orders.")
        conn.close()
        return

    # Index items by category and name keywords
    cat_items = {}
    keyword_items = {}
    for item in all_items:
        cat = item["category"]
        cat_items.setdefault(cat, []).append(item["sku"])
        
        name_lower = item["name"].lower()
        for kw in ["bread", "butter", "milk", "eggs", "cheese", "banana", "wheat", "rice",
                   "pan", "spatula", "kettle", "toaster", "blender", "pot", "oven", "microwave",
                   "tablet", "laptop", "keyboard", "mouse", "monitor", "charger", "smartwatch", "headphones",
                   "jacket", "t-shirt", "jeans", "belt", "sunglasses", "shoes", "socks", "gloves", "hat", "scarf"]:
            if kw in name_lower:
                keyword_items.setdefault(kw, []).append(item["sku"])

    # High affinity cluster templates (correlations that naturally occur in retail)
    affinity_clusters = [
        # Breakfast & pantry staples
        ["bread", "butter", "eggs"],
        ["bread", "butter", "cheese"],
        ["bread", "milk", "eggs"],
        ["banana", "milk", "blender"],
        ["wheat", "butter", "pan"],
        ["rice", "butter", "pot"],
        ["cheese", "eggs", "pan"],

        # Tech setup & peripherals
        ["tablet", "keyboard", "mouse"],
        ["laptop", "keyboard", "mouse"],
        ["monitor", "keyboard", "mouse"],
        ["tablet", "charger", "headphones"],
        ["smartwatch", "headphones", "charger"],
        ["monitor", "charger", "laptop"],

        # Kitchen cookware & appliances
        ["pan", "spatula", "pot"],
        ["kettle", "toaster", "bread"],
        ["blender", "kettle", "toaster"],
        ["oven", "pan", "pot"],
        ["spatula", "pan", "butter"],

        # Fashion outfits & accessories
        ["jacket", "belt", "sunglasses"],
        ["t-shirt", "jeans", "belt"],
        ["jacket", "gloves", "scarf"],
        ["shoes", "socks", "jeans"],
        ["hat", "sunglasses", "t-shirt"],
        ["jacket", "t-shirt", "sunglasses"],
        ["jeans", "shoes", "belt"],

        # Cross-category lifestyles (e.g. gym, morning routine, home office)
        ["smartwatch", "gloves", "headphones"],
        ["tablet", "headphones", "kettle"],
        ["laptop", "headphones", "charger"],
    ]

    orders_to_insert = []
    base_time = datetime.utcnow() - timedelta(days=60)

    for i in range(num_orders):
        order_id = f"syn_ord_{i+1:04d}"
        created_at = (base_time + timedelta(hours=i * 4 + random.randint(0, 180))).isoformat() + "Z"

        # 75% affinity cluster based, 25% category co-browse
        if random.random() < 0.75:
            cluster = random.choice(affinity_clusters)
            basket_skus = []
            for kw in cluster:
                pool = keyword_items.get(kw, [])
                if pool:
                    basket_skus.append(random.choice(pool))
            
            # Occasionally add 1 related item from the same category
            if basket_skus and random.random() < 0.4:
                sample_item = next((it for it in all_items if it["sku"] == basket_skus[0]), None)
                if sample_item:
                    cat_pool = cat_items.get(sample_item["category"], [])
                    if cat_pool:
                        extra_sku = random.choice(cat_pool)
                        if extra_sku not in basket_skus:
                            basket_skus.append(extra_sku)
        else:
            # Random category shopping basket (2 to 4 items in same or adjacent category)
            cat = random.choice(list(cat_items.keys()))
            pool = cat_items[cat]
            k = min(len(pool), random.randint(2, 4))
            basket_skus = random.sample(pool, k)

        # Deduplicate and ensure at least 2 items per order
        basket_skus = list(dict.fromkeys(basket_skus))
        if len(basket_skus) < 2:
            # Pad with an item from same category
            cat_pool = cat_items.get("grocery", all_items)
            extra = random.choice(cat_pool)
            if isinstance(extra, dict):
                extra = extra["sku"]
            if extra not in basket_skus:
                basket_skus.append(extra)

        orders_to_insert.append((
            order_id,
            json.dumps(basket_skus),
            1,  # is_synthetic = 1
            created_at
        ))

    cursor.executemany(
        """INSERT OR REPLACE INTO historical_orders (order_id, items, is_synthetic, created_at)
           VALUES (?, ?, ?, ?)""",
        orders_to_insert
    )
    conn.commit()
    print(f"✅ Successfully seeded {len(orders_to_insert)} synthetic historical orders.")
    conn.close()

if __name__ == "__main__":
    generate_synthetic_orders(350)
