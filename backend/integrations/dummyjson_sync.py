import json
import urllib.request
import random
from datetime import datetime, timedelta
from backend.db import get_db, init_db

def sync_dummyjson_catalog():
    """
    Fetches live catalog data from DummyJSON (194 items), maps all fields into SQLite catalog,
    precomputes dense sentence embeddings, and bootstraps historical basket lift pairs.
    """
    print("🌐 Fetching live catalog from https://dummyjson.com/products?limit=194 ...")
    url = "https://dummyjson.com/products?limit=194"
    req = urllib.request.Request(url, headers={"User-Agent": "CartPilot/1.0"})
    
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    products = data.get("products", [])
    if not products:
        print("❌ No products retrieved from DummyJSON.")
        return 0

    print(f"📦 Received {len(products)} products from DummyJSON.")
    init_db()

    conn = get_db()
    cursor = conn.cursor()

    # Clear old synthetic data
    cursor.execute("DELETE FROM catalog")

    items_to_insert = []
    texts_to_embed = []
    skus = []

    for p in products:
        sku = p.get("sku") or f"DJ-{p['id']:04d}"
        name = p.get("title", f"Product {p['id']}")
        price_paise = round(float(p.get("price", 10.0)) * 100)
        stock = int(p.get("stock", 25))
        category = p.get("category", "general")
        merchant = p.get("brand") or "DummyJSON Merchant"
        description = p.get("description", "")
        
        # Extract authentic product image
        images = p.get("images", [])
        image_url = images[0] if images else p.get("thumbnail", "")
        tags = p.get("tags", [])
        tags_str = json.dumps(tags)
        rating = float(p.get("rating", 4.0))
        boosted = 1 if rating >= 4.7 else 0


        # Extract sizes/variants based on category
        cat_lower = category.lower()

        if any(c in cat_lower for c in ["shirt", "top", "dress", "clothing", "apparel"]):
            sizes = ["S", "M", "L", "XL", "XXL"]
            variant_label = "Size"
        elif "shoe" in cat_lower or "footwear" in cat_lower or "sneaker" in cat_lower:
            sizes = ["UK 6", "UK 7", "UK 8", "UK 9", "UK 10", "UK 11"]
            variant_label = "Shoe Size"
        elif any(c in cat_lower for c in ["smartphone", "tablet", "laptop"]):
            sizes = ["128GB", "256GB", "512GB", "1TB"]
            variant_label = "Storage"
        elif any(c in cat_lower for c in ["fragrance", "perfume", "beauty", "skin"]):
            sizes = ["30ml", "50ml", "100ml"]
            variant_label = "Volume"
        elif "grocer" in cat_lower:
            sizes = ["250g", "500g", "1kg", "2kg"]
            variant_label = "Weight"
        else:
            sizes = ["Standard Edition", "Pro Bundle"]
            variant_label = "Variant"

        prod_metadata = {
            "brand": merchant,
            "rating": rating,
            "weight": p.get("weight"),
            "dimensions": p.get("dimensions", {}),
            "warranty": p.get("warrantyInformation", "1 Year Manufacturer Warranty"),
            "shipping": p.get("shippingInformation", "Ships in 2-4 business days"),
            "returnPolicy": p.get("returnPolicy", "30 Days Free Return"),
            "availabilityStatus": p.get("availabilityStatus", "In Stock"),
            "variantLabel": variant_label,
            "sizes": sizes,
            "images": images[:4] if images else [image_url]
        }
        metadata_str = json.dumps(prod_metadata)

        embed_text = f"{name} | {description} | category: {category} | tags: {', '.join(tags)}"
        texts_to_embed.append(embed_text)
        skus.append(sku)

        items_to_insert.append((
            sku, name, price_paise, stock, category, merchant, boosted,
            image_url, description, tags_str, metadata_str
        ))

    cursor.executemany(
        """INSERT OR REPLACE INTO catalog 
           (sku, name, price_paise, stock, category, merchant, boosted, image_url, description, tags, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        items_to_insert
    )
    conn.commit()
    print(f"✅ Saved {len(items_to_insert)} products with rich metadata into catalog table.")


    # ── Precompute sentence embeddings locally ───────────────────────────
    print("🧠 Computing 384-d dense embeddings with SentenceTransformer('all-MiniLM-L6-v2')...")
    from backend.recommendations.embedding_engine import get_model
    model = get_model()
    
    if model is not None:
        embeddings = model.encode(texts_to_embed, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        updates = [(json.dumps(emb.tolist()), sku) for emb, sku in zip(embeddings, skus)]
        cursor.executemany("UPDATE catalog SET embedding = ? WHERE sku = ?", updates)
        conn.commit()
        print(f"✅ Precomputed {len(updates)} dense embeddings.")
    else:
        print("⚠️ Model not loaded; will compute embeddings on first query.")

    # ── Verify Category Compatibility Graph for Scalable Growth Engine ───
    print("🤖 Ensuring Category Compatibility Graph is seeded...")
    from backend.recommendations.scalable_engine import generate_category_compatibility
    res = generate_category_compatibility()
    print(f"✅ Category compatibility graph ready ({res.get('inserted', 0)} pairs added).")

    # Check real empirical orders for data-verified rules
    from backend.recommendations.lift_engine import compute_lift_pairs
    verified_count = compute_lift_pairs(min_co_occurrence=8)
    print(f"✅ Market Basket Analysis verified {verified_count} empirical rules (>= 8 orders).")

    return len(items_to_insert)

if __name__ == "__main__":
    sync_dummyjson_catalog()

