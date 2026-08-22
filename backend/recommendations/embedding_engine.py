import json
import math
import sqlite3
from typing import Optional
from backend.db import get_db

_MODEL = None

def get_model():
    """
    Lazily loads and caches the SentenceTransformer model on CPU.
    """
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            print(f"⚠️ Warning: Could not load SentenceTransformer: {e}")
            _MODEL = None
    return _MODEL


def compute_embedding(text: str) -> list[float]:
    """
    Computes a 384-dimensional dense vector embedding for input text.
    """
    model = get_model()
    if model is not None:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    # Fallback to OpenAI embedding if sentence-transformers is not available
    try:
        import os
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return resp.data[0].embedding
    except Exception as e:
        print(f"Error computing fallback embedding: {e}")
        
    return []


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Calculates cosine similarity between two normalized vectors.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def precompute_catalog_embeddings(force: bool = False) -> int:
    """
    Computes and saves embeddings for all catalog items where embedding is NULL.
    Returns the number of item embeddings updated.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT sku, name, category, merchant, embedding FROM catalog"
    if not force:
        query += " WHERE embedding IS NULL OR embedding = ''"

    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return 0

    print(f"🔄 Computing embeddings for {len(rows)} catalog items...")
    model = get_model()
    updated_count = 0

    texts_to_encode = []
    skus = []

    for row in rows:
        text = f"{row['name']} | category: {row['category']}"
        texts_to_encode.append(text)
        skus.append(row["sku"])


    if model is not None:
        embeddings = model.encode(texts_to_encode, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        updates = [(json.dumps(emb.tolist()), sku) for emb, sku in zip(embeddings, skus)]
        cursor.executemany("UPDATE catalog SET embedding = ? WHERE sku = ?", updates)
        conn.commit()
        updated_count = len(updates)
    else:
        # Fast batch fallback with OpenAI embeddings
        try:
            import os
            from openai import OpenAI
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                client = OpenAI(api_key=api_key)
                batch_size = 100
                for i in range(0, len(texts_to_encode), batch_size):
                    batch_texts = texts_to_encode[i:i+batch_size]
                    batch_skus = skus[i:i+batch_size]
                    resp = client.embeddings.create(
                        model="text-embedding-3-small",
                        input=batch_texts
                    )
                    updates = [(json.dumps(item.embedding), sku) for item, sku in zip(resp.data, batch_skus)]
                    cursor.executemany("UPDATE catalog SET embedding = ? WHERE sku = ?", updates)
                    conn.commit()
                    updated_count += len(updates)
        except Exception as e:
            print(f"Error in batch fallback embeddings: {e}")

    conn.close()
    print(f"✅ Precomputed embeddings for {updated_count} catalog items.")
    return updated_count



def find_substitutes(
    missing_item_or_description: str,
    budget_remaining_paise: Optional[int] = None,
    top_k: int = 3,
    min_similarity: float = 0.40
) -> list[dict]:
    """
    Finds top semantic in-stock substitutes for a missing or out-of-stock item.
    Uses cosine similarity of dense embeddings, filtered by budget and boosted by merchant priority.
    """
    conn = get_db()
    cursor = conn.cursor()

    target_embedding = None
    target_name = missing_item_or_description
    target_category = None

    # Check if input is an existing SKU
    cursor.execute("SELECT sku, name, category, price_paise, embedding FROM catalog WHERE sku = ?", (missing_item_or_description,))
    orig_row = cursor.fetchone()

    if orig_row:
        target_name = orig_row["name"]
        target_category = orig_row["category"]
        if orig_row["embedding"]:
            try:
                target_embedding = json.loads(orig_row["embedding"])
            except Exception:
                target_embedding = None

    # If no stored embedding found, compute directly from text
    if not target_embedding:
        target_text = f"{target_name} | category: {target_category or 'general'}"
        target_embedding = compute_embedding(target_text)

    if not target_embedding:
        conn.close()
        return []

    # Fetch all in-stock catalog items with embeddings
    cursor.execute(
        """SELECT sku, name, price_paise, category, merchant, stock, boosted, image_url, description, metadata, embedding 
           FROM catalog 
           WHERE stock > 0 AND embedding IS NOT NULL AND embedding != ''"""
    )
    candidates = cursor.fetchall()
    conn.close()

    results = []

    for row in candidates:
        if orig_row and row["sku"] == orig_row["sku"]:
            continue  # Don't suggest the exact same OOS item

        if budget_remaining_paise is not None and row["price_paise"] > budget_remaining_paise:
            continue  # Hard budget filter

        try:
            cand_embedding = json.loads(row["embedding"])
        except Exception:
            continue

        raw_sim = cosine_similarity(target_embedding, cand_embedding)

        if raw_sim < min_similarity:
            continue

        boosted = row["boosted"] or 0
        boost_multiplier = 1.15 if boosted else 1.0
        final_score = round(raw_sim * boost_multiplier, 4)

        reason = f"Closest in-stock semantic alternative ({raw_sim*100:.0f}% similarity) in {row['category']}."
        if boosted:
            reason += " Featured partner product."

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                meta_obj = {}

        results.append({
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": row["price_paise"],
            "category": row["category"],
            "stock": row["stock"],
            "image_url": row["image_url"] or "",
            "description": row["description"] or "",
            "metadata": meta_obj,
            "similarity_score": round(raw_sim, 4),
            "final_score": final_score,
            "boosted": bool(boosted),
            "original_query": target_name,
            "reason": reason
        })


    # Sort descending by final_score
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results[:top_k]

