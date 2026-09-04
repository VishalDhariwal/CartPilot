"""
scalable_engine.py
==================
Scalable Recommendation Architecture — Layers 1 & 2.

Layer 1: Category Compatibility Graph
  - One LLM call across all catalog categories → a small graph of compatible category pairs.
  - Scales by *category count*, not by product count. Survives millions of products.
  - Merchant-editable: rows with editable=0 are NEVER overwritten by regeneration.

Layer 2: Co-purchase Embeddings (item2vec style)
  - Pure-numpy skip-gram with negative sampling over real order sequences.
  - Trained only on historical_orders WHERE is_synthetic = 0 (real orders).
  - Requires >= min_orders real orders; returns a clean insufficient_data status below that.
  - Vectors stored per-SKU in catalog.co_purchase_embedding (JSON float array).
  - At recommendation time: cosine similarity of average cart vector vs all catalog embeddings.
"""
import os
import json
import math
import random
import numpy as np
from datetime import datetime
from collections import defaultdict
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# ── Pydantic schema for structured LLM output ────────────────────────────────

class CategoryPair(BaseModel):
    category_a: str
    category_b: str
    reasoning: str  # One-line plain-language explanation


class CategoryCompatResponse(BaseModel):
    pairs: list[CategoryPair]


# ── Layer 1: Category Compatibility Graph ─────────────────────────────────────

def generate_category_compatibility() -> dict:
    """
    Layer 1 cold-start: ask the LLM which catalog categories are commonly
    purchased together, then persist as category_compatibility rows.

    - Uses a SINGLE LLM call (not per-product), so this scales by category count.
    - NEVER overwrites rows where editable=0 (merchant-locked decisions).
    - Returns {"inserted": N, "skipped_locked": M, "total_categories": K}
    """
    from backend.engine.llm import generate_structured, get_available_providers
    from backend.db import get_db

    if not get_available_providers():
        print("⚠️ Neither OPENAI_API_KEY nor GEMINI_API_KEY is set — skipping category compatibility generation.")
        return {"inserted": 0, "skipped_locked": 0, "total_categories": 0}

    conn = get_db()
    cursor = conn.cursor()

    # Fetch distinct catalog categories
    cursor.execute(
        "SELECT DISTINCT category FROM catalog WHERE category IS NOT NULL AND stock > 0 ORDER BY category"
    )
    categories = [row["category"] for row in cursor.fetchall()]

    if len(categories) < 2:
        conn.close()
        return {"inserted": 0, "skipped_locked": 0, "total_categories": len(categories)}

    # Fetch already-locked rows (merchant edits — must not regenerate)
    cursor.execute(
        "SELECT category_a, category_b FROM category_compatibility WHERE editable = 0"
    )
    locked_pairs = {(r["category_a"], r["category_b"]) for r in cursor.fetchall()}
    conn.close()

    cat_list_str = "\n".join(f"- {c}" for c in categories)

    prompt = f"""You are an expert e-commerce merchandising analyst.

Below is the complete list of product categories in our catalog.
Your task: identify which category pairs are commonly purchased together on the same shopping trip.
For each compatible pair, write one concise plain-language reason.

CATALOG CATEGORIES:
{cat_list_str}

RULES:
1. Output realistic, cross-category complements only (e.g. motorcycle ↔ sunglasses, laptop ↔ mobile-accessories).
2. Do NOT pair a category with itself.
3. Do NOT output pairs that are the same category with minor wording differences.
4. Produce roughly the same number of pairs as there are categories (target ~{len(categories)} pairs total, not more than {len(categories) * 2}).
5. Each reasoning must be a single concise sentence (e.g. "Riders typically buy protective eyewear alongside their motorcycle.").
6. Only use category names from the list above — no invented categories.
"""

    try:
        data = generate_structured(
            prompt=prompt,
            schema=CategoryCompatResponse,
            system_prompt="You produce cross-category shopping compatibility graphs for e-commerce recommendation engines."
        )
        pairs = data.pairs
    except Exception as e:
        print(f"⚠️ LLM call failed for category compatibility: {e}")
        return {"inserted": 0, "skipped_locked": 0, "total_categories": len(categories)}

    conn = get_db()
    cursor = conn.cursor()

    now_iso = datetime.utcnow().isoformat() + "Z"
    cat_set = set(categories)
    inserted = 0
    skipped_locked = 0

    for pair in pairs:
        a, b = pair.category_a.strip(), pair.category_b.strip()
        # Validate both categories exist in catalog
        if a not in cat_set or b not in cat_set or a == b:
            continue
        # Canonical alphabetical ordering to avoid mirrored duplicates
        cat_a, cat_b = sorted([a, b])
        if (cat_a, cat_b) in locked_pairs:
            skipped_locked += 1
            continue
        cursor.execute(
            """
            INSERT INTO category_compatibility (category_a, category_b, reasoning, editable, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(category_a, category_b) DO UPDATE SET
                reasoning = excluded.reasoning,
                created_at = excluded.created_at
            WHERE category_compatibility.editable = 1
            """,
            (cat_a, cat_b, pair.reasoning.strip(), now_iso)
        )
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()

    print(f"✅ Category compatibility graph: {inserted} pairs written, {skipped_locked} merchant-locked pairs preserved.")
    return {"inserted": inserted, "skipped_locked": skipped_locked, "total_categories": len(categories)}


# ── Layer 2: Co-purchase Embeddings (item2vec — pure numpy) ─────────────────

_EMBEDDING_DIM = 64
_WINDOW = 3
_NEG_SAMPLES = 5
_EPOCHS = 10
_LEARNING_RATE = 0.025
_MIN_ORDERS = 50  # Below this, training is meaningless — clean fallback


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -10, 10)))


def _build_vocab(sequences: list[list[str]]) -> tuple[dict, np.ndarray]:
    """Build SKU vocab and frequency table for negative sampling."""
    freq = defaultdict(int)
    for seq in sequences:
        for token in seq:
            freq[token] += 1
    vocab = {sku: idx for idx, sku in enumerate(sorted(freq.keys()))}
    # Frequency table for negative sampling (unigram^0.75)
    freqs = np.array([freq[sku] ** 0.75 for sku in sorted(freq.keys())], dtype=np.float32)
    freqs /= freqs.sum()
    return vocab, freqs


def train_co_purchase_embeddings(min_orders: int = _MIN_ORDERS) -> dict:
    """
    Layer 2: Train item2vec (skip-gram + negative sampling) over real completed orders.

    - Input: historical_orders WHERE is_synthetic = 0 only.
    - If real order count < min_orders: returns {"status": "insufficient_data", "real_order_count": N}
      Clean fallback — no crash, no training on synthetic data.
    - Writes embedding vectors to catalog.co_purchase_embedding as JSON float arrays.
    - Returns training summary dict.
    """
    from backend.db import get_db

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT items FROM historical_orders WHERE is_synthetic = 0")
    rows = cursor.fetchall()
    real_order_count = len(rows)

    if real_order_count < min_orders:
        print(f"⚠️ Layer 2 embeddings: only {real_order_count} real orders (need {min_orders}). Skipping training.")
        conn.close()
        return {"status": "insufficient_data", "real_order_count": real_order_count, "min_orders": min_orders}

    sequences = []
    for row in rows:
        try:
            items = json.loads(row["items"]) if isinstance(row["items"], str) else row["items"]
            if len(items) >= 2:
                sequences.append([str(s) for s in items])
        except Exception:
            continue

    if len(sequences) < 2:
        conn.close()
        return {"status": "insufficient_data", "real_order_count": real_order_count, "min_orders": min_orders}

    print(f"🧠 Training item2vec on {len(sequences)} real order sequences...", flush=True)

    vocab, neg_freq = _build_vocab(sequences)
    V = len(vocab)
    idx_to_sku = {v: k for k, v in vocab.items()}

    # Skip-gram matrices: W_in (target embedding), W_out (context projection)
    rng = np.random.default_rng(42)
    W_in  = rng.standard_normal((V, _EMBEDDING_DIM)).astype(np.float32) * 0.01
    W_out = np.zeros((V, _EMBEDDING_DIM), dtype=np.float32)

    # Training loop
    for epoch in range(_EPOCHS):
        lr = _LEARNING_RATE * (1 - epoch / _EPOCHS)
        random.shuffle(sequences)

        for seq in sequences:
            indices = [vocab[t] for t in seq if t in vocab]
            if len(indices) < 2:
                continue

            for pos, center in enumerate(indices):
                # Determine window
                start = max(0, pos - _WINDOW)
                end = min(len(indices), pos + _WINDOW + 1)
                context_indices = [indices[i] for i in range(start, end) if i != pos]

                for ctx in context_indices:
                    # Positive sample
                    h = W_in[center]  # shape (D,)
                    score_pos = _sigmoid(W_out[ctx] @ h)
                    grad_ctx_pos = (score_pos - 1.0) * h
                    grad_h_pos = (score_pos - 1.0) * W_out[ctx]

                    # Negative samples (unigram^0.75 distribution)
                    num_negs = min(V, _NEG_SAMPLES)
                    neg_indices = np.random.choice(V, size=num_negs, p=neg_freq, replace=True)
                    neg_scores = _sigmoid(W_out[neg_indices] @ h)  # (num_negs,)
                    grad_h_neg = (neg_scores[:, None] * W_out[neg_indices]).sum(axis=0)

                    # Updates
                    W_out[ctx]           -= lr * grad_ctx_pos
                    W_out[neg_indices]   -= lr * (neg_scores[:, None] * h[None, :])
                    W_in[center]         -= lr * (grad_h_pos + grad_h_neg)

    print(f"✅ item2vec training complete. Writing {V} embedding vectors to catalog.", flush=True)

    # Write embeddings back to catalog
    now_iso = datetime.utcnow().isoformat() + "Z"
    skus_updated = 0

    for idx in range(V):
        sku = idx_to_sku[idx]
        vec = W_in[idx].tolist()
        cursor.execute(
            "UPDATE catalog SET co_purchase_embedding = ? WHERE sku = ?",
            (json.dumps(vec), sku)
        )
        if cursor.rowcount > 0:
            skus_updated += 1

    conn.commit()
    conn.close()

    return {
        "status": "trained",
        "real_order_count": real_order_count,
        "skus_updated": skus_updated,
        "embedding_dim": _EMBEDDING_DIM,
        "epochs": _EPOCHS,
        "trained_at": now_iso
    }


def get_embedding_status() -> dict:
    """Returns current embedding training status without re-training."""
    from backend.db import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM historical_orders WHERE is_synthetic = 0")
    real_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM catalog WHERE co_purchase_embedding IS NOT NULL")
    skus_with_embeddings = cursor.fetchone()[0]
    conn.close()
    return {
        "real_order_count": real_orders,
        "min_orders_required": _MIN_ORDERS,
        "skus_with_embeddings": skus_with_embeddings,
        "trained": skus_with_embeddings > 0,
        "ready": real_orders >= _MIN_ORDERS
    }


# ── Layer 2: Nearest Neighbor Lookup at Recommendation Time ──────────────────

def find_co_purchase_neighbors(
    cart_items: list[dict],
    exclude_skus: set[str],
    top_k: int = 5
) -> list[dict]:
    """
    Given a list of cart items, compute the average of their co-purchase embedding vectors,
    then return the top_k most similar in-stock catalog items by cosine similarity.

    Returns [] if:
    - No embeddings are trained yet (catalog.co_purchase_embedding is NULL for cart items).
    - Cart items have no embeddings.
    - No candidates remain after excluding cart/already-seen SKUs.

    Never fabricates lift or statistical metrics. Each returned candidate carries:
      source = "co_purchase"
      lift = None, support = None, confidence = None
      reason = "Learned from <N> real orders' co-purchase patterns."
    """
    from backend.db import get_db

    if not cart_items:
        return []

    conn = get_db()
    cursor = conn.cursor()

    # Get co-purchase embedding count so we can report in reason string
    cursor.execute("SELECT COUNT(*) FROM historical_orders WHERE is_synthetic = 0")
    real_order_count = cursor.fetchone()[0]

    # Load cart item metadata & embeddings
    cart_skus = [i["sku"] for i in cart_items if "sku" in i]
    if not cart_skus:
        conn.close()
        return []

    placeholders = ",".join(["?"] * len(cart_skus))
    cursor.execute(
        f"SELECT sku, name, category, price_paise, co_purchase_embedding FROM catalog WHERE sku IN ({placeholders})",
        cart_skus
    )
    cart_rows = cursor.fetchall()

    cart_vecs = []
    cart_cats = set()
    cart_prices = []

    for row in cart_rows:
        if row["category"]:
            cart_cats.add(row["category"])
        if row["price_paise"]:
            cart_prices.append(row["price_paise"])
        if row["co_purchase_embedding"]:
            try:
                vec = np.array(json.loads(row["co_purchase_embedding"]), dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    cart_vecs.append(vec / norm)
            except Exception:
                pass

    if not cart_vecs:
        conn.close()
        return []

    # Verify if these cart SKUs actually participated in real co-purchase orders.
    # If a cart SKU has < 2 real orders, its vector is untrained random noise.
    # Falling back cleanly to Tier 3 (Category Graph + Dense MiniLM Semantic Embeddings)
    # guarantees relevant, high-quality recommendations.
    order_placeholders = " OR ".join(["items LIKE ?" for _ in cart_skus])
    order_params = [f"%{sku}%" for sku in cart_skus]
    cursor.execute(
        f"SELECT COUNT(*) FROM historical_orders WHERE is_synthetic = 0 AND ({order_placeholders})",
        order_params
    )
    matching_orders = cursor.fetchone()[0]
    if matching_orders < 2:
        conn.close()
        return []

    # Average normalized cart vector
    query_vec = np.mean(cart_vecs, axis=0)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        conn.close()
        return []
    query_vec = query_vec / query_norm

    # Determine compatible categories for the cart items
    target_categories = set(cart_cats)
    if cart_cats:
        cat_placeholders = ",".join(["?"] * len(cart_cats))
        cursor.execute(
            f"""
            SELECT category_b FROM category_compatibility WHERE category_a IN ({cat_placeholders})
            UNION
            SELECT category_a FROM category_compatibility WHERE category_b IN ({cat_placeholders})
            """,
            list(cart_cats) + list(cart_cats)
        )
        for r in cursor.fetchall():
            if r[0]:
                target_categories.add(r[0])

    if not target_categories:
        target_categories = set(cart_cats)

    # Price plausibility: prevent exorbitant upsells (e.g. ₹25,000 car for a ₹20 slipper)
    max_cart_price = max(cart_prices) if cart_prices else 200000
    price_cap = max(max_cart_price * 4, 250000)

    # Load in-stock catalog candidates within compatible categories and price limits
    excluded = list(exclude_skus | set(cart_skus))
    exc_placeholders = ",".join(["?"] * len(excluded)) if excluded else "NULL"
    compat_placeholders = ",".join(["?"] * len(target_categories))

    sql = f"""
        SELECT sku, name, price_paise, category, boosted, boost_weight, boost_source, boost_reason, image_url, description, metadata, co_purchase_embedding
        FROM catalog
        WHERE stock > 0
          AND co_purchase_embedding IS NOT NULL
          AND price_paise <= ?
          AND category IN ({compat_placeholders})
          {"AND sku NOT IN (" + exc_placeholders + ")" if excluded else ""}
    """
    params = [price_cap] + list(target_categories) + (excluded if excluded else [])
    cursor.execute(sql, params)
    cand_rows = cursor.fetchall()
    conn.close()

    if not cand_rows:
        return []

    # Batch cosine similarity
    cand_skus = []
    cand_vecs = []
    cand_meta = []

    for row in cand_rows:
        try:
            vec = np.array(json.loads(row["co_purchase_embedding"]), dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                cand_skus.append(row["sku"])
                cand_vecs.append(vec / norm)
                cand_meta.append(row)
        except Exception:
            continue

    if not cand_vecs:
        return []

    cand_matrix = np.stack(cand_vecs, axis=0)  # (N, D)
    similarities = cand_matrix @ query_vec       # (N,)

    # Only accept candidates with high affinity (>= 0.65) to reject uncorrelated noise
    qual_indices = [i for i in range(len(similarities)) if similarities[i] >= 0.65]
    if not qual_indices:
        return []

    top_indices = sorted(qual_indices, key=lambda i: similarities[i], reverse=True)[:top_k]

    results = []
    for i in top_indices:
        row = cand_meta[i]
        sim = float(similarities[i])
        boosted = bool(row["boosted"])
        boost_weight = float(row["boost_weight"]) if ("boost_weight" in row.keys() and row["boost_weight"] is not None) else 1.0
        boost_source = str(row["boost_source"]) if ("boost_source" in row.keys() and row["boost_source"]) else "system"
        boost_reason = str(row["boost_reason"]) if ("boost_reason" in row.keys() and row["boost_reason"]) else ""

        if boost_source == "manual" and boosted:
            boost_mul = 1.35
        else:
            boost_mul = boost_weight if boost_weight != 1.0 else (1.35 if boosted else 1.0)

        final_score = round(sim * boost_mul, 6)

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                pass

        reason = f"Learned from {real_order_count} real orders' co-purchase patterns."
        if boost_reason:
            reason += f" Seasonal merchandising: {boost_reason}."
        elif boosted:
            reason += " Featured partner recommendation."

        results.append({
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": row["price_paise"],
            "category": row["category"],
            "image_url": row["image_url"] or "",
            "description": row["description"] or "",
            "metadata": meta_obj,
            "source": "co_purchase",
            "lift": None,
            "support": None,
            "confidence": None,
            "reasoning": f"Co-purchase vector similarity: {sim:.2f}",
            "co_occurrence_count": matching_orders,
            "final_score": final_score,
            "similarity_score": round(sim, 4),
            "boosted": boosted,
            "boost_weight": boost_weight,
            "boost_source": boost_source,
            "boost_reason": boost_reason,
            "trigger_sku": cart_skus[0] if cart_skus else "",
            "trigger_name": "your cart",
            "reason": reason,
            "cosine_similarity": round(sim, 4)
        })

    return results


# ── Layer 1: Live Category-Scoped Selection at Recommendation Time ───────────

def find_live_category_candidates(
    cart_items: list[dict],
    exclude_skus: Optional[set[str]] = None,
    top_k: int = 3
) -> list[dict]:
    """
    Live Category-Scoped Semantic Selection (replaces static per-SKU priors):
    1. For each item in the cart, identify its category and query category_compatibility
       for compatible complement categories (excluding categories already in the cart).
    2. Pool all in-stock catalog items belonging to those compatible categories.
    3. Run dense embedding similarity between the cart's average representation and the pooled candidates.
       Ties are broken toward closer price tiers to what's already in the cart.
    4. Apply merchant boost multiplier (1.35x) to elevate featured partner inventory.
    5. Return top_k candidates directly in-memory with zero disk persistence (never stale!).

    Never fabricates lift or statistical metrics.
    source = "live_category" (or "category_match")
    """
    from backend.db import get_db

    if not cart_items:
        return []

    if exclude_skus is None:
        exclude_skus = set()

    conn = get_db()
    cursor = conn.cursor()

    # Resolve categories and prices for cart items if missing
    cart_skus = [i.get("sku") for i in cart_items if i.get("sku")]
    cart_cats = set()
    cart_prices = []
    cart_sku_meta = {}

    if cart_skus:
        placeholders = ",".join(["?"] * len(cart_skus))
        cursor.execute(
            f"SELECT sku, name, category, price_paise, embedding FROM catalog WHERE sku IN ({placeholders})",
            cart_skus
        )
        for r in cursor.fetchall():
            cart_sku_meta[r["sku"]] = dict(r)
            if r["category"]:
                cart_cats.add(r["category"])
            if r["price_paise"]:
                cart_prices.append(r["price_paise"])

    for i in cart_items:
        if i.get("category"):
            cart_cats.add(i["category"])
        if i.get("price_paise"):
            cart_prices.append(i["price_paise"])

    cart_categories = list(cart_cats)
    if not cart_categories:
        conn.close()
        return []

    avg_cart_price = float(np.mean(cart_prices)) if cart_prices else 1000.0

    # Query category_compatibility for compatible target categories (bidirectional UNION)
    cat_placeholders = ",".join(["?"] * len(cart_categories))
    cursor.execute(
        f"""
        SELECT category_b AS compat_cat, category_a AS trigger_cat, reasoning
        FROM category_compatibility
        WHERE category_a IN ({cat_placeholders})
        UNION
        SELECT category_a AS compat_cat, category_b AS trigger_cat, reasoning
        FROM category_compatibility
        WHERE category_b IN ({cat_placeholders})
        """,
        cart_categories + cart_categories
    )
    compat_rows = cursor.fetchall()

    # Target categories include cart's own categories (intra-category complements) + compatible partner categories
    target_category_set = set(cart_categories)
    compat_reasoning = {}
    compat_triggers = {}

    for cat in cart_categories:
        clean_name = cat.replace('-', ' ')
        compat_reasoning[cat] = f"Complementary {clean_name} selection to complete your cart."
        compat_triggers[cat] = cat

    for r in compat_rows:
        target_category_set.add(r["compat_cat"])
        compat_reasoning[r["compat_cat"]] = r["reasoning"]
        compat_triggers[r["compat_cat"]] = r["trigger_cat"]

    compat_categories = list(target_category_set)
    if not compat_categories:
        conn.close()
        return []

    # Extract cart embedding representation (average normalized 384-d dense vector)
    cart_vecs = []
    for sku in cart_skus:
        meta = cart_sku_meta.get(sku, {})
        emb_str = meta.get("embedding")
        if emb_str:
            try:
                vec = np.array(json.loads(emb_str), dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    cart_vecs.append(vec / norm)
            except Exception:
                pass

    cart_query_vec = None
    if cart_vecs:
        avg_vec = np.mean(cart_vecs, axis=0)
        norm = np.linalg.norm(avg_vec)
        if norm > 0:
            cart_query_vec = avg_vec / norm

    # Pool all in-stock catalog items in compatible categories
    excluded = list(exclude_skus | set(cart_skus))
    exc_placeholders = ",".join(["?"] * len(excluded)) if excluded else "NULL"
    cat_in = ",".join(["?"] * len(compat_categories))

    cursor.execute(
        f"""
        SELECT sku, name, price_paise, category, boosted, boost_weight, boost_source, boost_reason, image_url, description, metadata, embedding
        FROM catalog
        WHERE stock > 0
          AND category IN ({cat_in})
          {"AND sku NOT IN (" + exc_placeholders + ")" if excluded else ""}
        """,
        compat_categories + (excluded if excluded else [])
    )
    candidate_rows = cursor.fetchall()
    conn.close()

    if not candidate_rows:
        return []

    # Score candidates using cosine similarity, price tier proximity, and merchant/seasonal boost
    scored = []
    for row in candidate_rows:
        cat = row["category"]
        cand_price = row["price_paise"] or 0

        # Embedding similarity
        raw_sim = 0.50  # Default neutral baseline if embedding not available
        if cart_query_vec is not None and row["embedding"]:
            try:
                cand_vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
                cand_norm = np.linalg.norm(cand_vec)
                if cand_norm > 0:
                    raw_sim = float(np.dot(cart_query_vec, cand_vec / cand_norm))
            except Exception:
                pass

        # Price proximity factor: closer price tiers break ties favorably
        price_diff_ratio = abs(cand_price - avg_cart_price) / max(1.0, avg_cart_price)
        price_factor = 1.0 / (1.0 + 0.15 * min(price_diff_ratio, 10.0))

        # Promotion & Seasonal boost multiplier
        boosted = bool(row["boosted"])
        boost_weight = float(row["boost_weight"]) if ("boost_weight" in row.keys() and row["boost_weight"] is not None) else 1.0
        boost_source = str(row["boost_source"]) if ("boost_source" in row.keys() and row["boost_source"]) else "system"
        boost_reason = str(row["boost_reason"]) if ("boost_reason" in row.keys() and row["boost_reason"]) else ""

        if boost_source == "manual" and boosted:
            boost_mul = 1.35
        else:
            boost_mul = boost_weight if boost_weight != 1.0 else (1.35 if boosted else 1.0)

        final_score = round(raw_sim * price_factor * boost_mul, 4)

        cat_reason = compat_reasoning.get(cat, f"Complementary {cat} selection for your cart.")
        reason = f"Category match: {cat_reason}"
        if boost_reason:
            reason += f" Seasonal merchandising: {boost_reason}."
        elif boosted:
            reason += " Featured partner recommendation."

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                pass

        trigger_sku = cart_skus[0] if cart_skus else ""
        trigger_name = cart_sku_meta.get(trigger_sku, {}).get("name", "your cart")

        scored.append({
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": cand_price,
            "category": cat,
            "image_url": row["image_url"] or "",
            "description": row["description"] or "",
            "metadata": meta_obj,
            "source": "category_match",
            "lift": None,
            "support": None,
            "confidence": None,
            "reasoning": cat_reason,
            "co_occurrence_count": 0,
            "final_score": final_score,
            "boosted": boosted,
            "boost_weight": boost_weight,
            "boost_source": boost_source,
            "boost_reason": boost_reason,
            "trigger_sku": trigger_sku,
            "trigger_name": trigger_name,
            "reason": reason,
            "cosine_similarity": round(raw_sim, 4)
        })

    # Sort descending by final_score
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # Ensure category diversity: max 2 items per category in top recommendations
    diverse_results = []
    seen_cats = defaultdict(int)
    for item in scored:
        if seen_cats[item["category"]] < 2:
            diverse_results.append(item)
            seen_cats[item["category"]] += 1
            if len(diverse_results) >= top_k:
                break

    # If diverse filter produced fewer than top_k, fill up to top_k
    if len(diverse_results) < top_k:
        seen_skus = {x["sku"] for x in diverse_results}
        for item in scored:
            if item["sku"] not in seen_skus:
                diverse_results.append(item)
                if len(diverse_results) >= top_k:
                    break

    return diverse_results


# Backwards compatibility alias
find_category_compat_candidates = find_live_category_candidates
