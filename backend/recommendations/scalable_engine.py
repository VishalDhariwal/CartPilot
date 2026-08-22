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
    from openai import OpenAI
    from backend.db import get_db

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY not set — skipping category compatibility generation.")
        return {"inserted": 0, "skipped_locked": 0, "total_categories": 0}

    client = OpenAI(api_key=api_key)
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
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You produce cross-category shopping compatibility graphs for e-commerce recommendation engines."},
                {"role": "user", "content": prompt}
            ],
            response_format=CategoryCompatResponse,
            temperature=0.2
        )
        pairs = completion.choices[0].message.parsed.pairs
    except Exception as e:
        print(f"⚠️ LLM call failed for category compatibility: {e}")
        conn.close()
        return {"inserted": 0, "skipped_locked": 0, "total_categories": len(categories)}

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

    if len(sequences) < min_orders:
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

    # Load cart item embeddings
    cart_skus = [i["sku"] for i in cart_items if "sku" in i]
    if not cart_skus:
        conn.close()
        return []

    placeholders = ",".join(["?"] * len(cart_skus))
    cursor.execute(
        f"SELECT sku, co_purchase_embedding FROM catalog WHERE sku IN ({placeholders})",
        cart_skus
    )
    cart_rows = cursor.fetchall()

    cart_vecs = []
    for row in cart_rows:
        if row["co_purchase_embedding"]:
            try:
                vec = np.array(json.loads(row["co_purchase_embedding"]), dtype=np.float32)
                cart_vecs.append(vec)
            except Exception:
                pass

    if not cart_vecs:
        conn.close()
        return []

    # Average cart vector
    query_vec = np.mean(cart_vecs, axis=0)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        conn.close()
        return []
    query_vec = query_vec / query_norm

    # Load all in-stock catalog embeddings (excluding cart & already-seen SKUs)
    excluded = list(exclude_skus | set(cart_skus))
    exc_placeholders = ",".join(["?"] * len(excluded)) if excluded else "NULL"
    cursor.execute(
        f"""
        SELECT sku, name, price_paise, category, boosted, image_url, description, metadata, co_purchase_embedding
        FROM catalog
        WHERE stock > 0
          AND co_purchase_embedding IS NOT NULL
          {"AND sku NOT IN (" + exc_placeholders + ")" if excluded else ""}
        """,
        excluded if excluded else []
    )
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

    top_indices = np.argsort(-similarities)[:top_k]

    results = []
    for i in top_indices:
        row = cand_meta[i]
        sim = float(similarities[i])
        boosted = bool(row["boosted"])
        boost_mul = 1.35 if boosted else 1.0
        final_score = round(sim * boost_mul, 6)

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                pass

        reason = f"Learned from {real_order_count} real orders' co-purchase patterns."
        if boosted:
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
            "reasoning": None,
            "co_occurrence_count": real_order_count,
            "final_score": final_score,
            "boosted": boosted,
            "trigger_sku": cart_skus[0] if cart_skus else "",
            "trigger_name": "your cart",
            "reason": reason,
            "cosine_similarity": round(sim, 4)
        })

    return results


# ── Layer 1: Category-match candidates at recommendation time ─────────────────

def find_category_compat_candidates(
    cart_items: list[dict],
    exclude_skus: set[str],
    top_k: int = 5
) -> list[dict]:
    """
    Layer 1 cold-start: for each category in the cart, look up category_compatibility
    to find compatible target categories, then return in-stock items from those categories,
    ranked by boosted DESC.

    Never shows a fabricated lift or statistical metric.
    source = "category_match"
    """
    from backend.db import get_db

    if not cart_items:
        return []

    cart_categories = list({i.get("category") for i in cart_items if i.get("category")})
    if not cart_categories:
        return []

    conn = get_db()
    cursor = conn.cursor()

    cat_placeholders = ",".join(["?"] * len(cart_categories))
    cursor.execute(
        f"""
        SELECT category_b AS compat_cat, reasoning
        FROM category_compatibility
        WHERE category_a IN ({cat_placeholders})
          AND category_b NOT IN ({cat_placeholders})
        UNION
        SELECT category_a AS compat_cat, reasoning
        FROM category_compatibility
        WHERE category_b IN ({cat_placeholders})
          AND category_a NOT IN ({cat_placeholders})
        """,
        cart_categories + cart_categories + cart_categories + cart_categories
    )
    compat_rows = cursor.fetchall()

    if not compat_rows:
        conn.close()
        return []

    # Shuffle the compatible categories to add variety
    import random
    compat_list = [dict(r) for r in compat_rows]
    random.shuffle(compat_list)

    compat_categories = [r["compat_cat"] for r in compat_list]
    compat_reasoning = {r["compat_cat"]: r["reasoning"] for r in compat_list}

    excluded = list(exclude_skus | {i["sku"] for i in cart_items if "sku" in i})
    exc_placeholders = ",".join(["?"] * len(excluded)) if excluded else "NULL"
    cat_in = ",".join(["?"] * len(compat_categories))

    cursor.execute(
        f"""
        SELECT sku, name, price_paise, category, boosted, image_url, description, metadata
        FROM catalog
        WHERE stock > 0
          AND category IN ({cat_in})
          {"AND sku NOT IN (" + exc_placeholders + ")" if excluded else ""}
        ORDER BY boosted DESC, price_paise ASC
        LIMIT ?
        """,
        compat_categories + (excluded if excluded else []) + [top_k * 2]
    )
    rows = cursor.fetchall()
    conn.close()

    results = []
    seen_cats = defaultdict(int)

    for row in rows:
        cat = row["category"]
        if seen_cats[cat] >= 2:
            continue
        seen_cats[cat] += 1

        boosted = bool(row["boosted"])
        boost_mul = 1.35 if boosted else 1.0
        final_score = round(boost_mul, 4)

        cat_reason = compat_reasoning.get(cat, f"Complementary {cat} item for your shopping trip.")
        reason = f"Category match: {cat_reason}"
        if boosted:
            reason += " Featured partner recommendation."

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                pass

        results.append({
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": row["price_paise"],
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
            "trigger_sku": cart_items[0].get("sku", "") if cart_items else "",
            "trigger_name": "your cart",
            "reason": reason
        })

        if len(results) >= top_k:
            break

    return results
