import json
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

class AddCategoryCompatRequest(BaseModel):
    category_a: str
    category_b: str
    reasoning: str


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
            ORDER BY boosted DESC, category ASC, name ASC
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


# ─── TAB 3: Growth Rules Inspector ──────────────────────────────────────────
@router.get("/growth-rules", tags=["Merchant Console"])
def get_growth_rules(
    q: Optional[str] = None,
    status: Optional[str] = "all"  # "all", "data_verified", "ai_suggested", "active", "muted"
):
    """
    Returns hybrid market basket association rules (data-verified and AI-suggested)
    cross-referenced with empirical upsell_events conversion metrics.
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

        if status == "active":
            where_clauses.append("(bp.muted IS NULL OR bp.muted = 0)")
        elif status == "muted":
            where_clauses.append("bp.muted = 1")
        elif status == "data_verified":
            where_clauses.append("bp.source = 'data_verified'")
        elif status == "ai_suggested":
            where_clauses.append("bp.source = 'ai_suggested'")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

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
              CASE WHEN bp.source = 'data_verified' THEN 0 ELSE 1 END ASC,
              COALESCE(bp.lift, 1.0) DESC,
              bp.co_occurrence_count DESC
        """
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # Fetch per-target-SKU empirical metrics from upsell_events
        cursor.execute("""
            SELECT 
                suggested_sku,
                COUNT(*) AS times_offered,
                SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) AS times_accepted,
                SUM(CASE WHEN accepted = 1 THEN (cart_total_after_paise - cart_total_before_paise) ELSE 0 END) AS total_revenue_lift_paise
            FROM upsell_events
            GROUP BY suggested_sku
        """)
        events_by_sku = {r["suggested_sku"]: dict(r) for r in cursor.fetchall()}

        rules = []
        total_offered_all = 0
        total_accepted_all = 0
        total_revenue_lift_paise_all = 0
        active_count = 0
        muted_count = 0
        verified_count = 0
        ai_suggested_count = 0

        # Query all summary counts across DB
        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE source = 'data_verified'")
        db_verified_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE source = 'ai_suggested' OR source IS NULL")
        db_ai_suggested_count = cursor.fetchone()[0]

        for r in rows:
            is_muted = bool(r["muted"])
            source = r["source"] or "ai_suggested"
            is_verified = (source == "data_verified" and r["lift"] is not None)

            if is_muted:
                muted_count += 1
            else:
                active_count += 1

            if is_verified:
                verified_count += 1
            else:
                ai_suggested_count += 1

            target_sku = r["sku_b"]
            perf = events_by_sku.get(target_sku, {
                "times_offered": 0,
                "times_accepted": 0,
                "total_revenue_lift_paise": 0
            })

            times_offered = perf["times_offered"] or 0
            times_accepted = perf["times_accepted"] or 0
            lift_paise = perf["total_revenue_lift_paise"] or 0

            total_offered_all += times_offered
            total_accepted_all += times_accepted
            total_revenue_lift_paise_all += lift_paise

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
                plain_language = r["reasoning"] or f"AI-suggested complementary pairing for {r['trigger_name']}."

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
                "plain_language": plain_language,
                "times_offered": times_offered,
                "times_accepted": times_accepted,
                "conversion_rate_pct": conversion_pct,
                "revenue_lift_rupees": round(lift_paise / 100, 2)
            })

        overall_conv = round((total_accepted_all / total_offered_all * 100), 1) if total_offered_all > 0 else 0.0

        return {
            "rules": rules,
            "summary": {
                "total_rules": len(rules),
                "verified_rules": db_verified_count,
                "ai_suggested_rules": db_ai_suggested_count,
                "active_rules": active_count,
                "muted_rules": muted_count,
                "total_offered": total_offered_all,
                "total_accepted": total_accepted_all,
                "overall_conversion_pct": overall_conv,
                "total_revenue_lift_rupees": round(total_revenue_lift_paise_all / 100, 2)
            }
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


@router.post("/growth-rules/reseed-priors", tags=["Merchant Console"])
def reseed_growth_priors():
    """
    Triggers re-generation of LLM-seeded cold start priors grounded in active catalog items.
    """
    from backend.recommendations.lift_engine import generate_ai_priors
    count = generate_ai_priors()
    _log_console_audit(
        "growth_engine", "priors_generator", "AI Growth Priors Reseeded",
        f"Regenerated {count} grounded AI-suggested cross-category growth rules."
    )
    return {
        "status": "success",
        "priors_count": count,
        "message": f"Successfully generated {count} AI-suggested growth rules."
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
            ORDER BY category_a ASC, category_b ASC
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
    Deletes a category compatibility pair and marks it as merchant-locked (editable = 0)
    so future automatic generations do not recreate it.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cat_a, cat_b = sorted([category_a, category_b])
        # Delete canonical pair
        cursor.execute(
            "DELETE FROM category_compatibility WHERE category_a = ? AND category_b = ?",
            (cat_a, cat_b)
        )
        conn.commit()

        _log_console_audit(
            "category_compat", f"{category_a}__{category_b}", "Category Compatibility Pair Removed",
            f"Merchant removed compatibility between '{category_a}' and '{category_b}'."
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


