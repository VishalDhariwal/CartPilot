import json
import math
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query
from backend.db import get_db

router = APIRouter()

# ─── Pydantic Models ────────────────────────────────────────────────────────
class UpdatePolicyRequest(BaseModel):
    spend_cap_paise: int
    allowed_categories: List[str]
    autonomy_threshold_paise: int

class ToggleBoostRequest(BaseModel):
    sku: str
    boosted: bool

class ToggleMuteRuleRequest(BaseModel):
    sku_a: str
    sku_b: str
    muted: bool

class AddGrowthRuleRequest(BaseModel):
    sku_a: str
    sku_b: str
    lift: Optional[float] = 2.5
    reasoning: Optional[str] = "Merchant verified association rule"

class DeleteGrowthRuleRequest(BaseModel):
    sku_a: str
    sku_b: str

class AddCategoryCompatRequest(BaseModel):
    category_a: str
    category_b: str
    reasoning: str

class LivePreviewRequest(BaseModel):
    sku: str
    top_k: int = 3
    weight_association: float = 0.40
    weight_item2vec: float = 0.30
    weight_category: float = 0.20
    weight_revenue: float = 0.10


# ─── Helper: Audit Log Writer ───────────────────────────────────────────────
def _log_console_audit(ref_type: str, ref_id: str, event: str, detail: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        from backend.engine.mandates import create_audit_log
        create_audit_log(cursor, ref_type, ref_id, event, detail)
        conn.commit()
    finally:
        conn.close()


# ─── TAB 1: Policy Control ──────────────────────────────────────────────────
@router.get("/policy", tags=["Merchant Console"])
def get_console_policy():
    """
    Returns the active merchant governance policy along with all distinct catalog categories.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Active policy
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        policy_row = cursor.fetchone()

        spend_cap_paise = policy_row["spend_cap_paise"] if policy_row else 1000000
        autonomy_threshold_paise = policy_row["autonomy_threshold_paise"] if policy_row and policy_row["autonomy_threshold_paise"] else 500000
        allowed_categories = json.loads(policy_row["allowed_categories"]) if policy_row and policy_row["allowed_categories"] else []

        # Distinct categories from live catalog
        cursor.execute("SELECT DISTINCT category FROM catalog WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        available_categories = [r["category"] for r in cursor.fetchall()]

        return {
            "spend_cap_paise": spend_cap_paise,
            "spend_cap_rupees": round(spend_cap_paise / 100, 2),
            "autonomy_threshold_paise": autonomy_threshold_paise,
            "autonomy_threshold_rupees": round(autonomy_threshold_paise / 100, 2),
            "allowed_categories": allowed_categories,
            "available_categories": available_categories
        }
    finally:
        conn.close()


@router.put("/policy", tags=["Merchant Console"])
def update_console_policy(req: UpdatePolicyRequest):
    """
    Updates the spend cap, autonomy threshold, and allowed categories.
    Writes an immutable before/after audit log event.
    """
    if req.spend_cap_paise <= 0:
        raise HTTPException(status_code=400, detail="Spend cap must be greater than zero.")
    if req.autonomy_threshold_paise <= 0:
        raise HTTPException(status_code=400, detail="Autonomy threshold must be greater than zero.")
    if not req.allowed_categories:
        raise HTTPException(status_code=400, detail="At least one category must be allowed.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch previous state for audit diff
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        old_row = cursor.fetchone()
        old_cap = old_row["spend_cap_paise"] if old_row else 1000000
        old_aut = old_row["autonomy_threshold_paise"] if old_row and old_row["autonomy_threshold_paise"] else 500000
        old_cats = json.loads(old_row["allowed_categories"]) if old_row and old_row["allowed_categories"] else []

        # Update policy
        cursor.execute(
            """
            UPDATE policy_config 
            SET spend_cap_paise = ?, allowed_categories = ?, autonomy_threshold_paise = ?
            WHERE id = 1
            """,
            (req.spend_cap_paise, json.dumps(req.allowed_categories), req.autonomy_threshold_paise)
        )
        conn.commit()

        # Write audit trail
        diff_detail = (
            f"Spend Cap: ₹{old_cap/100:.0f} → ₹{req.spend_cap_paise/100:.0f} | "
            f"Autonomy Threshold: ₹{old_aut/100:.0f} → ₹{req.autonomy_threshold_paise/100:.0f} | "
            f"Allowed Categories: {len(old_cats)} → {len(req.allowed_categories)} selected."
        )
        _log_console_audit("policy", "config_1", "Policy Configuration Updated", diff_detail)

        return {
            "status": "success",
            "message": "Merchant policy updated successfully.",
            "spend_cap_paise": req.spend_cap_paise,
            "autonomy_threshold_paise": req.autonomy_threshold_paise,
            "allowed_categories": req.allowed_categories
        }
    finally:
        conn.close()


# ─── TAB 2: Catalog & Promotions ────────────────────────────────────────────
@router.get("/catalog", tags=["Merchant Console"])
def list_console_catalog(
    q: Optional[str] = None,
    category: Optional[str] = None,
    boosted_only: Optional[bool] = False,
    page: int = 1,
    limit: int = 50
):
    """
    Returns filterable catalog items with boost levers and summary stats.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []

        if q and q.strip():
            search_term = f"%{q.strip()}%"
            where_clauses.append("(name LIKE ? OR sku LIKE ? OR description LIKE ?)")
            params.extend([search_term, search_term, search_term])

        if category and category != "all":
            where_clauses.append("category = ?")
            params.append(category)

        if boosted_only:
            where_clauses.append("boosted = 1")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total count for pagination
        cursor.execute(f"SELECT COUNT(*) FROM catalog {where_sql}", params)
        total_filtered = cursor.fetchone()[0]

        # Overall summary stats
        cursor.execute("SELECT COUNT(*) FROM catalog")
        total_items = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM catalog WHERE boosted = 1")
        boosted_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM catalog WHERE stock <= 0")
        oos_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT category) FROM catalog")
        categories_count = cursor.fetchone()[0]

        offset = (max(1, page) - 1) * limit
        query_sql = f"""
            SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description
            FROM catalog
            {where_sql}
            ORDER BY boosted DESC, rowid DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query_sql, params + [limit, offset])
        rows = cursor.fetchall()

        items = [
            {
                "sku": r["sku"],
                "name": r["name"],
                "price_paise": r["price_paise"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "stock": r["stock"],
                "category": r["category"],
                "merchant": r["merchant"],
                "boosted": bool(r["boosted"]),
                "image_url": r["image_url"] or "",
                "description": r["description"] or ""
            }
            for r in rows
        ]

        return {
            "items": items,
            "total": total_filtered,
            "page": page,
            "limit": limit,
            "has_more": (offset + limit) < total_filtered,
            "summary": {
                "total_items": total_items,
                "boosted_items": boosted_count,
                "out_of_stock_items": oos_count,
                "categories_count": categories_count
            }
        }
    finally:
        conn.close()


@router.post("/catalog/boost", tags=["Merchant Console"])
def toggle_item_boost(req: ToggleBoostRequest):
    """
    Toggles the boosted promotion flag for a SKU.
    Simulates and returns a live rank-uplift preview and writes an audit log entry.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT sku, name, price_paise, category, boosted FROM catalog WHERE sku = ?", (req.sku,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"SKU {req.sku} not found.")

        item_name = row["name"]
        new_boost = 1 if req.boosted else 0

        cursor.execute("UPDATE catalog SET boosted = ? WHERE sku = ?", (new_boost, req.sku))
        conn.commit()

        # Simulate rank preview in basket_pairs cross-sell
        cursor.execute(
            """
            SELECT bp.sku_a, bp.lift, c.name AS trigger_name 
            FROM basket_pairs bp
            JOIN catalog c ON c.sku = bp.sku_a
            WHERE bp.sku_b = ? AND (bp.muted IS NULL OR bp.muted = 0)
            ORDER BY bp.lift DESC LIMIT 1
            """,
            (req.sku,)
        )
        sample_pair = cursor.fetchone()

        if sample_pair:
            trigger_name = sample_pair["trigger_name"]
            raw_lift = sample_pair["lift"]
            boosted_lift = round(raw_lift * 1.35, 2)
            if req.boosted:
                rank_preview = f"Boost activated: Cross-sell score for '{item_name}' when buying '{trigger_name}' increased from {raw_lift:.2f} → {boosted_lift:.2f} (1.35x rank uplift applied)."
            else:
                rank_preview = f"Boost removed: Cross-sell score for '{item_name}' when buying '{trigger_name}' restored to natural baseline ({raw_lift:.2f})."
        else:
            if req.boosted:
                rank_preview = f"Boost activated: 1.35x priority multiplier applied to '{item_name}' across semantic substitution and discovery carousels."
            else:
                rank_preview = f"Boost removed: '{item_name}' restored to standard ranking."

        # Write audit trail
        _log_console_audit(
            "catalog",
            req.sku,
            "Promotion Boost Toggled",
            f"SKU {req.sku} ('{item_name}') boosted flag set to {req.boosted}. {rank_preview}"
        )

        return {
            "status": "success",
            "sku": req.sku,
            "name": item_name,
            "boosted": req.boosted,
            "rank_preview": rank_preview
        }
    finally:
        conn.close()


# ─── TAB 3: Growth Rules Inspector & Live Recommendation Sandbox ────────────
@router.get("/growth-rules", tags=["Merchant Console"])
def get_growth_rules(
    q: Optional[str] = None,
    status: Optional[str] = "all",  # "all", "data_verified", "retired", "active", "muted"
    page: int = 1,
    limit: int = 50
):
    """
    Returns market basket association rules with server-side pagination.
    - Active view: Only data-verified empirical rules (retired = 0, source = 'data_verified')
    - Retired view: Legacy static per-SKU priors (retired = 1) kept for audit history.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []

        if q and q.strip():
            search_term = f"%{q.strip()}%"
            where_clauses.append("(c_a.name LIKE ? OR c_b.name LIKE ? OR bp.sku_a LIKE ? OR bp.sku_b LIKE ? OR bp.reasoning LIKE ?)")
            params.extend([search_term, search_term, search_term, search_term, search_term])

        if status == "retired":
            where_clauses.append("(bp.retired = 1 OR bp.source = 'ai_suggested')")
        elif status == "muted":
            where_clauses.append("bp.muted = 1 AND (bp.retired IS NULL OR bp.retired = 0)")
        elif status == "data_verified":
            where_clauses.append("(bp.retired IS NULL OR bp.retired = 0) AND (bp.source = 'data_verified' OR (bp.co_occurrence_count >= 2 AND bp.lift >= 1.1))")
        else:  # "all" or "active"
            where_clauses.append("(bp.retired IS NULL OR bp.retired = 0) AND (bp.source = 'data_verified' OR (bp.co_occurrence_count >= 2 AND bp.lift >= 1.1))")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total count for server-side pagination
        count_sql = f"""
            SELECT COUNT(*)
            FROM basket_pairs bp
            JOIN catalog c_a ON c_a.sku = bp.sku_a
            JOIN catalog c_b ON c_b.sku = bp.sku_b
            {where_sql}
        """
        cursor.execute(count_sql, params)
        total_filtered_rules = cursor.fetchone()[0]

        # Auto-mine if zero data_verified rules found
        if total_filtered_rules == 0:
            from backend.recommendations.lift_engine import compute_lift_pairs
            compute_lift_pairs(min_co_occurrence=2, min_lift=1.1)
            cursor.execute(count_sql, params)
            total_filtered_rules = cursor.fetchone()[0]

        offset = (max(1, page) - 1) * limit

        sql = f"""
            SELECT 
                bp.sku_a,
                bp.sku_b,
                bp.lift,
                bp.support,
                bp.confidence,
                COALESCE(bp.source, 'ai_suggested') AS source,
                bp.reasoning,
                COALESCE(bp.co_occurrence_count, 0) AS co_occurrence_count,
                COALESCE(bp.muted, 0) AS muted,
                COALESCE(bp.retired, 0) AS retired,
                bp.computed_at,
                c_a.name AS trigger_name,
                c_a.category AS trigger_category,
                c_a.price_paise AS trigger_price,
                c_a.image_url AS trigger_image,
                c_b.name AS target_name,
                c_b.category AS target_category,
                c_b.price_paise AS target_price,
                c_b.image_url AS target_image,
                c_b.boosted AS target_boosted
            FROM basket_pairs bp
            JOIN catalog c_a ON c_a.sku = bp.sku_a
            JOIN catalog c_b ON c_b.sku = bp.sku_b
            {where_sql}
            ORDER BY 
              bp.muted ASC,
              bp.computed_at DESC,
              COALESCE(bp.lift, 1.0) DESC,
              bp.co_occurrence_count DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(sql, params + [limit, offset])
        rows = cursor.fetchall()

        # Fetch per-target-SKU empirical metrics from upsell_events (excluding refunded/cancelled orders)
        cursor.execute("""
            SELECT 
                u.suggested_sku,
                COUNT(*) AS times_offered,
                SUM(CASE WHEN u.accepted = 1 THEN 1 ELSE 0 END) AS times_accepted,
                SUM(CASE WHEN u.accepted = 1 
                         AND COALESCE(pm.status, '') = 'succeeded'
                         AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
                         AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
                         THEN (u.cart_total_after_paise - u.cart_total_before_paise) ELSE 0 END) AS total_revenue_lift_paise
            FROM upsell_events u
            LEFT JOIN cart_mandates cm ON u.cart_id = cm.id
            LEFT JOIN payment_mandates pm ON u.cart_id = pm.cart_id
            GROUP BY u.suggested_sku
        """)
        events_by_sku = {r["suggested_sku"]: dict(r) for r in cursor.fetchall()}

        # Global totals across all upsell events (excluding refunded/cancelled orders)
        cursor.execute("""
            SELECT 
                COUNT(*) AS total_offered,
                SUM(CASE WHEN u.accepted = 1 THEN 1 ELSE 0 END) AS total_accepted,
                SUM(CASE WHEN u.accepted = 1 
                         AND COALESCE(pm.status, '') = 'succeeded'
                         AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
                         AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
                         THEN (u.cart_total_after_paise - u.cart_total_before_paise) ELSE 0 END) AS total_revenue_lift_paise
            FROM upsell_events u
            LEFT JOIN cart_mandates cm ON u.cart_id = cm.id
            LEFT JOIN payment_mandates pm ON u.cart_id = pm.cart_id
        """)
        global_summary = cursor.fetchone()
        total_offered_all = global_summary["total_offered"] or 0
        total_accepted_all = global_summary["total_accepted"] or 0
        total_revenue_lift_paise_all = global_summary["total_revenue_lift_paise"] or 0

        rules = []
        active_count = 0
        muted_count = 0

        # Query all summary counts across DB
        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE source = 'data_verified' AND (retired IS NULL OR retired = 0) AND co_occurrence_count >= 8 AND lift > 1.2")
        db_verified_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE retired = 1 OR source = 'ai_suggested'")
        db_retired_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM category_compatibility")
        db_category_compat_count = cursor.fetchone()[0]

        # Total active live rules = verified empirical rules + category compatibility graph pairs
        total_active_live_rules = db_verified_count + db_category_compat_count

        for r in rows:
            is_muted = bool(r["muted"])
            is_retired = bool(r["retired"])
            source = r["source"] or "ai_suggested"
            is_verified = (source == "data_verified" and r["lift"] is not None)

            if is_muted:
                muted_count += 1
            elif not is_retired:
                active_count += 1

            target_sku = r["sku_b"]
            perf = events_by_sku.get(target_sku, {
                "times_offered": 0,
                "times_accepted": 0,
                "total_revenue_lift_paise": 0
            })

            times_offered = perf["times_offered"] or 0
            times_accepted = perf["times_accepted"] or 0
            lift_paise = perf["total_revenue_lift_paise"] or 0

            conversion_pct = round((times_accepted / times_offered * 100), 1) if times_offered > 0 else 0.0
            co_occurrence = r["co_occurrence_count"] or 0

            if is_verified:
                lift_val = round(r["lift"], 2)
                support_val = round(r["support"], 4) if r["support"] is not None else 0.0
                confidence_val = round(r["confidence"], 2) if r["confidence"] is not None else min(0.99, round(support_val * lift_val, 2))
                plain_language = (
                    f"Customers who buy {r['trigger_name']} are {lift_val:.2f}x more likely "
                    f"to also buy {r['target_name']} than random chance."
                )
            else:
                lift_val = None
                support_val = None
                confidence_val = None
                plain_language = r["reasoning"] or f"Legacy AI prior (Retired): {r['trigger_name']} → {r['target_name']}."

            rules.append({
                "rule_id": f"{r['sku_a']}__{r['sku_b']}",
                "sku_a": r["sku_a"],
                "sku_b": r["sku_b"],
                "trigger_name": r["trigger_name"],
                "trigger_category": r["trigger_category"],
                "trigger_price_rupees": round(r["trigger_price"] / 100, 2),
                "trigger_image": r["trigger_image"] or "",
                "target_name": r["target_name"],
                "target_category": r["target_category"],
                "target_price_rupees": round(r["target_price"] / 100, 2),
                "target_image": r["target_image"] or "",
                "target_boosted": bool(r["target_boosted"]),
                "source": source,
                "reasoning": r["reasoning"] or "",
                "co_occurrence_count": co_occurrence,
                "verification_threshold": 8,
                "lift": lift_val,
                "support": support_val,
                "confidence": confidence_val,
                "muted": is_muted,
                "retired": is_retired,
                "plain_language": plain_language,
                "times_offered": times_offered,
                "times_accepted": times_accepted,
                "conversion_rate_pct": conversion_pct,
                "revenue_lift_rupees": round(lift_paise / 100, 2)
            })

        # Query total customer shopping orders vs total accepted recommendations
        cursor.execute("SELECT COUNT(*) FROM intent_mandates")
        total_customer_orders = cursor.fetchone()[0] or 1

        overall_conv = round((total_accepted_all / total_customer_orders * 100), 1)

        return {
            "rules": rules,
            "total": total_filtered_rules,
            "page": page,
            "limit": limit,
            "has_more": (offset + limit) < total_filtered_rules,
            "summary": {
                "total_rules": total_filtered_rules,
                "active_rules": total_active_live_rules,
                "verified_rules": db_verified_count,
                "category_compat_rules": db_category_compat_count,
                "retired_priors": db_retired_count,
                "muted_rules": muted_count,
                "total_orders": total_customer_orders,
                "total_accepted": total_accepted_all,
                "total_offered": total_offered_all,
                "overall_conversion_pct": overall_conv,
                "total_revenue_lift_rupees": round(total_revenue_lift_paise_all / 100, 2)
            }
        }
    finally:
        conn.close()


@router.post("/growth-rules/live-preview", tags=["Merchant Console"])
def preview_live_recommendations(req: LivePreviewRequest):
    """
    Live Multi-Engine Recommendation Reranker Sandbox.
    Collects top-5 candidates across 3 distinct engines:
      1. Engine 1: Association Rules (basket_pairs)
      2. Engine 2: Item2Vec Neural Vector Embeddings
      3. Engine 3: Category Compatibility Graph & Semantic Matching
    Fuses multi-engine signals, applies merchant configurable weights (Association, Item2Vec, Category, Revenue),
    reranks the pooled candidates, and returns top_k results with complete score attribution.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT sku, name, category, price_paise, image_url, description, metadata, boosted, embedding FROM catalog WHERE sku = ?",
            (req.sku,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"SKU '{req.sku}' not found in catalog.")

        trigger_item = dict(row)
        trigger_sku = trigger_item["sku"]
        trigger_category = trigger_item["category"]

        # Fetch category compatibility connections for this category
        cursor.execute(
            """
            SELECT category_b AS compat_cat, reasoning, editable
            FROM category_compatibility
            WHERE category_a = ?
            UNION
            SELECT category_a AS compat_cat, reasoning, editable
            FROM category_compatibility
            WHERE category_b = ?
            """,
            (trigger_category, trigger_category)
        )
        compat_paths = [
            {
                "compatible_category": r["compat_cat"],
                "reasoning": r["reasoning"],
                "editable": bool(r["editable"])
            }
            for r in cursor.fetchall()
        ]

        # ── 1. Engine 1: Association Rules (basket_pairs) - Top 5 ──
        cursor.execute(
            """
            SELECT 
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
                c.description AS candidate_description
            FROM basket_pairs bp
            JOIN catalog c ON c.sku = bp.sku_b
            WHERE bp.sku_a = ?
              AND c.stock > 0
              AND bp.sku_b != ?
              AND (bp.muted IS NULL OR bp.muted = 0)
              AND (bp.retired IS NULL OR bp.retired = 0)
            ORDER BY bp.lift DESC, bp.co_occurrence_count DESC
            LIMIT 5
            """,
            (trigger_sku, trigger_sku)
        )
        assoc_rows = cursor.fetchall()

        # ── 2. Engine 2: Item2Vec Neural Embeddings - Top 5 ──
        from backend.recommendations.scalable_engine import find_co_purchase_neighbors
        try:
            item2vec_candidates = find_co_purchase_neighbors([trigger_item], exclude_skus={trigger_sku}, top_k=5)
        except Exception as e:
            print(f"⚠️ Item2Vec lookup fallback: {e}")
            item2vec_candidates = []

        # ── 3. Engine 3: Category Graph & Semantic Matching - Top 5 ──
        from backend.recommendations.scalable_engine import find_live_category_candidates
        try:
            category_candidates = find_live_category_candidates([trigger_item], exclude_skus={trigger_sku}, top_k=5)
        except Exception as e:
            print(f"⚠️ Category candidates fallback: {e}")
            category_candidates = []

        # ── Pool & Multi-Signal Fusion ──
        candidate_pool = {}

        # Ingest Engine 1
        for r in assoc_rows:
            sku = r["sku_b"]
            lift_val = float(r["lift"]) if r["lift"] is not None else 1.0
            # Normalized association score between 0.2 and 1.0 based on lift
            assoc_score = min(max((lift_val - 1.0) / 3.0, 0.2), 1.0)
            candidate_pool[sku] = {
                "sku": sku,
                "name": r["candidate_name"],
                "price_paise": r["candidate_price"],
                "category": r["candidate_category"],
                "image_url": r["candidate_image_url"] or "",
                "description": r["candidate_description"] or "",
                "boosted": bool(r["candidate_boosted"]),
                "signals": {
                    "association": assoc_score,
                    "item2vec": 0.0,
                    "category": 0.0,
                    "revenue": 0.0,
                },
                "engines": ["Association Rules"],
                "raw_reasons": [f"Frequently bought together with {trigger_item['name']} ({lift_val:.1f}x lift)."],
                "lift": lift_val,
                "co_occurrence_count": r["co_occurrence_count"] or 0,
            }

        # Ingest Engine 2
        for cand in item2vec_candidates:
            sku = cand["sku"]
            sim_score = float(cand.get("cosine_similarity", 0.75))
            if sku not in candidate_pool:
                candidate_pool[sku] = {
                    "sku": sku,
                    "name": cand.get("name", sku),
                    "price_paise": cand.get("price_paise", 0),
                    "category": cand.get("category", ""),
                    "image_url": cand.get("image_url", ""),
                    "description": cand.get("description", ""),
                    "boosted": bool(cand.get("boosted", False)),
                    "signals": {
                        "association": 0.0,
                        "item2vec": sim_score,
                        "category": 0.0,
                        "revenue": 0.0,
                    },
                    "engines": ["Item2Vec Vectors"],
                    "raw_reasons": [cand.get("reason", "Neural basket embedding match.")],
                    "lift": None,
                    "co_occurrence_count": cand.get("co_occurrence_count", 0),
                }
            else:
                candidate_pool[sku]["signals"]["item2vec"] = sim_score
                if "Item2Vec Vectors" not in candidate_pool[sku]["engines"]:
                    candidate_pool[sku]["engines"].append("Item2Vec Vectors")
                candidate_pool[sku]["raw_reasons"].append(cand.get("reason", "Neural vector match."))

        # Ingest Engine 3
        for cand in category_candidates:
            sku = cand["sku"]
            cat_score = float(cand.get("semantic_similarity", 0.80)) if "semantic_similarity" in cand else 0.85
            if sku not in candidate_pool:
                candidate_pool[sku] = {
                    "sku": sku,
                    "name": cand.get("name", sku),
                    "price_paise": cand.get("price_paise", 0),
                    "category": cand.get("category", ""),
                    "image_url": cand.get("image_url", ""),
                    "description": cand.get("description", ""),
                    "boosted": bool(cand.get("boosted", False)),
                    "signals": {
                        "association": 0.0,
                        "item2vec": 0.0,
                        "category": cat_score,
                        "revenue": 0.0,
                    },
                    "engines": ["Category Graph"],
                    "raw_reasons": [cand.get("reason", f"Complementary {cand.get('category', '')} match.")],
                    "lift": None,
                    "co_occurrence_count": 0,
                }
            else:
                candidate_pool[sku]["signals"]["category"] = cat_score
                if "Category Graph" not in candidate_pool[sku]["engines"]:
                    candidate_pool[sku]["engines"].append("Category Graph")
                candidate_pool[sku]["raw_reasons"].append(cand.get("reason", "Category compatibility match."))

        # Normalize merchant weights so total weight = 1.0
        total_w = req.weight_association + req.weight_item2vec + req.weight_category + req.weight_revenue
        if total_w <= 0:
            total_w = 1.0
        w_assoc = req.weight_association / total_w
        w_vec = req.weight_item2vec / total_w
        w_cat = req.weight_category / total_w
        w_rev = req.weight_revenue / total_w

        trigger_price = float(trigger_item["price_paise"] or 1000)

        # Score & Rerank all pooled candidates
        scored_candidates = []
        for cand in candidate_pool.values():
            # Revenue score based on ideal complementary basket ratio (0.2x - 3.0x trigger price)
            cand_price = float(cand["price_paise"] or 1000)
            ratio = cand_price / trigger_price if trigger_price > 0 else 1.0

            if 0.2 <= ratio <= 3.5:
                rev_score = min(0.6 + (ratio / 7.0), 1.0)
            elif ratio < 0.2:
                rev_score = max((ratio / 0.2) * 0.6, 0.1)
            else:
                rev_score = max(1.0 - (math.log10(ratio) * 0.4), 0.1)

            cand["signals"]["revenue"] = rev_score

            # Composite weighted calculation
            s_assoc = cand["signals"]["association"]
            s_vec = cand["signals"]["item2vec"]
            s_cat = cand["signals"]["category"]
            s_rev = cand["signals"]["revenue"]

            raw_composite = (
                (w_assoc * s_assoc) +
                (w_vec * s_vec) +
                (w_cat * s_cat) +
                (w_rev * s_rev)
            )

            # Boost multiplier if featured partner
            boost_mul = 1.25 if cand["boosted"] else 1.0
            final_composite = min(raw_composite * boost_mul, 1.0)
            score_points = round(final_composite * 100, 1)

            # Build readable summary rationale
            combined_reason = " · ".join(cand["raw_reasons"][:2])

            scored_candidates.append({
                "sku": cand["sku"],
                "name": cand["name"],
                "category": cand["category"],
                "price_paise": cand["price_paise"],
                "price_rupees": round(cand["price_paise"] / 100, 2),
                "image_url": cand["image_url"],
                "description": cand["description"],
                "boosted": cand["boosted"],
                "composite_score": score_points,
                "engines": cand["engines"],
                "score_breakdown": {
                    "association": round(s_assoc * 100, 1),
                    "item2vec": round(s_vec * 100, 1),
                    "category": round(s_cat * 100, 1),
                    "revenue": round(s_rev * 100, 1),
                },
                "lift": cand["lift"],
                "reason": combined_reason,
                "multi_engine_match": len(cand["engines"]) > 1,
            })

        # Sort by composite score descending
        scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)

        # Apply policy allowed_categories guardrails
        cursor.execute("SELECT allowed_categories FROM policy_config WHERE id = 1")
        p_row = cursor.fetchone()
        if p_row and p_row["allowed_categories"]:
            try:
                allowed_cats = json.loads(p_row["allowed_categories"])
                if allowed_cats:
                    from backend.engine.guardrail import is_category_allowed
                    scored_candidates = [
                        c for c in scored_candidates
                        if is_category_allowed(c.get("category", ""), allowed_cats)
                    ]
            except Exception:
                pass

        top_candidates = scored_candidates[:req.top_k]

        return {
            "trigger_sku": trigger_item["sku"],
            "trigger_name": trigger_item["name"],
            "trigger_category": trigger_category,
            "trigger_price_rupees": round(trigger_item["price_paise"] / 100, 2),
            "trigger_image": trigger_item["image_url"] or "",
            "compatible_categories": compat_paths,
            "candidates": top_candidates,
            "pool_size": len(candidate_pool),
            "weights_applied": {
                "association": round(w_assoc * 100, 0),
                "item2vec": round(w_vec * 100, 0),
                "category": round(w_cat * 100, 0),
                "revenue": round(w_rev * 100, 0),
            },
            "computed_at": datetime.utcnow().isoformat() + "Z",
            "is_live_computed": True
        }
    finally:
        conn.close()


@router.post("/growth-rules/mute", tags=["Merchant Console"])
def toggle_mute_growth_rule(req: ToggleMuteRuleRequest):
    """
    Mutes or unmutes a specific growth association rule.
    Muted rules are instantly excluded from buyer agent recommendations without restarting the server.
    Writes an audit log entry.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch rule details for readable audit log
        cursor.execute(
            """
            SELECT bp.lift, bp.source, bp.reasoning, c_a.name AS trigger_name, c_b.name AS target_name
            FROM basket_pairs bp
            JOIN catalog c_a ON c_a.sku = bp.sku_a
            JOIN catalog c_b ON c_b.sku = bp.sku_b
            WHERE bp.sku_a = ? AND bp.sku_b = ?
            """,
            (req.sku_a, req.sku_b)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Association rule not found.")

        trigger_name = row["trigger_name"]
        target_name = row["target_name"]
        source_type = row["source"] or "ai_suggested"
        lift_val = row["lift"]

        new_muted = 1 if req.muted else 0
        cursor.execute(
            "UPDATE basket_pairs SET muted = ? WHERE sku_a = ? AND sku_b = ?",
            (new_muted, req.sku_a, req.sku_b)
        )
        conn.commit()

        action_word = "Muted" if req.muted else "Unmuted"
        stat_desc = f"(Lift: {lift_val:.2f}x)" if lift_val else "(AI-suggested prior)"
        detail = (
            f"Growth Rule '{trigger_name}' → '{target_name}' {stat_desc} {action_word}. "
            f"{'Immediately excluded from cross-sell recommendation candidates.' if req.muted else 'Restored to active recommendation engine.'}"
        )
        _log_console_audit("growth_rule", f"{req.sku_a}__{req.sku_b}", f"Growth Rule {action_word}", detail)

        return {
            "status": "success",
            "rule_id": f"{req.sku_a}__{req.sku_b}",
            "trigger_name": trigger_name,
            "target_name": target_name,
            "muted": req.muted,
            "message": detail
        }
    finally:
        conn.close()


@router.post("/growth-rules/add", tags=["Merchant Console"])
@router.post("/growth-rules", tags=["Merchant Console"])
def add_growth_rule(req: AddGrowthRuleRequest):
    """
    Creates or updates a custom verified association rule between two products.
    """
    if req.sku_a == req.sku_b:
        raise HTTPException(status_code=400, detail="Antecedent and Consequent products must be different.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Validate that both SKUs exist in catalog
        cursor.execute("SELECT sku, name FROM catalog WHERE sku IN (?, ?)", (req.sku_a, req.sku_b))
        skus_found = {r["sku"]: r["name"] for r in cursor.fetchall()}
        if req.sku_a not in skus_found:
            raise HTTPException(status_code=404, detail=f"Trigger product SKU '{req.sku_a}' not found in catalog.")
        if req.sku_b not in skus_found:
            raise HTTPException(status_code=404, detail=f"Target product SKU '{req.sku_b}' not found in catalog.")

        now_iso = datetime.utcnow().isoformat() + "Z"
        lift_val = float(req.lift) if req.lift else 2.5
        reason = req.reasoning or f"Merchant verified recommendation rule: {skus_found[req.sku_a]} → {skus_found[req.sku_b]}"

        cursor.execute(
            """
            INSERT INTO basket_pairs 
            (sku_a, sku_b, lift, support, confidence, source, reasoning, co_occurrence_count, computed_at, muted, retired)
            VALUES (?, ?, ?, 0.05, 0.85, 'data_verified', ?, 10, ?, 0, 0)
            ON CONFLICT(sku_a, sku_b) DO UPDATE SET
                lift = excluded.lift,
                source = 'data_verified',
                reasoning = excluded.reasoning,
                co_occurrence_count = 10,
                retired = 0,
                muted = 0,
                computed_at = excluded.computed_at
            """,
            (req.sku_a, req.sku_b, lift_val, reason, now_iso)
        )
        conn.commit()

        detail = f"Added custom verified association rule: {skus_found[req.sku_a]} ({req.sku_a}) → {skus_found[req.sku_b]} ({req.sku_b}) with {lift_val:.1f}x Lift."
        _log_console_audit("growth_rule", f"{req.sku_a}__{req.sku_b}", "Growth Rule Added", detail)

        return {
            "status": "success",
            "rule_id": f"{req.sku_a}__{req.sku_b}",
            "sku_a": req.sku_a,
            "sku_b": req.sku_b,
            "trigger_name": skus_found[req.sku_a],
            "target_name": skus_found[req.sku_b],
            "lift": lift_val,
            "message": detail
        }
    finally:
        conn.close()


@router.post("/growth-rules/delete", tags=["Merchant Console"])
@router.delete("/growth-rules", tags=["Merchant Console"])
def delete_growth_rule(req: DeleteGrowthRuleRequest):
    """
    Deletes or retires a specific growth association rule.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT c_a.name AS trigger_name, c_b.name AS target_name
            FROM basket_pairs bp
            JOIN catalog c_a ON c_a.sku = bp.sku_a
            JOIN catalog c_b ON c_b.sku = bp.sku_b
            WHERE bp.sku_a = ? AND bp.sku_b = ?
            """,
            (req.sku_a, req.sku_b)
        )
        row = cursor.fetchone()
        trigger_name = row["trigger_name"] if row else req.sku_a
        target_name = row["target_name"] if row else req.sku_b

        cursor.execute(
            "DELETE FROM basket_pairs WHERE sku_a = ? AND sku_b = ?",
            (req.sku_a, req.sku_b)
        )
        conn.commit()

        detail = f"Deleted association rule: '{trigger_name}' → '{target_name}'."
        _log_console_audit("growth_rule", f"{req.sku_a}__{req.sku_b}", "Growth Rule Deleted", detail)

        return {
            "status": "success",
            "rule_id": f"{req.sku_a}__{req.sku_b}",
            "message": detail
        }
    finally:
        conn.close()


@router.post("/growth-rules/reseed-priors", tags=["Merchant Console"])
def reseed_growth_priors():
    """
    Regenerates the category compatibility graph and re-mines empirical lift pairs.
    """
    from backend.recommendations.scalable_engine import generate_category_compatibility
    from backend.recommendations.lift_engine import compute_lift_pairs
    res = generate_category_compatibility()
    mined_count = compute_lift_pairs(min_co_occurrence=2, min_lift=1.1)
    _log_console_audit(
        "growth_engine", "growth_rules", "Statistical Rules Mined",
        f"Mined {mined_count} empirical association rules and {res.get('inserted', 0)} category compatibility pairs."
    )
    return {
        "status": "success",
        "mined_rules_count": mined_count,
        "category_pairs_count": res.get("inserted", 0),
        "message": f"Successfully mined {mined_count} empirical association rules and updated {res.get('inserted', 0)} category pairs."
    }


# ─── Scalable Architecture: Category Compatibility Endpoints ────────────────

@router.get("/category-compat", tags=["Merchant Console"])
def get_category_compatibility():
    """
    Returns all category compatibility graph pairs and distinct categories.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT category_a, category_b, reasoning, editable, created_at
            FROM category_compatibility
            ORDER BY created_at DESC
            """
        )
        pairs = [
            {
                "category_a": r["category_a"],
                "category_b": r["category_b"],
                "reasoning": r["reasoning"],
                "editable": bool(r["editable"]),
                "created_at": r["created_at"]
            }
            for r in cursor.fetchall()
        ]

        cursor.execute("SELECT DISTINCT category FROM catalog WHERE category IS NOT NULL AND stock > 0 ORDER BY category")
        categories = [r["category"] for r in cursor.fetchall()]

        return {
            "pairs": pairs,
            "total_pairs": len(pairs),
            "categories": categories
        }
    finally:
        conn.close()


@router.post("/category-compat/generate", tags=["Merchant Console"])
def generate_category_compat_graph():
    """
    Triggers LLM generation of the category compatibility graph.
    Preserves all merchant-locked rows (editable = 0).
    """
    from backend.recommendations.scalable_engine import generate_category_compatibility
    res = generate_category_compatibility()
    _log_console_audit(
        "growth_engine", "category_compat", "Category Compatibility Graph Generated",
        f"Generated {res['inserted']} compatibility pairs across {res['total_categories']} categories ({res['skipped_locked']} merchant-locked preserved)."
    )
    return {
        "status": "success",
        **res,
        "message": f"Category compatibility graph updated with {res['inserted']} pairs."
    }


@router.delete("/category-compat/{category_a}/{category_b}", tags=["Merchant Console"])
def delete_category_compat_pair(category_a: str, category_b: str):
    """
    Deletes a category compatibility pair (in both directions) and records audit log.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Delete both directions to ensure bidirectional cleanup
        cursor.execute(
            """
            DELETE FROM category_compatibility 
            WHERE (category_a = ? AND category_b = ?) 
               OR (category_a = ? AND category_b = ?)
            """,
            (category_a, category_b, category_b, category_a)
        )
        deleted_count = cursor.rowcount
        conn.commit()

        _log_console_audit(
            "category_compat", f"{category_a}__{category_b}", "Category Compatibility Pair Removed",
            f"Merchant removed compatibility between '{category_a}' and '{category_b}' ({deleted_count} record(s) deleted)."
        )
        return {
            "status": "success",
            "message": f"Compatibility between '{category_a}' and '{category_b}' removed."
        }
    finally:
        conn.close()


@router.post("/category-compat/add", tags=["Merchant Console"])
def add_category_compat_pair(req: AddCategoryCompatRequest):
    """
    Adds a merchant-defined category compatibility pair with editable = 0 (merchant-locked).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        # Insert canonical direction with editable = 0
        cat_a, cat_b = sorted([req.category_a, req.category_b])
        cursor.execute(
            """
            INSERT INTO category_compatibility (category_a, category_b, reasoning, editable, created_at)
            VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(category_a, category_b) DO UPDATE SET
                reasoning = excluded.reasoning,
                editable = 0,
                created_at = excluded.created_at
            """,
            (cat_a, cat_b, req.reasoning.strip(), now_iso)
        )
        conn.commit()

        _log_console_audit(
            "category_compat", f"{req.category_a}__{req.category_b}", "Category Compatibility Pair Added",
            f"Merchant manually added compatibility between '{req.category_a}' and '{req.category_b}': '{req.reasoning}'."
        )
        return {
            "status": "success",
            "message": f"Compatibility between '{req.category_a}' and '{req.category_b}' added and locked."
        }
    finally:
        conn.close()


# ─── Scalable Architecture: Embedding Training Endpoints ─────────────────────

@router.get("/embeddings/status", tags=["Merchant Console"])
def get_embeddings_status():
    """
    Returns the current training status of Layer 2 co-purchase embeddings.
    """
    from backend.recommendations.scalable_engine import get_embedding_status
    return get_embedding_status()


@router.post("/embeddings/train", tags=["Merchant Console"])
def trigger_train_embeddings():
    """
    Triggers Layer 2 co-purchase embeddings training over historical real completed orders.
    """
    from backend.recommendations.scalable_engine import train_co_purchase_embeddings
    res = train_co_purchase_embeddings(min_orders=50)
    if res["status"] == "insufficient_data":
        return {
            "status": "insufficient_data",
            "message": f"Insufficient real order data: {res['real_order_count']} orders found, need at least {res['min_orders']} real orders to train item2vec.",
            "real_order_count": res["real_order_count"],
            "min_orders": res["min_orders"]
        }

    _log_console_audit(
        "growth_engine", "item2vec", "Co-Purchase Embeddings Trained",
        f"Trained item2vec model over {res['real_order_count']} real orders. Updated embeddings for {res['skus_updated']} SKUs."
    )
    return {
        "status": "success",
        **res,
        "message": f"Successfully trained co-purchase embeddings for {res['skus_updated']} catalog SKUs over {res['real_order_count']} real orders."
    }


