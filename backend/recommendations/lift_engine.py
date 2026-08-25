import os
import json
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from backend.db import get_db

load_dotenv()

# ── Structured Output Models for AI Priors ──────────────────────────────────
class PriorPairing(BaseModel):
    target_sku: str
    suggested_sku: str
    reasoning: str  # One-line explanation grounded in why these two pair well

class CategoryPriorsResponse(BaseModel):
    pairings: list[PriorPairing]


# Complementary category affinity map to ensure rich, cross-category candidate pools
COMPLEMENTARY_CATEGORY_MAP = {
    "motorcycle": ["sunglasses", "mobile-accessories", "sports-accessories", "mens-watches", "mens-shoes"],
    "smartphones": ["mobile-accessories", "laptops", "tablets"],
    "laptops": ["mobile-accessories", "tablets", "smartphones"],
    "tablets": ["mobile-accessories", "laptops", "smartphones"],
    "mobile-accessories": ["smartphones", "laptops", "tablets"],
    "beauty": ["skin-care", "fragrances", "sunglasses", "womens-jewellery"],
    "skin-care": ["beauty", "fragrances", "sunglasses"],
    "fragrances": ["beauty", "skin-care", "mens-watches", "womens-jewellery"],
    "sunglasses": ["mens-shirts", "womens-dresses", "motorcycle", "sports-accessories", "beauty"],
    "mens-shirts": ["mens-shoes", "mens-watches", "sunglasses"],
    "mens-shoes": ["mens-shirts", "mens-watches", "sports-accessories"],
    "mens-watches": ["mens-shirts", "mens-shoes", "fragrances", "sunglasses"],
    "womens-dresses": ["womens-shoes", "womens-bags", "womens-jewellery", "beauty", "fragrances"],
    "womens-shoes": ["womens-dresses", "womens-bags", "womens-jewellery"],
    "womens-bags": ["womens-dresses", "womens-shoes", "womens-jewellery", "sunglasses"],
    "womens-jewellery": ["womens-dresses", "womens-bags", "beauty", "fragrances"],
    "tops": ["womens-shoes", "womens-bags", "sunglasses", "beauty"],
    "groceries": ["kitchen-accessories", "home-decoration"],
    "kitchen-accessories": ["groceries", "home-decoration", "furniture"],
    "furniture": ["home-decoration", "kitchen-accessories"],
    "home-decoration": ["furniture", "kitchen-accessories", "groceries"],
    "sports-accessories": ["sunglasses", "mens-shoes"],
    "vehicle": ["mobile-accessories", "sunglasses"],
}


def generate_ai_priors(batch_size: int = 6) -> int:
    """
    Part 1: LLM-Seeded Priors (Cold-Start Bootstrap).
    Replaces synthetic random orders entirely.
    Uses GPT-4o-mini grounded strictly in catalog inventory to generate
    high-quality, cross-category complementary associations with qualitative reasoning.
    Sets lift, support, and confidence to NULL.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY is not set. Skipping AI priors generation.")
        return 0

    client = OpenAI(api_key=api_key)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT sku, name, category, price_paise, merchant FROM catalog WHERE stock > 0")
    all_catalog_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not all_catalog_rows:
        print("⚠️ No catalog items available to seed priors.")
        return 0

    # Build category indexing
    catalog_by_sku = {item["sku"]: item for item in all_catalog_rows}
    items_by_cat = defaultdict(list)
    for item in all_catalog_rows:
        items_by_cat[item["category"]].append(item)

    all_categories = list(items_by_cat.keys())
    now_iso = datetime.utcnow().isoformat() + "Z"
    total_pairs_inserted = 0

    print(f"🤖 Generating AI-seeded cold-start priors across {len(all_catalog_rows)} catalog items...")

    # Build work batches
    tasks = []
    for cat in all_categories:
        target_items = items_by_cat[cat]
        adjacent_cats = COMPLEMENTARY_CATEGORY_MAP.get(cat, [c for c in all_categories if c != cat][:4])

        # Build rich candidate pool (items from complementary & adjacent categories)
        candidate_pool = []
        for adj_cat in adjacent_cats:
            candidate_pool.extend(items_by_cat.get(adj_cat, [])[:6])

        # Add a few random items from other categories for variety
        other_cats = [c for c in all_categories if c != cat and c not in adjacent_cats]
        for oc in other_cats[:3]:
            candidate_pool.extend(items_by_cat.get(oc, [])[:2])

        if len(candidate_pool) < 6:
            candidate_pool = [i for i in all_catalog_rows if i["category"] != cat][:25]

        candidate_map = {c["sku"]: c for c in candidate_pool}
        candidate_list_str = "\n".join(
            f"- SKU: {c['sku']} | Name: {c['name']} | Category: {c['category']} | ₹{c['price_paise']/100:.0f}"
            for c in candidate_pool
        )

        for i in range(0, len(target_items), batch_size):
            batch = target_items[i:i+batch_size]
            tasks.append((batch, candidate_pool, candidate_map, candidate_list_str))

    print(f"🚀 Dispatching {len(tasks)} parallel prior-generation tasks across worker threads...", flush=True)

    def _process_task(task):
        batch, candidate_pool, candidate_map, candidate_list_str = task
        targets_str = "\n".join(
            f"- TARGET SKU: {t['sku']} | Name: {t['name']} | Category: {t['category']} | ₹{t['price_paise']/100:.0f}"
            for t in batch
        )

        prompt = f"""
You are an expert e-commerce merchandising intelligence system.
For each TARGET item below, select 2 to 3 COMPLEMENTARY items from the CANDIDATE list that customers would naturally buy alongside it.

TARGET ITEMS TO PAIR:
{targets_str}

AVAILABLE CANDIDATES (Choose ONLY from this list):
{candidate_list_str}

STRICT MERCHANDISING RULES:
1. CROSS-CATEGORY COMPLEMENTS ONLY:
   - Pair items across complementary categories (e.g. Motorcycle → Sunglasses / Gear / Phone Holder; Shirt → Watch / Shoes; Laptop → Accessories / Tablet).
   - NEVER pair an item with another item of the exact same category or product type (e.g. NEVER pair Motorcycle with another Motorcycle).
2. STRICT GROUNDING & ANTI-HALLUCINATION:
   - You MUST ONLY select SKUs that explicitly exist in the AVAILABLE CANDIDATES list above. Never invent, truncate, or guess SKUs.
3. CLEAR 1-LINE REASONING:
   - Provide a concise, engaging, 1-line plain-language reason for each pairing (e.g. "Essential eye protection and road style for riding" or "Perfect matching footwear for this casual look").
"""
        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You generate grounded cross-category e-commerce merchandising pairs."},
                    {"role": "user", "content": prompt}
                ],
                response_format=CategoryPriorsResponse,
                temperature=0.2
            )
            data = completion.choices[0].message.parsed
            valid_pairs = []

            for pair in data.pairings:
                t_sku = pair.target_sku.strip()
                s_sku = pair.suggested_sku.strip()
                reason = pair.reasoning.strip()

                if (t_sku in catalog_by_sku and
                    s_sku in catalog_by_sku and
                    s_sku in candidate_map and
                    t_sku != s_sku and
                    reason):
                    valid_pairs.append((
                        t_sku, s_sku, None, None, None,
                        'ai_suggested', reason, 0, now_iso, 0
                    ))
            return valid_pairs
        except Exception as e:
            print(f"⚠️ Error generating AI priors for batch: {e}", flush=True)
            return []

    from concurrent.futures import ThreadPoolExecutor
    all_valid_pairs = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(_process_task, tasks)
        for r in results:
            all_valid_pairs.extend(r)

    if all_valid_pairs:
        conn = get_db()
        cursor = conn.cursor()
        for p in all_valid_pairs:
            cursor.execute(
                """
                INSERT INTO basket_pairs 
                (sku_a, sku_b, lift, support, confidence, source, reasoning, co_occurrence_count, computed_at, muted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku_a, sku_b) DO UPDATE SET
                    reasoning = excluded.reasoning,
                    computed_at = excluded.computed_at
                WHERE basket_pairs.source = 'ai_suggested'
                """,
                p
            )
        conn.commit()
        conn.close()

    total_pairs_inserted = len(all_valid_pairs)
    print(f"✅ Generated and saved {total_pairs_inserted} grounded AI-suggested growth rules.", flush=True)
    return total_pairs_inserted


def compute_lift_pairs(min_co_occurrence: int = 8, min_lift: float = 1.2) -> int:
    """
    Part 2: Real Statistical Rules.
    Mines real orders in historical_orders and cart_mandates to compute Lift, Support, Confidence.
    Strictly gates data_verified rules at:
      - co_occurrence_count >= min_co_occurrence (default >= 8)
      - lift > min_lift (default > 1.2)
    When an empirical rule crosses these thresholds, it graduates to data_verified (retired = 0).
    Any rules falling below these gates are re-retired (retired = 1, source = 'ai_suggested').
    """
    conn = get_db()
    cursor = conn.cursor()

    # Fetch items from historical_orders AND all succeeded cart_mandates
    cursor.execute("SELECT items FROM historical_orders")
    hist_rows = cursor.fetchall()

    cursor.execute("""
        SELECT cm.items 
        FROM cart_mandates cm
        JOIN payment_mandates pm ON pm.cart_id = cm.id
        WHERE pm.status = 'succeeded'
    """)
    settled_rows = cursor.fetchall()

    all_raw_orders = [r["items"] for r in hist_rows] + [r["items"] for r in settled_rows]

    if not all_raw_orders:
        conn.close()
        return 0

    total_orders = len(all_raw_orders)
    item_counts = defaultdict(int)
    pair_counts = defaultdict(int)

    for raw_items in all_raw_orders:
        try:
            parsed = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
            if not parsed:
                continue
            # Extract SKUs whether items are list of strings or list of dicts
            skus = []
            for it in parsed:
                if isinstance(it, dict) and "sku" in it:
                    skus.append(it["sku"])
                elif isinstance(it, str):
                    skus.append(it)
            unique_items = sorted(list(set(skus)))

            for item in unique_items:
                item_counts[item] += 1

            for i in range(len(unique_items)):
                for j in range(len(unique_items)):
                    if i != j:
                        pair_counts[(unique_items[i], unique_items[j])] += 1
        except Exception:
            continue

    now_iso = datetime.utcnow().isoformat() + "Z"
    verified_rules_count = 0

    # Fetch catalog names for explainable audit logging
    cursor.execute("SELECT sku, name FROM catalog")
    catalog_names = {r["sku"]: r["name"] for r in cursor.fetchall()}

    # Re-retire any existing rules that do not meet the strict >=8 co-occurrence & >1.2 lift gates
    cursor.execute(
        """
        UPDATE basket_pairs
        SET source = 'ai_suggested',
            retired = 1,
            lift = NULL,
            support = NULL,
            confidence = NULL
        WHERE source = 'data_verified'
          AND (co_occurrence_count < ? OR lift <= ?)
        """,
        (min_co_occurrence, min_lift)
    )

    for (sku_a, sku_b), pair_freq in pair_counts.items():
        support_a = item_counts[sku_a] / total_orders
        support_b = item_counts[sku_b] / total_orders
        support_ab = pair_freq / total_orders

        if support_a == 0 or support_b == 0:
            continue

        confidence = support_ab / support_a
        lift = confidence / support_b

        # Strict empirical gating: must meet BOTH >= min_co_occurrence AND > min_lift
        if pair_freq < min_co_occurrence or lift <= min_lift:
            # Update co_occurrence_count for progress tracking, but keep retired
            cursor.execute(
                """
                UPDATE basket_pairs 
                SET co_occurrence_count = ?,
                    source = 'ai_suggested',
                    retired = 1,
                    lift = NULL,
                    support = NULL,
                    confidence = NULL
                WHERE sku_a = ? AND sku_b = ?
                """,
                (pair_freq, sku_a, sku_b)
            )
            continue

        # Check if this rule is graduating from ai_suggested / retired
        cursor.execute(
            "SELECT source, retired FROM basket_pairs WHERE sku_a = ? AND sku_b = ?",
            (sku_a, sku_b)
        )
        existing = cursor.fetchone()
        was_unverified = existing and (existing["source"] == "ai_suggested" or existing["retired"] == 1)

        cursor.execute(
            """
            INSERT INTO basket_pairs 
            (sku_a, sku_b, lift, support, confidence, source, reasoning, co_occurrence_count, computed_at, muted, retired)
            VALUES (?, ?, ?, ?, ?, 'data_verified', NULL, ?, ?, 0, 0)
            ON CONFLICT(sku_a, sku_b) DO UPDATE SET
                lift = excluded.lift,
                support = excluded.support,
                confidence = excluded.confidence,
                source = 'data_verified',
                retired = 0,
                reasoning = NULL,
                co_occurrence_count = excluded.co_occurrence_count,
                computed_at = excluded.computed_at
            """,
            (sku_a, sku_b, round(lift, 4), round(support_ab, 4), round(confidence, 4), pair_freq, now_iso)
        )
        verified_rules_count += 1

        if was_unverified:
            from backend.engine.mandates import create_audit_log
            name_a = catalog_names.get(sku_a, sku_a)
            name_b = catalog_names.get(sku_b, sku_b)
            detail = (
                f"Association rule '{name_a}' → '{name_b}' crossed empirical threshold "
                f"({pair_freq} orders >= {min_co_occurrence}, Lift {lift:.2f}x > {min_lift:.1f}x). "
                f"Graduated to data-verified rule (Lift: {lift:.2f}x, Support: {support_ab*100:.1f}%, Confidence: {confidence*100:.1f}%)."
            )
            create_audit_log(cursor, "growth_rule", f"{sku_a}__{sku_b}", "Rule Graduated to Data-Verified", detail)

    conn.commit()
    conn.close()

    print(f"📊 Statistical Mining: {verified_rules_count} pairs reached data_verified status (>= {min_co_occurrence} orders & > {min_lift} lift).")
    return verified_rules_count


def find_cross_sell(cart_items: list, top_k: int = 3) -> list[dict]:
    """
    Live-Computed 3-Tier Recommendation Merge Logic:

    Candidate sources blended in priority order:
      1. Tier 1 (Highest Trust): data_verified rows from basket_pairs (mined exact-pair statistical evidence >= 8 real orders)
      2. Tier 2 (Empirical Sequences): Layer 2 co-purchase embeddings (item2vec nearest neighbors from >= 50 real orders)
      3. Tier 3 (Live Cold-Start): find_live_category_candidates (live-computed category graph + semantic dense embeddings)

    Per-SKU static ai_suggested priors are completely retired and excluded (bp.retired = 0).
    Boost multiplier (1.35x) applies uniformly across all candidates.
    No fake or fabricated numeric lift values for non-empirical layers.
    """
    if not cart_items:
        return []

    conn = get_db()
    cursor = conn.cursor()

    cart_skus = [item["sku"] for item in cart_items if "sku" in item]
    if not cart_skus:
        conn.close()
        return []

    # Map cart SKUs to names
    cursor.execute(
        f"SELECT sku, name FROM catalog WHERE sku IN ({','.join(['?'] * len(cart_skus))})",
        cart_skus
    )
    cart_sku_names = {row["sku"]: row["name"] for row in cursor.fetchall()}

    placeholders = ','.join(['?'] * len(cart_skus))
    # Query only active, non-retired, empirical data_verified rules
    sql = f"""
    SELECT 
        bp.sku_a,
        bp.sku_b,
        bp.lift,
        bp.support,
        bp.confidence,
        bp.source,
        bp.reasoning,
        bp.co_occurrence_count,
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
      AND bp.source = 'data_verified'
      AND (bp.muted IS NULL OR bp.muted = 0)
      AND (bp.retired IS NULL OR bp.retired = 0)
    """

    cursor.execute(sql, cart_skus + cart_skus)
    rows = cursor.fetchall()
    conn.close()

    candidates_by_sku = {}

    # ── Tier 1: Exact-Pair Data-Verified Rules (Highest Priority) ───────────────
    for row in rows:
        sku_b = row["sku_b"]
        source = "data_verified"
        boosted = bool(row["candidate_boosted"] or 0)
        boost_multiplier = 1.35 if boosted else 1.0

        trigger_sku = row["sku_a"]
        trigger_name = cart_sku_names.get(trigger_sku, trigger_sku)

        lift_val = round(row["lift"], 2) if row["lift"] is not None else 1.0
        support_val = round(row["support"], 4) if row["support"] is not None else None
        confidence_val = round(row["confidence"], 4) if row["confidence"] is not None else None
        final_score = round(lift_val * boost_multiplier, 4)
        reason = f"Frequently bought together with {trigger_name} ({lift_val:.1f}x higher affinity across {row['co_occurrence_count']} orders)."
        tier_priority = 3  # Tier 1 highest

        if boosted:
            reason += " Featured partner recommendation."

        meta_obj = {}
        if row["candidate_metadata"]:
            try:
                meta_obj = json.loads(row["candidate_metadata"])
            except Exception:
                pass

        candidate = {
            "sku": sku_b,
            "name": row["candidate_name"],
            "price_paise": row["candidate_price"],
            "category": row["candidate_category"],
            "image_url": row["candidate_image_url"] or "",
            "description": row["candidate_description"] or "",
            "metadata": meta_obj,
            "source": source,
            "lift": lift_val,
            "support": support_val,
            "confidence": confidence_val,
            "reasoning": row["reasoning"],
            "co_occurrence_count": row["co_occurrence_count"] or 0,
            "final_score": final_score,
            "boosted": boosted,
            "trigger_sku": trigger_sku,
            "trigger_name": trigger_name,
            "reason": reason,
            "_tier_priority": tier_priority
        }

        if sku_b not in candidates_by_sku or candidate["_tier_priority"] > candidates_by_sku[sku_b]["_tier_priority"]:
            candidates_by_sku[sku_b] = candidate

    # ── Tier 2: Layer 2 Co-Purchase Embeddings (item2vec, >= 50 real orders) ─────
    try:
        from backend.recommendations.scalable_engine import find_co_purchase_neighbors
        copurchase_candidates = find_co_purchase_neighbors(
            cart_items,
            exclude_skus=set(candidates_by_sku.keys()),
            top_k=top_k
        )
        for cand in copurchase_candidates:
            cand["_tier_priority"] = 2  # Tier 2 priority
            sku = cand["sku"]
            if sku not in candidates_by_sku or cand["_tier_priority"] > candidates_by_sku[sku]["_tier_priority"]:
                candidates_by_sku[sku] = cand
    except Exception as e:
        print(f"⚠️ Layer 2 co-purchase neighbor lookup skipped: {e}")

    # ── Tier 3: Live Category-Scoped Selection (Category Graph + Dense Embeddings)
    try:
        from backend.recommendations.scalable_engine import find_live_category_candidates
        live_cat_candidates = find_live_category_candidates(
            cart_items,
            exclude_skus=set(candidates_by_sku.keys()),
            top_k=top_k
        )
        for cand in live_cat_candidates:
            cand["_tier_priority"] = 1  # Tier 3 live cold-start priority
            sku = cand["sku"]
            if sku not in candidates_by_sku or cand["_tier_priority"] > candidates_by_sku[sku]["_tier_priority"]:
                candidates_by_sku[sku] = cand
    except Exception as e:
        print(f"⚠️ Live category candidate lookup skipped: {e}")

    # Fetch active policy allowed_categories to guarantee recommended candidates never violate guardrails
    allowed_categories = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT allowed_categories FROM policy_config WHERE id = 1")
        p_row = cursor.fetchone()
        if p_row and p_row["allowed_categories"]:
            allowed_categories = json.loads(p_row["allowed_categories"])
        conn.close()
    except Exception:
        pass

    # Sort candidates by tier priority first (3 -> 2 -> 1), then by final_score (boosted items rise)
    sorted_candidates = sorted(
        candidates_by_sku.values(),
        key=lambda x: (x.get("_tier_priority", 0), x.get("final_score", 0)),
        reverse=True
    )

    # Filter strictly by active merchant policy categories
    if allowed_categories:
        from backend.engine.guardrail import is_category_allowed
        sorted_candidates = [
            cand for cand in sorted_candidates
            if is_category_allowed(cand.get("category", ""), allowed_categories)
        ]

    # Clean up internal sorting helper before returning
    for cand in sorted_candidates:
        cand.pop("_tier_priority", None)

    return sorted_candidates[:top_k]

