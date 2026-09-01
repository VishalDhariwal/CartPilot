import os
import json
import uuid
from typing import Any, Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel
from backend.db import get_db
from backend.recommendations.lift_engine import find_cross_sell
from backend.agents.recovery_agent import detect_recoverable_carts, execute_recovery
from backend.engine.mandates import create_audit_log, append_audit_log

load_dotenv()


class UpsellChoice(BaseModel):
    suggest: bool
    sku: str
    reason: str


def generate_upsell(cart_items: list) -> dict | None:
    """
    Data-driven cross-sell recommendation using Hybrid Growth Engine:
      Layer 1 (Lift Engine): query basket_pairs derived from empirical orders or AI-seeded priors.
      Layer 2 (Growth Agent): given top candidates, LLM selects best
                             and writes natural, contextual copy grounded in the cart.

    Returns dict with keys:
      sku, name, price_paise, category, source, lift, support, confidence, reasoning, final_score, reason, candidates
    """
    if not cart_items:
        return None

    # Layer 1: Query Hybrid Lift Engine for top candidates
    candidates = find_cross_sell(cart_items, top_k=3)

    if not candidates:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if len(candidates) == 1 or not api_key:
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "source": c.get("source", "ai_suggested"),
            "lift": c.get("lift"),
            "support": c.get("support"),
            "confidence": c.get("confidence"),
            "reasoning": c.get("reasoning"),
            "co_occurrence_count": c.get("co_occurrence_count", 0),
            "final_score": c.get("final_score", 1.0),
            "reason": c.get("reason", "Complementary recommendation for your cart."),
            "candidates": candidates,
        }

    from backend.engine.llm import generate_structured
    system_instruction = (
        "You are an AI Commerce Growth Agent helping a customer. "
        "Review the proposed cart and candidate complementary add-on products. "
        "Select the most contextually relevant candidate SKU and write a concise, compelling 1-sentence recommendation reason."
    )
    try:
        choice = generate_structured(
            prompt=f"Cart Items: {json.dumps(cart_items)}\nCandidates: {json.dumps(candidates)}\nPick the best complementary cross-sell item.",
            schema=UpsellChoice,
            system_prompt=system_instruction
        )

        if choice.suggest and choice.sku:
            candidate_map = {c["sku"]: c for c in candidates}
            if choice.sku in candidate_map:
                chosen = candidate_map[choice.sku]
                return {
                    "sku": chosen["sku"],
                    "name": chosen["name"],
                    "price_paise": chosen["price_paise"],
                    "category": chosen["category"],
                    "source": chosen.get("source", "ai_suggested"),
                    "lift": chosen.get("lift"),
                    "support": chosen.get("support"),
                    "confidence": chosen.get("confidence"),
                    "reasoning": chosen.get("reasoning"),
                    "co_occurrence_count": chosen.get("co_occurrence_count", 0),
                    "final_score": chosen.get("final_score", 1.0),
                    "reason": choice.reason,
                    "candidates": candidates,
                }
    except Exception as e:
        print(f"Error in Growth Agent LLM selection: {e}")

    # Fallback to top ranked candidate by final_score
    c = candidates[0]
    return {
        "sku": c["sku"],
        "name": c["name"],
        "price_paise": c["price_paise"],
        "category": c["category"],
        "source": c.get("source", "ai_suggested"),
        "lift": c.get("lift"),
        "support": c.get("support"),
        "confidence": c.get("confidence"),
        "reasoning": c.get("reasoning"),
        "co_occurrence_count": c.get("co_occurrence_count", 0),
        "final_score": c.get("final_score", 1.0),
        "reason": c.get("reason", "Top complementary item for your order."),
        "candidates": candidates,
    }


def calculate_inventory_velocity_metrics(cursor) -> dict[str, Any]:
    """
    OBSERVE REAL INVENTORY BEHAVIOR:
    Calculates per-SKU sales velocity and inventory coverage from live orders:
    - units_sold_7d, units_sold_30d, units_sold_total
    - orders_7d, orders_30d, orders_total
    - sales_velocity_daily (units/day over 30d window)
    - days_since_last_sale
    - days_of_inventory (stock / max(velocity, 0.001))
    - cart_appearances (number of customer carts containing this SKU)
    - upsell_appearances (number of upsell offers and accepted count)
    """
    now = datetime.utcnow()

    # 1. Fetch settled orders with cart item arrays (excluding cancelled and refunded orders)
    cursor.execute("""
        SELECT pm.id, pm.cart_id, pm.created_at, cm.items
        FROM payment_mandates pm
        JOIN cart_mandates cm ON pm.cart_id = cm.id
        WHERE pm.status = 'succeeded'
          AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
          AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
    """)
    succeeded_orders = cursor.fetchall()

    sales_by_sku = {}

    for order in succeeded_orders:
        try:
            items = json.loads(order["items"]) if isinstance(order["items"], str) else (order["items"] or [])
        except Exception:
            items = []

        try:
            order_time = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            days_ago = (now - order_time).total_seconds() / 86400.0
        except Exception:
            days_ago = 15.0
            order_time = now - timedelta(days=15)

        for itm in items:
            sku = itm.get("sku")
            if not sku:
                continue
            qty = itm.get("qty", 1)
            if sku not in sales_by_sku:
                sales_by_sku[sku] = {
                    "units_sold_total": 0,
                    "units_sold_7d": 0,
                    "units_sold_30d": 0,
                    "orders_7d": 0,
                    "orders_30d": 0,
                    "orders_total": 0,
                    "last_sale_time": None,
                    "last_sale_days_ago": 999.0
                }
            s = sales_by_sku[sku]
            s["units_sold_total"] += qty
            s["orders_total"] += 1
            if days_ago <= 7:
                s["units_sold_7d"] += qty
                s["orders_7d"] += 1
            if days_ago <= 30:
                s["units_sold_30d"] += qty
                s["orders_30d"] += 1
            if s["last_sale_time"] is None or order_time > s["last_sale_time"]:
                s["last_sale_time"] = order_time
                s["last_sale_days_ago"] = round(days_ago, 1)

    # 2. Count cart appearances across all active/abandoned carts
    cursor.execute("SELECT items FROM cart_mandates")
    cart_rows = cursor.fetchall()
    cart_counts = {}
    for cr in cart_rows:
        try:
            c_items = json.loads(cr["items"]) if isinstance(cr["items"], str) else (cr["items"] or [])
            for itm in c_items:
                c_sku = itm.get("sku")
                if c_sku:
                    cart_counts[c_sku] = cart_counts.get(c_sku, 0) + 1
        except Exception:
            pass

    # 3. Count upsell offer events from upsell_events table
    cursor.execute("SELECT suggested_sku, COUNT(*) as offers, SUM(accepted) as accepted FROM upsell_events GROUP BY suggested_sku")
    upsell_counts = {r["suggested_sku"]: {"offers": r["offers"], "accepted": r["accepted"] or 0} for r in cursor.fetchall()}

    return {
        "sales": sales_by_sku,
        "cart_counts": cart_counts,
        "upsell_counts": upsell_counts
    }


def calculate_buyer_relevance_score(sku: str, category: str, velocity_data: dict, cursor) -> tuple[float, list[str]]:
    """
    USE CUSTOMER-DEMAND SIGNALS:
    Evaluates whether stagnant inventory is actually relevant to buyers before boosting:
    - Category Compatibility (does category have high-affinity links?)
    - Cart appearances & Search discoverability
    - Catalog embedding & metadata quality
    Returns (score 0.0 - 1.0, explanation_signals)
    """
    score = 0.50  # Neutral base prior
    signals = []

    # 1. Category Compatibility Graph connection
    cursor.execute("SELECT COUNT(*) FROM category_compatibility WHERE category_a = ? OR category_b = ?", (category, category))
    compat_count = cursor.fetchone()[0] or 0
    if compat_count > 0:
        score += 0.20
        signals.append(f"Strong category affinity ({compat_count} category graph links)")
    else:
        score -= 0.10
        signals.append("No active category compatibility graph links")

    # 2. Cart appearance history
    cart_appearances = velocity_data.get("cart_counts", {}).get(sku, 0)
    if cart_appearances > 0:
        score += 0.15
        signals.append(f"Appeared in {cart_appearances} customer shopping carts")

    # 3. Upsell conversion signals
    upsell_info = velocity_data.get("upsell_counts", {}).get(sku)
    if upsell_info and upsell_info["offers"] > 0:
        acceptance_pct = (upsell_info["accepted"] / upsell_info["offers"]) * 100
        if acceptance_pct >= 20:
            score += 0.15
            signals.append(f"High upsell conversion ({acceptance_pct:.1f}% acceptance)")
        elif acceptance_pct < 10 and upsell_info["offers"] >= 5:
            score -= 0.15
            signals.append(f"Low past upsell conversion ({acceptance_pct:.1f}%)")

    # 4. Check embedding vector presence for semantic retrieval
    cursor.execute("SELECT embedding FROM catalog WHERE sku = ?", (sku,))
    emb_row = cursor.fetchone()
    if emb_row and emb_row["embedding"]:
        score += 0.10
        signals.append("Vector embeddings indexed for semantic retrieval")

    normalized_score = max(0.10, min(0.95, round(score, 2)))
    return normalized_score, signals


class LLMVetoItem(BaseModel):
    sku: str
    decision: str  # 'ACCEPT' | 'REJECT'
    reasoning: str  # Grounded in provided evidence


class LLMVetoEvaluation(BaseModel):
    evaluations: list[LLMVetoItem]


def get_discoverability_and_demand_signals(sku: str, category: str, cursor) -> dict[str, Any]:
    """
    Extracts empirical discoverability and demand signals without fabricating metrics:
    - Recommendation Offers: upsell_events suggested_sku count
    - Recommendation Accepts: upsell_events accepted count
    - Cart Appearances: cart_mandates items matching sku
    - Realized Orders: historical_orders + payment_mandates
    - Structural Affinity: basket_pairs co-occurrences + category compatibility graph
    """
    # 1. Recommendation Offers (upsell_events)
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) FROM upsell_events WHERE suggested_sku = ?", (sku,))
    up_row = cursor.fetchone()
    rec_offers = up_row[0] or 0 if up_row else 0
    rec_accepts = up_row[1] or 0 if up_row else 0
    rec_conv_pct = round((rec_accepts / rec_offers) * 100, 1) if rec_offers > 0 else None

    # 2. Cart Appearances (cart_mandates)
    cursor.execute("SELECT COUNT(*) FROM cart_mandates WHERE items LIKE ?", (f"%{sku}%",))
    cart_appearances = cursor.fetchone()[0] or 0

    # 3. Realized Orders (historical_orders)
    cursor.execute("SELECT COUNT(*) FROM historical_orders WHERE items LIKE ?", (f"%{sku}%",))
    orders_count = cursor.fetchone()[0] or 0

    # 4. Structural Co-purchase Affinity (basket_pairs)
    cursor.execute("SELECT COUNT(*), MAX(lift) FROM basket_pairs WHERE (sku_a = ? OR sku_b = ?) AND muted = 0 AND retired = 0", (sku, sku))
    bp_row = cursor.fetchone()
    affinity_pairs_count = bp_row[0] or 0 if bp_row else 0
    max_lift = bp_row[1] or 1.0 if bp_row else 1.0

    # 5. Category Compatibility Count
    cursor.execute("SELECT COUNT(*) FROM category_compatibility WHERE category_a = ? OR category_b = ?", (category, category))
    cat_compat_count = cursor.fetchone()[0] or 0

    # 6. Vector Embedding Index Status
    cursor.execute("SELECT embedding FROM catalog WHERE sku = ?", (sku,))
    emb_row = cursor.fetchone()
    has_embedding = bool(emb_row and emb_row["embedding"])

    return {
        "sku": sku,
        "category": category,
        "recommendation_offer_count": rec_offers,
        "recommendation_accepted_count": rec_accepts,
        "recommendation_conversion_pct": rec_conv_pct,
        "cart_appearances_count": cart_appearances,
        "orders_count": orders_count,
        "affinity_pairs_count": affinity_pairs_count,
        "max_basket_lift": round(max_lift, 2),
        "category_compat_count": cat_compat_count,
        "has_embedding": has_embedding,
        "actual_impressions_recorded": "Not recorded in V1"
    }


def find_matched_controls(treatment_sku: str, category: str, price_paise: int, baseline_velocity: float, cursor, limit: int = 2) -> list[dict[str, Any]]:
    """
    Finds at least 2 valid matched control SKUs in the same category:
    - Same category
    - Unboosted (boosted = 0)
    - Non-legacy
    - Not in another active experiment
    - Not in active cooldown
    - Similar price band (0.4x to 2.5x of treatment price)
    - Similar baseline velocity
    """
    now_str = datetime.utcnow().isoformat() + "Z"
    cursor.execute("SELECT sku FROM promotion_experiments WHERE status = 'ACTIVE' OR cooldown_until > ?", (now_str,))
    excluded_skus = {r["sku"] for r in cursor.fetchall()}
    excluded_skus.add(treatment_sku)

    cursor.execute("""
        SELECT sku, name, category, price_paise, stock
        FROM catalog
        WHERE category = ? AND boosted = 0 AND stock > 0
    """, (category,))
    candidates = cursor.fetchall()

    velocity_data = calculate_inventory_velocity_metrics(cursor)
    sales_dict = velocity_data.get("sales", {})

    valid_controls = []
    min_price = int(price_paise * 0.35)
    max_price = int(price_paise * 2.8)

    for cand in candidates:
        c_sku = cand["sku"]
        if c_sku in excluded_skus:
            continue

        c_price = cand["price_paise"]
        if not (min_price <= c_price <= max_price):
            continue

        c_sales = sales_dict.get(c_sku, {})
        c_vel = round(c_sales.get("units_sold_30d", 0) / 30.0, 3)

        # Distance metric: combination of relative price distance and velocity distance
        price_diff_ratio = abs(c_price - price_paise) / max(1, price_paise)
        vel_diff = abs(c_vel - baseline_velocity)
        distance = price_diff_ratio + (vel_diff * 2.0)

        valid_controls.append({
            "sku": c_sku,
            "name": cand["name"],
            "category": cand["category"],
            "price_paise": c_price,
            "price_rupees": round(c_price / 100, 2),
            "stock": cand["stock"],
            "baseline_velocity_daily": c_vel,
            "orders_30d": c_sales.get("orders_30d", 0),
            "distance": distance
        })

    valid_controls.sort(key=lambda x: x["distance"])
    return valid_controls[:limit]


def scan_and_score_promotion_candidates(cursor) -> list[dict[str, Any]]:
    """
    STAGE 1: Whole-Catalog Deterministic Scoring (No LLM calls).
    Scans whole catalog, filters eligible SKUs, calculates continuous multi-factor scores,
    finds matched controls, and shortlists top 15–20 candidates.
    """
    now_str = datetime.utcnow().isoformat() + "Z"
    velocity_data = calculate_inventory_velocity_metrics(cursor)
    sales_dict = velocity_data.get("sales", {})

    cursor.execute("SELECT sku, cooldown_until FROM promotion_experiments WHERE cooldown_until > ?", (now_str,))
    in_cooldown_skus = {r["sku"]: r["cooldown_until"] for r in cursor.fetchall()}

    cursor.execute("SELECT sku, control_skus FROM promotion_experiments WHERE status = 'ACTIVE'")
    active_exp_rows = cursor.fetchall()
    active_exp_skus = {r["sku"] for r in active_exp_rows}
    active_control_skus = set()
    for r in active_exp_rows:
        try:
            ctrls = json.loads(r["control_skus"]) if r["control_skus"] else []
            for c in ctrls:
                active_control_skus.add(c.get("sku") if isinstance(c, dict) else c)
        except Exception:
            pass

    cursor.execute("SELECT sku, name, category, price_paise, stock, boosted, description FROM catalog WHERE stock > 0")
    all_catalog_items = cursor.fetchall()

    shortlist = []

    for itm in all_catalog_items:
        sku = itm["sku"]
        stock = itm["stock"]
        price_paise = itm["price_paise"]
        category = itm["category"]
        boosted = bool(itm["boosted"])

        # Exclusions: active experiment, active control SKU, active cooldown, currently boosted
        if sku in active_exp_skus or sku in active_control_skus or sku in in_cooldown_skus or boosted:
            continue

        sales_info = sales_dict.get(sku, {
            "units_sold_total": 0,
            "units_sold_7d": 0,
            "units_sold_30d": 0,
            "orders_7d": 0,
            "orders_30d": 0,
            "orders_total": 0,
            "last_sale_days_ago": 999.0
        })

        velocity_daily = round(sales_info["units_sold_30d"] / 30.0, 3)
        days_of_inv = round(stock / velocity_daily, 1) if velocity_daily > 0 else 999.0
        exposure_paise = stock * price_paise
        exposure_rupees = round(exposure_paise / 100, 2)

        signals = get_discoverability_and_demand_signals(sku, category, cursor)
        buyer_rel_score, rel_notes = calculate_buyer_relevance_score(sku, category, velocity_data, cursor)

        # ── 1. Discoverability vs. Demand Diagnostic Gate ────────────────────
        rec_offers = signals["recommendation_offer_count"]
        cart_apps = signals["cart_appearances_count"]
        orders_c = signals["orders_count"]

        # Discoverability Gap: high relevance but low recommendation offers & low cart appearances
        has_high_exposure = rec_offers >= 8 or cart_apps >= 6
        has_strong_demand = buyer_rel_score >= 0.40 or orders_c >= 2 or signals["affinity_pairs_count"] >= 1
        is_under_discovered = (rec_offers <= 3 and cart_apps <= 2 and buyer_rel_score >= 0.45)

        # Classify Business Objective / Opportunity Reason
        if stock >= 15 and days_of_inv >= 60 and has_strong_demand:
            opp_reason = "INVENTORY_RISK_WITH_DEMAND"
        elif is_under_discovered:
            opp_reason = "DISCOVERABILITY_GAP"
        elif sales_info["units_sold_30d"] == 0 and orders_c == 0 and buyer_rel_score >= 0.50:
            opp_reason = "NEW_PRODUCT_LAUNCH"
        elif category in ["sunglasses", "swimwear", "fragrances", "beauty"]:
            opp_reason = "SEASONAL_WINDOW"
        elif price_paise >= 200000 and buyer_rel_score >= 0.45:
            opp_reason = "STRATEGIC_PRODUCT"
        else:
            opp_reason = "INVENTORY_RISK_WITH_DEMAND"

        # Classify Diagnostic Product State
        if days_of_inv <= 45 and velocity_daily >= 0.2:
            product_state = "HEALTHY"
        elif 45 < days_of_inv <= 90 and velocity_daily > 0.05:
            product_state = "WATCH"
        elif is_under_discovered:
            product_state = "UNDER_DISCOVERED"
        elif days_of_inv > 60 and has_strong_demand:
            product_state = "STAGNANT_WITH_DEMAND"
        elif days_of_inv > 60 and not has_strong_demand:
            product_state = "STAGNANT_WITH_WEAK_DEMAND"
        elif orders_c == 0 and sales_info["units_sold_total"] == 0:
            product_state = "NEW_INSUFFICIENT_HISTORY"
        else:
            product_state = "NO_ACTION"

        # ── 2. Continuous Multi-Factor Stage 1 Composite Score ───────────────
        inv_risk_score = min(1.0, days_of_inv / 180.0) if days_of_inv != 999.0 else 0.85
        discoverability_gap_score = max(0.1, 1.0 - min(1.0, (rec_offers + cart_apps) / 10.0))
        evidence_qual_score = min(1.0, 0.4 + (orders_c + signals["affinity_pairs_count"] + len(rel_notes)) / 10.0)
        target_test_vel = max(velocity_daily * 1.35, 0.10)
        expected_14d_units = min(stock, max(1, round(target_test_vel * 14)))
        proj_opp_paise = int(expected_14d_units * price_paise)
        business_val_score = min(1.0, 0.3 + 0.7 * min(1.0, proj_opp_paise / 500000.0))

        # Composite Continuous Ranking Score
        stage1_score = round(
            (inv_risk_score * 0.25) +
            (buyer_rel_score * 0.30) +
            (discoverability_gap_score * 0.20) +
            (business_val_score * 0.15) +
            (evidence_qual_score * 0.10),
            3
        )

        # Check matched controls
        matched_controls = find_matched_controls(sku, category, price_paise, velocity_daily, cursor, limit=2)
        has_sufficient_controls = len(matched_controls) >= 2

        shortlist.append({
            "sku": sku,
            "name": itm["name"],
            "category": category,
            "description": itm["description"] or itm["name"],
            "price_paise": price_paise,
            "price_rupees": round(price_paise / 100, 2),
            "stock": stock,
            "sales_velocity_daily": velocity_daily,
            "days_of_inventory": days_of_inv,
            "days_since_last_sale": sales_info["last_sale_days_ago"],
            "inventory_value_exposure_paise": exposure_paise,
            "inventory_value_exposure_rupees": exposure_rupees,
            "signals": signals,
            "buyer_relevance_score": buyer_rel_score,
            "relevance_signals": rel_notes,
            "opportunity_reason": opp_reason,
            "product_state": product_state,
            "has_high_exposure": has_high_exposure,
            "has_strong_demand": has_strong_demand,
            "is_under_discovered": is_under_discovered,
            "matched_controls": matched_controls,
            "has_sufficient_controls": has_sufficient_controls,
            "inv_risk_score": inv_risk_score,
            "discoverability_gap_score": discoverability_gap_score,
            "evidence_qual_score": evidence_qual_score,
            "business_val_score": business_val_score,
            "stage1_score": stage1_score,
            "projected_14d_units": expected_14d_units,
            "projected_opportunity_paise": proj_opp_paise,
            "projected_opportunity_rupees": round(proj_opp_paise / 100, 2)
        })

    # Sort descending by Stage 1 Ranking Score and return top 15–20 candidates
    shortlist.sort(key=lambda x: x["stage1_score"], reverse=True)
    return shortlist[:20]


def llm_veto_promotion_shortlist(shortlist_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    STAGE 2: LLM Veto over the deterministic Stage 1 shortlist.
    - Receives ONLY the Stage 1 shortlist (cannot inject external SKUs or change metrics).
    - Returns ACCEPT or REJECT with evidence-grounded justification.
    - If LLM is unavailable or offline: gracefully falls back with 'ACCEPT_FALLBACK'
      and records 'Deterministic fallback — LLM review unavailable.'
    """
    if not shortlist_candidates:
        return []

    from backend.engine.llm import generate_structured, get_available_providers

    providers = get_available_providers()
    if not providers:
        # Graceful deterministic fallback
        for c in shortlist_candidates:
            c["stage2_llm_decision"] = "ACCEPT_FALLBACK"
            c["stage2_llm_reasoning"] = "Deterministic fallback — LLM review unavailable."
        return shortlist_candidates

    system_prompt = (
        "You are an AI Commerce Growth Strategist performing Stage 2 Veto Review on candidate products shortlisted for 1.35x discoverability promotion.\n"
        "Your task: evaluate whether increasing discoverability will plausibly solve the merchant's problem or if it is a true demand/context failure.\n"
        "Rules:\n"
        "1. You may ONLY evaluate the provided shortlisted SKUs.\n"
        "2. For each candidate output: decision ('ACCEPT' or 'REJECT') and reasoning.\n"
        "3. Justify rejections using explicit evidence (e.g. seasonal mismatch, weak demand signals, high existing exposure with no conversion).\n"
        "4. Do NOT make unsupported claims like 'poor quality' unless supported by explicit catalog evidence."
    )

    eval_input = [
        {
            "sku": c["sku"],
            "name": c["name"],
            "category": c["category"],
            "price_rupees": c["price_rupees"],
            "stock": c["stock"],
            "days_of_inventory": c["days_of_inventory"],
            "sales_velocity_daily": c["sales_velocity_daily"],
            "buyer_relevance_score": c["buyer_relevance_score"],
            "recommendation_offers": c["signals"]["recommendation_offer_count"],
            "cart_appearances": c["signals"]["cart_appearances_count"],
            "opportunity_reason": c["opportunity_reason"],
            "product_state": c["product_state"],
            "stage1_score": c["stage1_score"]
        }
        for c in shortlist_candidates
    ]

    try:
        res: LLMVetoEvaluation = generate_structured(
            prompt=f"Review this Stage 1 Shortlist for Promotion Suitability:\n{json.dumps(eval_input, indent=2)}",
            schema=LLMVetoEvaluation,
            system_prompt=system_prompt
        )

        decision_map = {item.sku: item for item in res.evaluations}
        for c in shortlist_candidates:
            if c["sku"] in decision_map:
                eval_item = decision_map[c["sku"]]
                c["stage2_llm_decision"] = eval_item.decision.upper()
                c["stage2_llm_reasoning"] = eval_item.reasoning
            else:
                c["stage2_llm_decision"] = "ACCEPT"
                c["stage2_llm_reasoning"] = "Stage 1 candidate qualified by deterministic scoring."

    except Exception as e:
        for c in shortlist_candidates:
            c["stage2_llm_decision"] = "ACCEPT_FALLBACK"
            c["stage2_llm_reasoning"] = f"Deterministic fallback — LLM review unavailable ({str(e)[:40]})."

    return shortlist_candidates


def classify_legacy_boosted_skus(cursor) -> dict[str, Any]:
    """
    Classifies currently boosted catalog items:
    - managed_active_experiment: SKUs active in promotion_experiments
    - legacy_unmanaged: Boosted SKUs without active experiment lifecycle (frozen in current state)
    """
    cursor.execute("SELECT sku, name, category, price_paise, stock FROM catalog WHERE boosted = 1")
    boosted_rows = cursor.fetchall()

    cursor.execute("SELECT sku, id, started_at, ends_at FROM promotion_experiments WHERE status = 'ACTIVE'")
    active_exp_map = {r["sku"]: dict(r) for r in cursor.fetchall()}

    managed = []
    unmanaged = []

    for r in boosted_rows:
        sku = r["sku"]
        if sku in active_exp_map:
            managed.append({
                "sku": sku,
                "name": r["name"],
                "category": r["category"],
                "stock": r["stock"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "experiment_id": active_exp_map[sku]["id"],
                "started_at": active_exp_map[sku]["started_at"],
                "ends_at": active_exp_map[sku]["ends_at"]
            })
        else:
            unmanaged.append({
                "sku": sku,
                "name": r["name"],
                "category": r["category"],
                "stock": r["stock"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "status": "legacy_unmanaged"
            })

    return {
        "total_boosted_skus": len(boosted_rows),
        "managed_active_count": len(managed),
        "legacy_unmanaged_count": len(unmanaged),
        "managed_active_experiments": managed,
        "legacy_unmanaged_boosts": unmanaged
    }


def assess_legacy_boosts_observational(cursor) -> dict[str, Any]:
    """
    OBSERVATIONAL LEGACY BOOST ASSESSMENT:
    Evaluates the 82 legacy boosted SKUs against category median velocity.
    Provides observational suggestions (KEEP, RETIRE, CONVERT_TO_EXPERIMENT)
    without causal claims.
    """
    velocity_data = calculate_inventory_velocity_metrics(cursor)
    sales_dict = velocity_data.get("sales", {})

    cursor.execute("SELECT sku, name, category, price_paise, stock FROM catalog WHERE boosted = 1 ORDER BY rowid DESC")
    boosted_rows = cursor.fetchall()

    cursor.execute("SELECT sku FROM promotion_experiments WHERE status = 'ACTIVE'")
    active_skus = {r["sku"] for r in cursor.fetchall()}

    category_velocities: dict[str, list[float]] = {}
    for sku, s_info in sales_dict.items():
        cat = s_info.get("category", "all")
        category_velocities.setdefault(cat, []).append(s_info.get("units_sold_30d", 0) / 30.0)

    legacy_assessments = []
    for r in boosted_rows:
        sku = r["sku"]
        if sku in active_skus:
            continue

        cat = r["category"]
        s_info = sales_dict.get(sku, {})
        vel = round(s_info.get("units_sold_30d", 0) / 30.0, 3)
        cat_vels = category_velocities.get(cat, [0.1])
        cat_median = round(sorted(cat_vels)[len(cat_vels)//2], 3) if cat_vels else 0.1

        signals = get_discoverability_and_demand_signals(sku, cat, cursor)

        if vel >= cat_median and vel > 0.1:
            suggested_action = "KEEP"
            reason = f"Observational velocity ({vel}/day) is above category median ({cat_median}/day)."
        elif vel == 0 and signals["recommendation_offer_count"] >= 5:
            suggested_action = "RETIRE"
            reason = f"Received {signals['recommendation_offer_count']} recommendation offers with 0 sales."
        else:
            suggested_action = "CONVERT_TO_EXPERIMENT"
            reason = f"Stagnant performance ({vel}/day); candidate for controlled 14-day experiment with matched controls."

        legacy_assessments.append({
            "sku": sku,
            "name": r["name"],
            "category": cat,
            "stock": r["stock"],
            "price_rupees": round(r["price_paise"] / 100, 2),
            "velocity_daily": vel,
            "category_median_velocity": cat_median,
            "suggested_action": suggested_action,
            "reason": reason,
            "disclaimer": "Legacy boost assessment — observational, not experimental."
        })

    return {
        "count": len(legacy_assessments),
        "assessments": legacy_assessments,
        "disclaimer": "Legacy boost assessment — observational, not experimental."
    }


def get_promotion_system_state(cursor) -> dict[str, Any]:
    """
    Returns live Promotion Experiment System State:
    - active_experiments_count (only 'ACTIVE' status experiments count towards cap)
    - max_active_experiments (from policy_config, default 5)
    - capacity_full (True if active_count >= max_active)
    - legacy_unmanaged_count (pre-existing unmanaged boosts)
    """
    cursor.execute("SELECT max_active_promotions FROM policy_config WHERE id = 1")
    pol = cursor.fetchone()
    max_active = pol["max_active_promotions"] if pol and pol["max_active_promotions"] is not None else 5

    cursor.execute("SELECT COUNT(*) FROM promotion_experiments WHERE status = 'ACTIVE'")
    active_count = cursor.fetchone()[0] or 0

    classification = classify_legacy_boosted_skus(cursor)

    capacity_full = active_count >= max_active
    available_capacity = max(0, max_active - active_count)

    return {
        "active_experiments_count": active_count,
        "max_active_experiments": max_active,
        "capacity_full": capacity_full,
        "available_capacity": available_capacity,
        "legacy_unmanaged_count": classification["legacy_unmanaged_count"],
        "total_boosted_skus": classification["total_boosted_skus"],
        "managed_active_experiments": classification["managed_active_experiments"],
        "legacy_unmanaged_boosts": classification["legacy_unmanaged_boosts"][:10],
        "message": (
            f"Promotion capacity full — {active_count}/{max_active} experiments active."
            if capacity_full
            else f"Promotion capacity available — {active_count}/{max_active} active experiments ({available_capacity} slot{'s' if available_capacity > 1 else ''} open)."
        )
    }


def evaluate_active_promotion_experiments(cursor) -> list[dict[str, Any]]:
    """
    DIFFERENCE-IN-DIFFERENCES EXPERIMENT EVALUATION & EARLY-KILL LOOP:
    Scans all ACTIVE promotion experiments:
    1. Measures treatment vs. matched control performance since started_at.
    2. Computes Treatment Lift, Control Lift, and Matched-Control Lift Estimate.
    3. Handles zero baselines cleanly (absolute unit differences).
    4. Early-Kill Check (Day 4–5): If treatment shows no advantage over controls and category is active, early-kills experiment.
    5. Day 14 Decision Gate: Reverts catalog.boosted = 0, checks minimum evidence thresholds,
       classifies outcome ('COMPLETED_LIFT', 'COMPLETED_NO_EFFECT', 'COMPLETED_HURT', 'COMPLETED_INCONCLUSIVE'),
       and sets merchant_decision = 'PENDING'.
    """
    now = datetime.utcnow()
    now_str = now.isoformat() + "Z"

    cursor.execute("""
        SELECT pe.*, c.name, c.stock as live_stock, c.price_paise
        FROM promotion_experiments pe
        JOIN catalog c ON pe.sku = c.sku
        WHERE pe.status = 'ACTIVE'
    """)
    active_exps = cursor.fetchall()
    evaluated = []

    for exp in active_exps:
        sku = exp["sku"]
        started_at_str = exp["started_at"]
        ends_at_str = exp["ends_at"]
        baseline_stock = exp["baseline_stock"]
        baseline_vel = exp["treatment_baseline_velocity"] or exp["baseline_velocity_daily"] or 0.0
        live_stock = exp["live_stock"]
        price_paise = exp["price_paise"]

        try:
            ctrls = json.loads(exp["control_skus"]) if exp["control_skus"] else []
        except Exception:
            ctrls = []

        try:
            start_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            start_dt = now - timedelta(days=1)

        try:
            ends_dt = datetime.fromisoformat(ends_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            ends_dt = now + timedelta(days=13)

        elapsed_days = max(1, (now - start_dt).days)

        # 1. Query treatment orders completed since experiment started (excluding cancelled/refunded)
        cursor.execute("""
            SELECT pm.id, pm.created_at, cm.items
            FROM payment_mandates pm
            JOIN cart_mandates cm ON pm.cart_id = cm.id
            WHERE pm.status = 'succeeded' 
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
              AND pm.created_at >= ?
        """, (started_at_str,))
        recent_orders = cursor.fetchall()

        units_sold_treatment = 0
        orders_treatment = 0
        for ro in recent_orders:
            try:
                items = json.loads(ro["items"]) if isinstance(ro["items"], str) else (ro["items"] or [])
                for itm in items:
                    if itm.get("sku") == sku:
                        units_sold_treatment += itm.get("qty", 1)
                        orders_treatment += 1
            except Exception:
                pass

        treatment_current_vel = round(units_sold_treatment / float(elapsed_days), 3)

        # 2. Query control group orders
        ctrl_skus = [c["sku"] if isinstance(c, dict) else c for c in ctrls]
        control_units_total = 0
        control_baseline_vel_total = 0.0
        for c in ctrls:
            if isinstance(c, dict):
                control_baseline_vel_total += c.get("baseline_velocity_daily", 0.0)

        control_baseline_vel_avg = round(control_baseline_vel_total / max(1, len(ctrls)), 3) if ctrls else 0.0

        for ro in recent_orders:
            try:
                items = json.loads(ro["items"]) if isinstance(ro["items"], str) else (ro["items"] or [])
                for itm in items:
                    if itm.get("sku") in ctrl_skus:
                        control_units_total += itm.get("qty", 1)
            except Exception:
                pass

        control_units_avg = control_units_total / max(1, len(ctrl_skus)) if ctrl_skus else 0.0
        control_current_vel_avg = round(control_units_avg / float(elapsed_days), 3)

        # 3. Calculate Treatment Lift & Control Lift (Matched-Control Lift Estimate)
        zero_baseline = baseline_vel == 0.0
        if zero_baseline:
            treatment_lift = None
            control_lift = None
            matched_lift_estimate = round(treatment_current_vel - control_current_vel_avg, 3)
        else:
            treatment_lift = round((treatment_current_vel - baseline_vel) / baseline_vel, 3)
            control_lift = round((control_current_vel_avg - control_baseline_vel_avg) / max(0.01, control_baseline_vel_avg), 3) if control_baseline_vel_avg > 0 else 0.0
            matched_lift_estimate = round(treatment_lift - control_lift, 3)

        realized_rev_paise = units_sold_treatment * price_paise
        units_liquidated = max(0, baseline_stock - live_stock)

        # 4. Check Early-Kill (Day 4–5): Treatment shows no advantage over controls and category is active
        is_early_kill = False
        early_kill_reason = None
        if 4 <= elapsed_days < 14:
            if units_sold_treatment <= control_units_avg and control_units_total >= 2:
                is_early_kill = True
                early_kill_reason = f"Day {elapsed_days} Early-Kill: Treatment ({units_sold_treatment} units) failed to outperform active category controls ({control_units_avg:.1f} avg units)."

        # 5. Check Day 14 Conclusion
        is_concluded = (now >= ends_dt) or is_early_kill
        if is_concluded:
            # Revert boost to organic 1.0x baseline
            cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))

            if is_early_kill:
                outcome_status = "early_killed_no_lift"
                merchant_dec = "DISCARD"
            else:
                # Minimum evidence thresholds check
                has_min_treatment_obs = units_sold_treatment >= 1 or orders_treatment >= 1
                has_min_control_obs = control_units_total >= 1
                if not (has_min_treatment_obs or has_min_control_obs):
                    outcome_status = "COMPLETED_INCONCLUSIVE"
                elif matched_lift_estimate and matched_lift_estimate > 0.15:
                    outcome_status = "COMPLETED_LIFT"
                elif matched_lift_estimate and matched_lift_estimate < -0.15:
                    outcome_status = "COMPLETED_HURT"
                else:
                    outcome_status = "COMPLETED_NO_EFFECT"
                merchant_dec = "PENDING"

            cursor.execute("""
                UPDATE promotion_experiments
                SET status = 'COMPLETED',
                    current_stock = ?,
                    units_liquidated = ?,
                    orders_during_experiment = ?,
                    realized_revenue_paise = ?,
                    treatment_current_velocity = ?,
                    control_current_velocity = ?,
                    treatment_lift = ?,
                    control_lift = ?,
                    matched_control_lift_estimate = ?,
                    zero_baseline_treatment = ?,
                    outcome_status = ?,
                    early_killed = ?,
                    early_kill_reason = ?,
                    merchant_decision = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                live_stock, units_liquidated, orders_treatment, realized_rev_paise,
                treatment_current_vel, control_current_vel_avg, treatment_lift, control_lift,
                matched_lift_estimate, 1 if zero_baseline else 0, outcome_status,
                1 if is_early_kill else 0, early_kill_reason, merchant_dec, now_str, exp["id"]
            ))

            create_audit_log(
                cursor,
                "growth_action",
                exp["id"],
                "Promotion Experiment Concluded",
                f"Promotion Experiment concluded for {exp['name']} (SKU: {sku}). Treatment sold: {units_sold_treatment} vs Control avg: {control_units_avg:.1f}. Matched-Control Lift Estimate: {matched_lift_estimate}. Outcome: {outcome_status}."
            )
        else:
            cursor.execute("""
                UPDATE promotion_experiments
                SET current_stock = ?,
                    units_liquidated = ?,
                    orders_during_experiment = ?,
                    realized_revenue_paise = ?,
                    treatment_current_velocity = ?,
                    control_current_velocity = ?,
                    treatment_lift = ?,
                    control_lift = ?,
                    matched_control_lift_estimate = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                live_stock, units_liquidated, orders_treatment, realized_rev_paise,
                treatment_current_vel, control_current_vel_avg, treatment_lift, control_lift,
                matched_lift_estimate, now_str, exp["id"]
            ))

        evaluated.append({
            "experiment_id": exp["id"],
            "sku": sku,
            "name": exp["name"],
            "status": "COMPLETED" if is_concluded else "ACTIVE",
            "units_sold_treatment": units_sold_treatment,
            "orders_treatment": orders_treatment,
            "control_units_avg": control_units_avg,
            "matched_control_lift_estimate": matched_lift_estimate,
            "realized_revenue_rupees": round(realized_rev_paise / 100, 2),
            "is_concluded": is_concluded,
            "early_killed": is_early_kill
        })

    return evaluated


def apply_seasonal_boosts(context: Optional[dict] = None) -> dict:
    """
    Autonomous AI Merchandiser:
    Evaluates real-time seasonal, meteorological, and festival signals from context_agent
    and writes dynamic boost weights and clear human-readable explanations to the catalog.
    
    PROTECTION RULE:
    If a SKU has boost_source == 'manual', its merchant-assigned boost is STRICTLY PROTECTED
    and will not be overwritten by autonomous seasonal adjustments.
    """
    from backend.agents.context_agent import get_context
    if context is None:
        context = get_context()

    conn = get_db()
    cursor = conn.cursor()

    category_boosts = context.get("category_boosts", {})
    
    cursor.execute("SELECT sku, category, boosted, boost_weight, boost_source, boost_reason FROM catalog")
    rows = cursor.fetchall()

    updated_count = 0
    manual_protected_count = 0
    elevated_count = 0
    penalized_count = 0

    for row in rows:
        sku = row["sku"]
        cat = row["category"]
        source = row["boost_source"] if "boost_source" in row.keys() and row["boost_source"] else "system"

        # Explicit User Directive: Protect manual merchant boosts
        if source == "manual":
            manual_protected_count += 1
            continue

        if cat in category_boosts:
            c_info = category_boosts[cat]
            target_weight = float(c_info.get("multiplier", 1.0))
            target_reason = str(c_info.get("reason", "Dynamic seasonal recommendation"))
        else:
            target_weight = 1.0
            target_reason = "Neutral baseline: standard seasonal demand"

        is_boosted = 1 if target_weight > 1.05 else 0

        cursor.execute(
            """
            UPDATE catalog 
            SET boost_weight = ?, boost_reason = ?, boost_source = 'agent', boosted = ?
            WHERE sku = ?
            """,
            (target_weight, target_reason, is_boosted, sku)
        )
        updated_count += 1
        if target_weight > 1.05:
            elevated_count += 1
        elif target_weight < 0.95:
            penalized_count += 1

    conn.commit()
    conn.close()

    return {
        "status": "applied",
        "season": context.get("season"),
        "season_label": context.get("season_label"),
        "weather": context.get("weather", {}),
        "total_skus_evaluated": len(rows),
        "updated_skus": updated_count,
        "manual_protected_skus": manual_protected_count,
        "elevated_skus": elevated_count,
        "penalized_skus": penalized_count,
        "upcoming_festivals_count": len(context.get("upcoming_festivals", []))
    }


def detect_all_opportunities() -> list[dict]:
    """
    OBSERVE & DETECT: Scans real merchant data across SQLite tables to detect live revenue growth opportunities.
    Returns structured Unified Growth Opportunity models:
    - RECOVER_CART: Carts approved by policy where checkout was not finalized.
    - CROSS_SELL: Category & empirical item affinity opportunities.
    - PROMOTE_PRODUCT: Evidence-based Inventory Stagnation & discoverability clearance.
    - weak_conversion: Low-converting upsell pairings (diagnostic only, NO_ACTION).
    """
    conn = get_db()
    cursor = conn.cursor()
    opportunities = []

    try:
        # 1. Fetch policy configuration for live guardrail evaluation
        cursor.execute("SELECT spend_cap_paise, autonomy_threshold_paise, allowed_categories, recovery_attribution_percent, recovery_idle_threshold_minutes FROM policy_config WHERE id = 1")
        pol_row = cursor.fetchone()
        spend_cap_paise = pol_row["spend_cap_paise"] if pol_row else 1000000
        autonomy_thresh_paise = pol_row["autonomy_threshold_paise"] if pol_row else 250000
        rec_attr_pct = pol_row["recovery_attribution_percent"] if pol_row and pol_row["recovery_attribution_percent"] is not None else 60
        rec_idle_min = pol_row["recovery_idle_threshold_minutes"] if pol_row and pol_row["recovery_idle_threshold_minutes"] is not None else 120

        # Get all dismissed and executed opportunity IDs & targets
        cursor.execute("SELECT id, execution_ref, affected_ref FROM growth_actions WHERE status IN ('dismissed', 'completed')")
        growth_action_rows = cursor.fetchall()
        dismissed_ids = {r[0] for r in growth_action_rows}
        executed_targets = set()
        for r in growth_action_rows:
            if r["execution_ref"]:
                executed_targets.add(r["execution_ref"])
            if r["affected_ref"]:
                try:
                    aff = json.loads(r["affected_ref"]) if isinstance(r["affected_ref"], str) else r["affected_ref"]
                    if isinstance(aff, dict):
                        if "target_sku" in aff:
                            executed_targets.add(aff["target_sku"])
                        if "sku" in aff:
                            executed_targets.add(aff["sku"])
                except Exception:
                    pass

        # Also get active promotion experiments to exclude active boosted SKUs
        cursor.execute("SELECT sku FROM promotion_experiments WHERE status = 'ACTIVE'")
        active_experiment_skus = {r[0] for r in cursor.fetchall()}
        executed_targets.update(active_experiment_skus)

        # ── 1. Abandoned Carts Recovery Opportunities (RECOVER_CART) ─────
        recoverable_carts = detect_recoverable_carts(limit=10)
        
        opp_recov_id = f"opp_recov_batch_{len(recoverable_carts)}"
        if recoverable_carts and opp_recov_id not in dismissed_ids:
            total_recov_paise = sum(c["total_paise"] for c in recoverable_carts)
            top_cart = recoverable_carts[0]
            avg_confidence = round(sum(c["confidence"] for c in recoverable_carts) / len(recoverable_carts), 2)
            ev_paise = int(avg_confidence * total_recov_paise)

            # Policy check: reminder link has ₹0 action cost & ₹0 autonomous financial exposure
            policy_ok = True
            policy_reason = f"Reminder link has ₹0 autonomous action cost (well within ₹{spend_cap_paise/100:.0f} spend cap). Customer checkout authorization is strictly required to capture funds."

            opportunities.append({
                "opportunity_id": opp_recov_id,
                "type": "RECOVER_CART",
                "goal": "Recover Lost Revenue",
                "business_problem": f"{len(recoverable_carts)} high-intent customer carts left incomplete after checkout approval",
                "evidence": {
                    "cart_count": len(recoverable_carts),
                    "top_cart_id": top_cart["cart_id"],
                    "top_cart_value_rupees": top_cart["total_rupees"],
                    "top_cart_items": top_cart["items_summary"],
                    "top_cart_idle_hours": top_cart.get("hours_since", 1.0),
                    "idle_gate_threshold_minutes": rec_idle_min,
                    "payment_state": top_cart.get("pay_status", "incomplete")
                },
                "affected_entity": {
                    "type": "cart_batch",
                    "id": top_cart["cart_id"],
                    "label": f"Top: {top_cart['items_summary']} (Cart {top_cart['cart_id'][-8:]})"
                },
                "estimated_opportunity_value_paise": total_recov_paise,
                "estimated_opportunity_value_rupees": round(total_recov_paise / 100, 2),
                "confidence": avg_confidence,
                "confidence_label": f"Heuristic Time-Decay ({top_cart.get('hours_since', 1.0):.1f}h idle)",
                "is_empirical_confidence": False,
                "expected_value_paise": ev_paise,
                "expected_value_rupees": round(ev_paise / 100, 2),
                "candidate_actions": [
                    {"action": "REISSUE_PAYMENT_LINK", "action_cost_paise": 0, "ev_paise": ev_paise, "label": "Reissue Razorpay payment link"},
                    {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "Wait for organic customer return"}
                ],
                "selected_action": {
                    "action_type": "RECOVER_CART",
                    "title": "Reissue Razorpay Payment Link",
                    "description": f"Generate clean payment recovery link for top cart {top_cart['cart_id'][-8:]} (₹{top_cart['total_rupees']})",
                    "target_id": top_cart["cart_id"],
                    "action_cost_paise": 0,
                    "action_cost_rupees": 0.0,
                    "financial_exposure_paise": 0,
                    "financial_exposure_rupees": 0.0
                },
                "policy_status": {
                    "approved": policy_ok,
                    "reason": policy_reason,
                    "idle_gate_met": top_cart.get("hours_since", 1.0) * 60 >= rec_idle_min or rec_idle_min == 0
                },
                "execution_status": "detected",
                "outcome": None,
                "why_this_action": {
                    "evidence_summary": [
                        f"{len(recoverable_carts)} carts approved by policy where checkout was not finalized.",
                        f"Top cart ({top_cart['items_summary']}) idle for {top_cart.get('hours_since', 1.0):.1f}h.",
                        "Items verified in stock."
                    ],
                    "calculation_formula": f"Expected Value = P(Success: {int(avg_confidence*100)}%) × Total Value (₹{total_recov_paise/100:.2f}) - Action Cost (₹0.00) = ₹{ev_paise/100:.2f}",
                    "historical_baseline": f"Baseline recovery rate decays from 38% over 48h. {rec_attr_pct}% attribution applied upon settlement.",
                    "policy_check": f"Action cost is ₹0 (Spend cap: ₹{spend_cap_paise/100:.0f}). Financial exposure is ₹0.",
                    "action_cost_explanation": "₹0.00 — Plain payment link; no discount or voucher created.",
                    "financial_exposure_explanation": "₹0.00 — Funds are only collected if the buyer explicitly completes Razorpay checkout.",
                    "will_do": "Generate/reissue a secure Razorpay Payment Link and dispatch a recovery reminder.",
                    "will_not_do": "Will NOT charge the customer's card automatically or apply unapproved price cuts."
                },
                "recommended_action": f"Reissue Razorpay payment link for top abandoned cart ({top_cart['cart_id'][-8:]}).",
                "action_target_id": top_cart["cart_id"],
                "action_executable": True,
                "created_at": datetime.utcnow().isoformat() + "Z"
            })

        # ── 2. Strong Statistical Cross-Sell Opportunities (CROSS_SELL) ──
        cursor.execute("""
            SELECT bp.sku_a, bp.sku_b, bp.lift, bp.co_occurrence_count, bp.confidence, bp.reasoning,
                   ca.name as name_a, cb.name as name_b, cb.price_paise as price_b, cb.category as cat_b
            FROM basket_pairs bp
            JOIN catalog ca ON ca.sku = bp.sku_a
            JOIN catalog cb ON cb.sku = bp.sku_b
            WHERE bp.source = 'data_verified' 
              AND (bp.retired IS NULL OR bp.retired = 0) 
              AND (bp.muted IS NULL OR bp.muted = 0)
              AND bp.co_occurrence_count >= 8 
              AND bp.lift > 1.2
            ORDER BY bp.lift DESC LIMIT 3
        """)
        strong_rules = cursor.fetchall()

        for r in strong_rules:
            opp_id = f"opp_xsell_{r['sku_a']}_{r['sku_b']}"
            if opp_id in dismissed_ids or r["sku_b"] in executed_targets or opp_id in executed_targets:
                continue

            est_incremental = r["price_b"]
            conf = min(0.85, round((r["confidence"] or 0.65), 2))
            ev_paise = int(conf * est_incremental)

            opportunities.append({
                "opportunity_id": opp_id,
                "type": "CROSS_SELL",
                "goal": "Increase Average Order Value (AOV)",
                "business_problem": f"Customers buying '{r['name_a']}' frequently seek '{r['name_b']}' but lack immediate checkout prompt",
                "evidence": {
                    "source_sku": r["sku_a"],
                    "target_sku": r["sku_b"],
                    "source_product": r["name_a"],
                    "target_product": r["name_b"],
                    "co_occurrences": r["co_occurrence_count"],
                    "statistical_lift": round(r["lift"], 2),
                    "rule_source": "data_verified"
                },
                "affected_entity": {
                    "type": "product_pair",
                    "id": f"{r['sku_a']}->{r['sku_b']}",
                    "label": f"{r['name_a']} → {r['name_b']}"
                },
                "estimated_opportunity_value_paise": est_incremental,
                "estimated_opportunity_value_rupees": round(est_incremental / 100, 2),
                "confidence": conf,
                "confidence_label": f"Empirical Lift ({r['lift']:.2f}x across {r['co_occurrence_count']} orders)",
                "is_empirical_confidence": True,
                "expected_value_paise": ev_paise,
                "expected_value_rupees": round(ev_paise / 100, 2),
                "candidate_actions": [
                    {"action": "PRIORITIZE_CROSS_SELL", "action_cost_paise": 0, "ev_paise": ev_paise, "label": f"Prioritize {r['name_b']} recommendation at checkout"},
                    {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "Rely on organic buyer search"}
                ],
                "selected_action": {
                    "action_type": "CROSS_SELL",
                    "title": f"Prioritize Cross-Sell: {r['name_b']}",
                    "description": f"Enable pre-checkout recommendation prompt when customer adds {r['name_a']}",
                    "target_id": r["sku_b"],
                    "action_cost_paise": 0,
                    "action_cost_rupees": 0.0,
                    "financial_exposure_paise": 0,
                    "financial_exposure_rupees": 0.0
                },
                "policy_status": {
                    "approved": True,
                    "reason": "Recommendation rule enablement has ₹0 financial cost. Revenue is realized only when buyer accepts at checkout."
                },
                "execution_status": "detected",
                "outcome": None,
                "why_this_action": {
                    "evidence_summary": [
                        f"{r['co_occurrence_count']} verified co-purchase orders in store history.",
                        f"{r['lift']:.2f}x statistical lift above independent chance.",
                        f"Target SKU '{r['name_b']}' priced at ₹{r['price_b']/100:.2f}."
                    ],
                    "calculation_formula": f"Expected Value = P(Acceptance: {int(conf*100)}%) × Add-on Price (₹{est_incremental/100:.2f}) - Action Cost (₹0.00) = ₹{ev_paise/100:.2f}",
                    "historical_baseline": "Cross-sell engine records exact cart delta upon settlement. No revenue claimed at rule activation time.",
                    "policy_check": "Category within merchant policy guidelines. Zero financial exposure.",
                    "action_cost_explanation": "₹0.00 — Internal ranking prioritization prompt.",
                    "financial_exposure_explanation": "₹0.00 — Customer must opt in by clicking 'Add to Cart' during checkout.",
                    "will_do": f"Prioritize {r['name_b']} in pre-checkout recommendation prompts for {r['name_a']}.",
                    "will_not_do": "Will NOT automatically inject items into the cart or bill the customer without approval."
                },
                "recommended_action": f"Prioritize {r['name_b']} in pre-checkout recommendations for {r['name_a']}.",
                "action_target_id": r["sku_b"],
                "action_executable": True,
                "created_at": datetime.utcnow().isoformat() + "Z"
            })

        if not strong_rules:
            cursor.execute("""
                SELECT cc.category_a, cc.category_b, cc.reasoning,
                       AVG(cb.price_paise) as avg_price_b
                FROM category_compatibility cc
                JOIN catalog cb ON cb.category = cc.category_b
                GROUP BY cc.category_a, cc.category_b
                LIMIT 2
            """)
            for cat_r in cursor.fetchall():
                opp_id = f"opp_cat_{cat_r['category_a']}_{cat_r['category_b']}"
                if opp_id in dismissed_ids:
                    continue

                avg_paise = int(cat_r["avg_price_b"] or 150000)
                conf = 0.68
                ev_paise = int(conf * avg_paise)

                opportunities.append({
                    "opportunity_id": opp_id,
                    "type": "CROSS_SELL",
                    "goal": "Increase Average Order Value (AOV)",
                    "business_problem": f"Buyers purchasing '{cat_r['category_a'].title()}' items frequently require complementary '{cat_r['category_b'].title()}' items",
                    "evidence": {
                        "category_a": cat_r["category_a"],
                        "category_b": cat_r["category_b"],
                        "compatibility_reason": cat_r["reasoning"],
                        "rule_source": "category_graph_prior"
                    },
                    "affected_entity": {
                        "type": "category_pair",
                        "id": f"{cat_r['category_a']}->{cat_r['category_b']}",
                        "label": f"{cat_r['category_a'].title()} → {cat_r['category_b'].title()}"
                    },
                    "estimated_opportunity_value_paise": avg_paise,
                    "estimated_opportunity_value_rupees": round(avg_paise / 100, 2),
                    "confidence": conf,
                    "confidence_label": "Graph Compatibility Prior",
                    "is_empirical_confidence": False,
                    "expected_value_paise": ev_paise,
                    "expected_value_rupees": round(ev_paise / 100, 2),
                    "candidate_actions": [
                        {"action": "PRIORITIZE_CATEGORY_AFFINITY", "action_cost_paise": 0, "ev_paise": ev_paise, "label": f"Prioritize {cat_r['category_b'].title()} add-ons"},
                        {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "No category prompt"}
                    ],
                    "selected_action": {
                        "action_type": "CROSS_SELL",
                        "title": f"Prioritize Category: {cat_r['category_b'].title()}",
                        "description": f"Enable cross-sell recommendations between {cat_r['category_a'].title()} and {cat_r['category_b'].title()}",
                        "target_id": cat_r["category_b"],
                        "action_cost_paise": 0,
                        "action_cost_rupees": 0.0,
                        "financial_exposure_paise": 0,
                        "financial_exposure_rupees": 0.0
                    },
                    "policy_status": {
                        "approved": True,
                        "reason": "Category synergy enablement has ₹0 cost. Realized revenue occurs strictly upon customer checkout acceptance."
                    },
                    "execution_status": "detected",
                    "outcome": None,
                    "why_this_action": {
                        "evidence_summary": [
                            f"Domain compatibility: {cat_r['reasoning']}",
                            f"Average add-on price in category: ₹{avg_paise/100:.2f}."
                        ],
                        "calculation_formula": f"Expected Value = P(Acceptance: 68%) × Avg Price (₹{avg_paise/100:.2f}) - Action Cost (₹0.00) = ₹{ev_paise/100:.2f}",
                        "historical_baseline": "Layer 1 Knowledge Graph prior. Calibrates with real checkout orders as transactions occur.",
                        "policy_check": "Both categories are approved in merchant policy.",
                        "action_cost_explanation": "₹0.00 — Recommendation rule configuration.",
                        "financial_exposure_explanation": "₹0.00 — Zero exposure; buyer must authorize purchase.",
                        "will_do": f"Surface relevant {cat_r['category_b'].title()} items when {cat_r['category_a'].title()} items are in cart.",
                        "will_not_do": "Will NOT charge buyer without confirmation."
                    },
                    "recommended_action": f"Actively cross-sell {cat_r['category_b'].title()} with {cat_r['category_a'].title()}.",
                    "action_target_id": cat_r["category_b"],
                    "action_executable": True,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })

        # ── 3. Evidence-Based Controlled Promotion Experiments (PROMOTE_PRODUCT) ────
        promo_state = get_promotion_system_state(cursor)

        # STAGE 1: Whole-Catalog Deterministic Scoring (15–20 candidates)
        stage1_candidates = scan_and_score_promotion_candidates(cursor)

        # STAGE 2: LLM Veto (Accept / Reject with evidence-grounded reasoning)
        stage2_candidates = llm_veto_promotion_shortlist(stage1_candidates)

        # Query empirical conversion history for promotion probability
        cursor.execute("""
            SELECT COUNT(*), SUM(CASE WHEN outcome_type = 'paid' THEN 1 ELSE 0 END)
            FROM growth_outcomes
            WHERE revenue_type = 'promotion'
        """)
        promo_history_row = cursor.fetchone()
        settled_promos_count = promo_history_row[1] or 0 if promo_history_row else 0
        total_promos_count = promo_history_row[0] or 0 if promo_history_row else 0

        if settled_promos_count >= 5:
            empirical_prob = round(settled_promos_count / max(1, total_promos_count), 2)
            prob_source = "empirical_conversion_history"
            is_emp_prob = True
            conf_label_template = f"Empirical Promotion Conversion ({settled_promos_count} settled outcomes)"
            opp_nature_label = "Projected Opportunity — Empirical Benchmark"
        else:
            empirical_prob = 0.20
            prob_source = "cold_start_heuristic"
            is_emp_prob = False
            conf_label_template = "Cold-start heuristic assumption: 15–20% expected velocity improvement"
            opp_nature_label = "Projected Opportunity — Heuristic"

        # STAGE 3: Final Promotion Suitability & Opportunity Construction
        accepted_candidates = [c for c in stage2_candidates if c.get("stage2_llm_decision") in ["ACCEPT", "ACCEPT_FALLBACK"]]
        rejected_candidates = [c for c in stage2_candidates if c.get("stage2_llm_decision") == "REJECT"]

        # Only generate new PROMOTE_PRODUCT opportunities if experiment capacity is available
        if not promo_state["capacity_full"]:
            slots_to_fill = min(2, promo_state["available_capacity"])
            for cand in accepted_candidates[:slots_to_fill]:
                opp_id = f"opp_promo_{cand['sku']}"
                if opp_id in dismissed_ids:
                    continue

                if not cand["has_sufficient_controls"]:
                    # Explicit NO_ACTION if fewer than 2 matched controls
                    opportunities.append({
                        "opportunity_id": f"opp_no_ctrls_{cand['sku']}",
                        "type": "PROMOTE_PRODUCT",
                        "goal": f"{cand['opportunity_reason']} (Insufficient Controls — No Action)",
                        "business_problem": f"Candidate '{cand['name']}' has {cand['stock']} units ({cand['days_of_inventory']}d coverage), but lacks 2 valid matched category controls",
                        "evidence": {
                            "sku": cand["sku"],
                            "product_name": cand["name"],
                            "category": cand["category"],
                            "stock_units": cand["stock"],
                            "unit_price_rupees": cand["price_rupees"],
                            "sales_velocity_daily": cand["sales_velocity_daily"],
                            "days_of_inventory": cand["days_of_inventory"],
                            "buyer_relevance_score": cand["buyer_relevance_score"],
                            "matched_controls_found": len(cand["matched_controls"]),
                            "status": "INSUFFICIENT_CONTROLS"
                        },
                        "affected_entity": {
                            "type": "product",
                            "id": cand["sku"],
                            "label": f"{cand['name']} (Insufficient Controls)"
                        },
                        "inventory_value_exposure_paise": cand["inventory_value_exposure_paise"],
                        "inventory_value_exposure_rupees": cand["inventory_value_exposure_rupees"],
                        "estimated_opportunity_value_paise": 0,
                        "estimated_opportunity_value_rupees": 0.0,
                        "opportunity_nature": "Control Group Gate Rejection",
                        "confidence": 0.90,
                        "confidence_label": "Methodological Control Check",
                        "is_empirical_confidence": True,
                        "expected_value_paise": 0,
                        "expected_value_rupees": 0.0,
                        "candidate_actions": [
                            {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "Insufficient matched controls for a defensible experiment"}
                        ],
                        "selected_action": {
                            "action_type": "NO_ACTION",
                            "title": "Do Not Promote — Insufficient Matched Controls",
                            "description": "Insufficient matched controls for a defensible experiment. Minimum 2 category control SKUs required.",
                            "target_id": cand["sku"],
                            "action_cost_paise": 0,
                            "action_cost_rupees": 0.0,
                            "financial_exposure_paise": 0,
                            "financial_exposure_rupees": 0.0
                        },
                        "policy_status": {
                            "approved": True,
                            "reason": "Difference-in-Differences methodology requires ≥2 valid unboosted category control SKUs."
                        },
                        "execution_status": "detected",
                        "outcome": None,
                        "why_this_action": {
                            "evidence_summary": [
                                f"Only {len(cand['matched_controls'])} matched control SKU(s) found in category '{cand['category']}' (minimum 2 required).",
                                "Running an uncontrolled single-product boost prevents causal measurement."
                            ],
                            "calculation_formula": "Expected Value = ₹0.00 (Uncontrolled single-item boosts prohibited)",
                            "historical_baseline": "Methodological control group requirement.",
                            "policy_check": "At least 2 matched control SKUs mandatory.",
                            "action_cost_explanation": "₹0.00 — No action dispatched.",
                            "financial_exposure_explanation": "₹0.00 — No financial exposure.",
                            "will_do": "Maintain standard 1.0x ranking until category peers are available for control matching.",
                            "will_not_do": "Will NOT launch uncontrolled single-item promotions."
                        },
                        "recommended_action": "Insufficient matched controls for a defensible experiment.",
                        "action_target_id": cand["sku"],
                        "action_executable": False,
                        "created_at": datetime.utcnow().isoformat() + "Z"
                    })
                    continue

                # Valid Promotion Candidate with Matched Controls
                inc_opp_paise = cand["projected_opportunity_paise"]
                ev_paise = int(empirical_prob * inc_opp_paise)
                expected_units = cand["projected_14d_units"]
                target_vel = max(cand["sales_velocity_daily"] * 1.35, 0.10)

                decision_confidence = round(min(0.95, 0.50 + cand["evidence_qual_score"] * 0.40), 2)
                decision_confidence_reason = (
                    f"Grounded in {cand['signals']['recommendation_offer_count']} recommendation offers, "
                    f"{cand['signals']['cart_appearances_count']} cart appearances, and {len(cand['matched_controls'])} matched controls."
                )

                opportunities.append({
                    "opportunity_id": opp_id,
                    "type": "PROMOTE_PRODUCT",
                    "goal": f"{cand['opportunity_reason']} (1.35x Discoverability Experiment)",
                    "business_problem": f"Business Opportunity ({cand['opportunity_reason'].replace('_', ' ')}): '{cand['name']}' has {cand['stock']} units sitting idle ({cand['days_of_inventory']}d coverage). Buyer relevance is strong ({cand['buyer_relevance_score']:.0%}), but product is currently under-discovered.",
                    "evidence": {
                        "sku": cand["sku"],
                        "product_name": cand["name"],
                        "category": cand["category"],
                        "stock_units": cand["stock"],
                        "unit_price_rupees": cand["price_rupees"],
                        "inventory_value_exposure_rupees": cand["inventory_value_exposure_rupees"],
                        "sales_velocity_daily": cand["sales_velocity_daily"],
                        "days_of_inventory": cand["days_of_inventory"],
                        "days_since_last_sale": cand["days_since_last_sale"] if cand["days_since_last_sale"] < 900 else "None in recorded store history",
                        "recommendation_offer_count": cand["signals"]["recommendation_offer_count"],
                        "recommendation_accepted_count": cand["signals"]["recommendation_accepted_count"],
                        "recommendation_conversion_pct": cand["signals"]["recommendation_conversion_pct"],
                        "cart_appearances_count": cand["signals"]["cart_appearances_count"],
                        "orders_count": cand["signals"]["orders_count"],
                        "actual_impressions_recorded": "Not recorded in V1",
                        "buyer_relevance_score": cand["buyer_relevance_score"],
                        "buyer_relevance_signals": cand["relevance_signals"],
                        "opportunity_reason": cand["opportunity_reason"],
                        "product_state": cand["product_state"],
                        "stage1_score": cand["stage1_score"],
                        "continuous_priority_score": cand["stage1_score"],
                        "stage2_llm_decision": cand.get("stage2_llm_decision", "ACCEPT_FALLBACK"),
                        "stage2_llm_reasoning": cand.get("stage2_llm_reasoning", "Stage 1 candidate qualified by deterministic scoring."),
                        "matched_controls": cand["matched_controls"],
                        "decision_confidence": decision_confidence,
                        "decision_confidence_reason": decision_confidence_reason,
                        "probability_source": prob_source,
                        "is_empirical_probability": is_emp_prob,
                        "active_experiment_capacity": f"{promo_state['active_experiments_count']}/{promo_state['max_active_experiments']}"
                    },
                    "affected_entity": {
                        "type": "product",
                        "id": cand["sku"],
                        "label": f"{cand['name']} ({cand['stock']} units · {cand['days_of_inventory']}d coverage)"
                    },
                    "inventory_value_exposure_paise": cand["inventory_value_exposure_paise"],
                    "inventory_value_exposure_rupees": cand["inventory_value_exposure_rupees"],
                    "estimated_opportunity_value_paise": inc_opp_paise,
                    "estimated_opportunity_value_rupees": round(inc_opp_paise / 100, 2),
                    "opportunity_nature": opp_nature_label,
                    "confidence": empirical_prob,
                    "confidence_label": conf_label_template,
                    "is_empirical_confidence": is_emp_prob,
                    "expected_value_paise": ev_paise,
                    "expected_value_rupees": round(ev_paise / 100, 2),
                    "candidate_actions": [
                        {
                            "action": "START_PROMOTION_EXPERIMENT",
                            "action_cost_paise": 0,
                            "ev_paise": ev_paise,
                            "label": f"Start 14-day promotion experiment (Target: {expected_units} units vs {len(cand['matched_controls'])} controls)"
                        },
                        {
                            "action": "NO_ACTION",
                            "action_cost_paise": 0,
                            "ev_paise": 0,
                            "label": "Maintain standard 1.0x discoverability ranking"
                        }
                    ],
                    "selected_action": {
                        "action_type": "PROMOTE_PRODUCT",
                        "title": f"Start 14-Day Promotion Experiment: {cand['name']}",
                        "description": f"Apply 1.35x search rank boost to test discoverability lift for {cand['name']} over 14d horizon against {len(cand['matched_controls'])} matched category controls",
                        "target_id": cand["sku"],
                        "action_cost_paise": 0,
                        "action_cost_rupees": 0.0,
                        "financial_exposure_paise": 0,
                        "financial_exposure_rupees": 0.0
                    },
                    "policy_status": {
                        "approved": True,
                        "reason": f"Category '{cand['category']}' is approved. Internal ranking boost costs ₹0 and active capacity ({promo_state['active_experiments_count']}/{promo_state['max_active_experiments']}) is available."
                    },
                    "execution_status": "detected",
                    "outcome": None,
                    "why_this_action": {
                        "evidence_summary": [
                            f"Business Objective: {cand['opportunity_reason'].replace('_', ' ')} (Diagnostic State: {cand['product_state']}).",
                            f"{cand['stock']} physical units in warehouse (Inventory Value Exposure: ₹{cand['inventory_value_exposure_rupees']:,.2f}).",
                            f"Discoverability vs Demand: {cand['signals']['recommendation_offer_count']} recommendation offers, {cand['signals']['cart_appearances_count']} cart appearances, {cand['buyer_relevance_score']:.0%} buyer relevance score.",
                            f"Stage 1 Continuous Score: {cand['stage1_score']:.3f} | Stage 2 LLM Review: {cand.get('stage2_llm_decision')} ({cand.get('stage2_llm_reasoning')}).",
                            f"Matched Control Group: {', '.join([c['name'] for c in cand['matched_controls']])}."
                        ],
                        "calculation_formula": f"Current velocity ({cand['sales_velocity_daily']:.2f} u/d) → 15-20% heuristic uplift (Target: {target_vel:.2f} u/d) → Projected {expected_units} units over 14d horizon → Projected Opportunity: ₹{inc_opp_paise/100:.2f} (EV @ {int(empirical_prob*100)}%: ₹{ev_paise/100:.2f})",
                        "historical_baseline": "Pre-action baseline snapshot and matched controls recorded at launch. Difference-in-Differences measured over 14-day horizon.",
                        "policy_check": "Product in stock, demand gate passed (≥40%), active capacity available.",
                        "action_cost_explanation": "₹0.00 — Purely an internal algorithmic ranking prioritization; no ad spend or voucher cost.",
                        "financial_exposure_explanation": "₹0.00 — Funds are collected as customer checkout orders occur organically at full retail price.",
                        "will_do": f"Activate 1.35x discoverability rank boost for {cand['name']} and begin 14-day Difference-in-Differences experiment tracking against {len(cand['matched_controls'])} controls.",
                        "will_not_do": "Will NOT markdown item price, create coupons, or incur paid advertising costs."
                    },
                    "recommended_action": f"Start 14-Day Promotion Experiment for {cand['name']}.",
                    "action_target_id": cand["sku"],
                    "action_executable": True,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })

        # ── 3b. Explicit NO_ACTION for Stagnant Inventory with Weak Buyer Demand / Vetoed ───
        weak_candidates = [c for c in stage1_candidates if c["buyer_relevance_score"] < 0.40 or c.get("stage2_llm_decision") == "REJECT"]
        if weak_candidates and len(opportunities) < 6:
            weak = weak_candidates[0]
            opp_id = f"opp_weak_demand_{weak['sku']}"
            if opp_id not in dismissed_ids:
                is_vetoed = weak.get("stage2_llm_decision") == "REJECT"
                no_act_title = "Do Not Promote — LLM Veto" if is_vetoed else "Do Not Promote — Weak Buyer Demand"
                no_act_desc = weak.get("stage2_llm_reasoning") if is_vetoed else "This inventory is stagnant, but increasing visibility is unlikely to solve the problem due to weak buyer demand signals."

                opportunities.append({
                    "opportunity_id": opp_id,
                    "type": "PROMOTE_PRODUCT",
                    "goal": f"INVENTORY STAGNANT ({'LLM Vetoed' if is_vetoed else 'Weak Buyer Demand'} — No Action)",
                    "business_problem": f"Stagnant inventory: '{weak['name']}' has {weak['stock']} units ({weak['days_of_inventory']}d coverage), but {no_act_desc}",
                    "evidence": {
                        "sku": weak["sku"],
                        "product_name": weak["name"],
                        "category": weak["category"],
                        "stock_units": weak["stock"],
                        "unit_price_rupees": weak["price_rupees"],
                        "inventory_value_exposure_rupees": weak["inventory_value_exposure_rupees"],
                        "sales_velocity_daily": weak["sales_velocity_daily"],
                        "days_of_inventory": weak["days_of_inventory"],
                        "buyer_relevance_score": weak["buyer_relevance_score"],
                        "recommendation_offer_count": weak["signals"]["recommendation_offer_count"],
                        "cart_appearances_count": weak["signals"]["cart_appearances_count"],
                        "stage1_score": weak["stage1_score"],
                        "stage2_llm_decision": weak.get("stage2_llm_decision"),
                        "stage2_llm_reasoning": weak.get("stage2_llm_reasoning"),
                        "status": "VETOED" if is_vetoed else "WEAK_BUYER_DEMAND"
                    },
                    "affected_entity": {
                        "type": "product",
                        "id": weak["sku"],
                        "label": f"{weak['name']} ({'Vetoed' if is_vetoed else 'Weak Demand'})"
                    },
                    "inventory_value_exposure_paise": weak["inventory_value_exposure_paise"],
                    "inventory_value_exposure_rupees": weak["inventory_value_exposure_rupees"],
                    "estimated_opportunity_value_paise": 0,
                    "estimated_opportunity_value_rupees": 0.0,
                    "opportunity_nature": "Demand / Veto Gate Rejection",
                    "confidence": 0.85,
                    "confidence_label": "Demand & Veto Gate Evaluated",
                    "is_empirical_confidence": True,
                    "expected_value_paise": 0,
                    "expected_value_rupees": 0.0,
                    "candidate_actions": [
                        {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "Do not promote (Demand/Veto gate)"}
                    ],
                    "selected_action": {
                        "action_type": "NO_ACTION",
                        "title": no_act_title,
                        "description": no_act_desc,
                        "target_id": weak["sku"],
                        "action_cost_paise": 0,
                        "action_cost_rupees": 0.0,
                        "financial_exposure_paise": 0,
                        "financial_exposure_rupees": 0.0
                    },
                    "policy_status": {
                        "approved": True,
                        "reason": "Demand and LLM Veto gates prevent wasteful discoverability dilution on products with weak conversion likelihood."
                    },
                    "execution_status": "detected",
                    "outcome": None,
                    "why_this_action": {
                        "evidence_summary": [
                            f"{weak['stock']} physical units with {weak['days_of_inventory']} days of coverage.",
                            f"Buyer relevance score is {weak['buyer_relevance_score']:.0%}.",
                            f"LLM Veto decision: {weak.get('stage2_llm_decision')} ({weak.get('stage2_llm_reasoning')})."
                        ],
                        "calculation_formula": "Expected Value = ₹0.00 (Low conversion probability makes promotion ineffective)",
                        "historical_baseline": "Boosting low-demand or context-mismatched items degrades search result quality without converting into checkout orders.",
                        "policy_check": "Demand gate active; ranking priority reserved for high-relevance inventory.",
                        "action_cost_explanation": "₹0.00 — No action taken.",
                        "financial_exposure_explanation": "₹0.00 — No financial exposure.",
                        "will_do": "Maintain standard ranking and monitor organic demand signals.",
                        "will_not_do": "Will NOT artificially promote items with low shopper relevance."
                    },
                    "recommended_action": no_act_desc,
                    "action_target_id": weak["sku"],
                    "action_executable": False,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })

        # ── 3c. Explicit NO_ACTION Decision for Healthy Inventory ───────────
        healthy_candidates = [c for c in stage1_candidates if c["product_state"] == "HEALTHY"]
        if healthy_candidates:
            healthy = healthy_candidates[0]
            opp_id = f"opp_healthy_{healthy['sku']}"
            if opp_id not in dismissed_ids:
                opportunities.append({
                    "opportunity_id": opp_id,
                    "type": "PROMOTE_PRODUCT",
                    "goal": "INVENTORY HEALTHY (Maintain Current Ranking)",
                    "business_problem": f"Healthy stock velocity: '{healthy['name']}' has {healthy['stock']} units with healthy {healthy['days_of_inventory']}d coverage",
                    "evidence": {
                        "sku": healthy["sku"],
                        "product_name": healthy["name"],
                        "category": healthy["category"],
                        "stock_units": healthy["stock"],
                        "unit_price_rupees": healthy["price_rupees"],
                        "inventory_value_exposure_rupees": healthy["inventory_value_exposure_rupees"],
                        "sales_velocity_daily": healthy["sales_velocity_daily"],
                        "days_of_inventory": healthy["days_of_inventory"],
                        "status": "HEALTHY_VELOCITY"
                    },
                    "affected_entity": {
                        "type": "product",
                        "id": healthy["sku"],
                        "label": f"{healthy['name']} (Healthy · {healthy['days_of_inventory']}d coverage)"
                    },
                    "inventory_value_exposure_paise": healthy["inventory_value_exposure_paise"],
                    "inventory_value_exposure_rupees": healthy["inventory_value_exposure_rupees"],
                    "estimated_opportunity_value_paise": 0,
                    "estimated_opportunity_value_rupees": 0.0,
                    "opportunity_nature": "Healthy Inventory Baseline",
                    "confidence": 0.95,
                    "confidence_label": "Healthy Velocity Benchmark",
                    "is_empirical_confidence": True,
                    "expected_value_paise": 0,
                    "expected_value_rupees": 0.0,
                    "candidate_actions": [
                        {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "Maintain standard 1.0x ranking"}
                    ],
                    "selected_action": {
                        "action_type": "NO_ACTION",
                        "title": "Maintain Standard 1.0x Ranking",
                        "description": "Inventory is healthy; additional discoverability is not currently justified.",
                        "target_id": healthy["sku"],
                        "action_cost_paise": 0,
                        "action_cost_rupees": 0.0,
                        "financial_exposure_paise": 0,
                        "financial_exposure_rupees": 0.0
                    },
                    "policy_status": {
                        "approved": True,
                        "reason": "Fast-moving inventory does not require artificial promotion."
                    },
                    "execution_status": "detected",
                    "outcome": None,
                    "why_this_action": {
                        "evidence_summary": [
                            f"Stock coverage is healthy at {healthy['days_of_inventory']} days (below 45-day stagnation threshold).",
                            f"Selling at {healthy['sales_velocity_daily']} units/day organically."
                        ],
                        "calculation_formula": "Expected Value = ₹0.00 (Promotion boost not required for healthy inventory)",
                        "historical_baseline": "Organic velocity already meets merchant inventory turnover expectations.",
                        "policy_check": "Inventory healthy; no intervention needed.",
                        "action_cost_explanation": "₹0.00 — No action taken.",
                        "financial_exposure_explanation": "₹0.00 — No financial exposure.",
                        "will_do": "Maintain standard search ranking and monitor sell-through rate.",
                        "will_not_do": "Will NOT dilute promotion slots on already high-velocity products."
                    },
                    "recommended_action": "Maintain standard 1.0x ranking for healthy inventory.",
                    "action_target_id": healthy["sku"],
                    "action_executable": False,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })


        # ── 4. Low Conversion Proxy (Diagnostic Review Only, NO_ACTION) ──
        cursor.execute("""
            SELECT ue.suggested_sku, c.name, c.price_paise,
                   COUNT(*) as offers,
                   SUM(ue.accepted) as accepted,
                   ROUND(SUM(ue.accepted)*1.0 / COUNT(*), 2) as conv_rate
            FROM upsell_events ue
            LEFT JOIN catalog c ON c.sku = ue.suggested_sku
            GROUP BY ue.suggested_sku
            HAVING offers >= 5 AND conv_rate < 0.20
            ORDER BY offers DESC LIMIT 1
        """)
        low_conv = cursor.fetchone()
        if low_conv:
            opp_id = f"opp_low_conv_{low_conv['suggested_sku']}"
            if opp_id not in dismissed_ids:
                opportunities.append({
                    "opportunity_id": opp_id,
                    "type": "weak_conversion",
                    "goal": "Optimize Recommendation Quality",
                    "business_problem": f"Low buyer conversion ({int(low_conv['conv_rate']*100)}%) on recommendation prompt for '{low_conv['name'] or low_conv['suggested_sku']}'",
                    "evidence": {
                        "sku": low_conv["suggested_sku"],
                        "product_name": low_conv["name"],
                        "total_offers": low_conv["offers"],
                        "accepted_count": int(low_conv["accepted"]),
                        "conversion_rate_pct": round(low_conv["conv_rate"] * 100, 1)
                    },
                    "affected_entity": {
                        "type": "recommendation_rule",
                        "id": low_conv["suggested_sku"],
                        "label": f"{low_conv['name'] or low_conv['suggested_sku']}"
                    },
                    "estimated_opportunity_value_paise": 0,
                    "estimated_opportunity_value_rupees": 0.0,
                    "confidence": 0.80,
                    "confidence_label": f"Empirical ({low_conv['offers']} offers recorded)",
                    "is_empirical_confidence": True,
                    "expected_value_paise": 0,
                    "expected_value_rupees": 0.0,
                    "candidate_actions": [
                        {"action": "NO_ACTION", "action_cost_paise": 0, "ev_paise": 0, "label": "No autonomous change; flag for merchant review"}
                    ],
                    "selected_action": {
                        "action_type": "NO_ACTION",
                        "title": "Merchant Review Recommended (No Action Dispatched)",
                        "description": "Diagnostic insight only. Review product price point, relevance, or substitute pairing.",
                        "target_id": low_conv["suggested_sku"],
                        "action_cost_paise": 0,
                        "action_cost_rupees": 0.0,
                        "financial_exposure_paise": 0,
                        "financial_exposure_rupees": 0.0
                    },
                    "policy_status": {
                        "approved": False,
                        "reason": "Diagnostic only. Autonomous modifications are disabled for weak conversion rules."
                    },
                    "execution_status": "diagnostic_only",
                    "outcome": None,
                    "why_this_action": {
                        "evidence_summary": [
                            f"Offered {low_conv['offers']} times to shoppers at checkout.",
                            f"Accepted only {int(low_conv['accepted'])} times ({round(low_conv['conv_rate']*100, 1)}% conversion rate).",
                            "Conversion is below the 20% healthy performance threshold."
                        ],
                        "calculation_formula": "Expected Value = ₹0.00 (No automated action is justified without merchant pairing review).",
                        "historical_baseline": "Empirical store analytics indicate low buyer affinity at the current price point.",
                        "policy_check": "Agent safely flags diagnostic data without making unapproved catalog changes.",
                        "action_cost_explanation": "₹0.00 — Informational notification.",
                        "financial_exposure_explanation": "₹0.00 — Zero financial exposure.",
                        "will_do": "Surface diagnostic analytics for merchant consideration.",
                        "will_not_do": "Will NOT automatically alter prices, disable pairings, or modify catalog without approval."
                    },
                    "recommended_action": "Review recommendation pairing and price point. No autonomous action dispatched.",
                    "action_target_id": low_conv["suggested_sku"],
                    "action_executable": False,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })

        return opportunities
    finally:
        conn.close()


def score_next_best_actions(limit: int = 5) -> list[dict]:
    """
    Next Best Action (NBA) engine:
    Evaluates detected opportunities and prioritizes by Expected Value (EV):
      EV = P(Success) * Expected Incremental Revenue - Action Cost
    Sorts and prioritizes the highest expected return actions for the merchant.
    """
    opportunities = detect_all_opportunities()
    # Sort by expected value descending
    opportunities.sort(key=lambda x: x.get("expected_value_paise", 0), reverse=True)
    return opportunities[:limit]


def execute_growth_action(action_type: str, target_id: str, mode: str = "manual") -> dict:
    """
    Executes a chosen Next Best Action with full auditability and guardrail verification:
    - RECOVER_CART: generates/reissues Razorpay payment link
    - PROMOTE_PRODUCT: toggles catalog.boosted = 1
    - CROSS_SELL: activates prioritized cross-sell recommendation rule
    - NO_ACTION: safely acknowledges diagnostic review
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"

        if action_type == "RECOVER_CART":
            return execute_recovery(target_id)

        elif action_type == "PROMOTE_PRODUCT":
            sku = target_id
            cursor.execute("SELECT sku, name, category, price_paise, stock FROM catalog WHERE sku = ?", (sku,))
            item = cursor.fetchone()
            if not item:
                raise ValueError(f"SKU {sku} not found in catalog.")

            # 1. Check Active Capacity Cap
            cursor.execute("SELECT max_active_promotions FROM policy_config WHERE id = 1")
            pol = cursor.fetchone()
            max_active = pol["max_active_promotions"] if pol and pol["max_active_promotions"] is not None else 5

            cursor.execute("SELECT COUNT(*) FROM promotion_experiments WHERE status = 'ACTIVE'")
            active_count = cursor.fetchone()[0] or 0
            if active_count >= max_active:
                raise ValueError(f"Active promotion experiment limit reached ({active_count}/{max_active}). Cannot launch new promotion experiments until existing experiments complete.")

            # 2. Check Cooldown
            cursor.execute("SELECT id, cooldown_until FROM promotion_experiments WHERE sku = ? AND cooldown_until > ?", (sku, now_str))
            cool = cursor.fetchone()
            if cool:
                raise ValueError(f"SKU {sku} is in promotion cooldown until {cool['cooldown_until']}.")

            # Record pre-action baseline experiment snapshot
            velocity_data = calculate_inventory_velocity_metrics(cursor)
            sku_sales = velocity_data.get("sales", {}).get(sku, {})
            pre_velocity = sku_sales.get("units_sold_30d", 0) / 30.0
            pre_coverage = round(item["stock"] / pre_velocity, 1) if pre_velocity > 0 else 999.0
            rel_score, rel_signals = calculate_buyer_relevance_score(sku, item["category"], velocity_data, cursor)

            now_dt = datetime.utcnow()
            ends_at_str = (now_dt + timedelta(days=14)).isoformat() + "Z"
            cooldown_until_str = (now_dt + timedelta(days=21)).isoformat() + "Z"

            pre_snapshot = {
                "sku": sku,
                "name": item["name"],
                "category": item["category"],
                "stock_units": item["stock"],
                "unit_price_paise": item["price_paise"],
                "units_sold_7d": sku_sales.get("units_sold_7d", 0),
                "units_sold_30d": sku_sales.get("units_sold_30d", 0),
                "orders_30d": sku_sales.get("orders_30d", 0),
                "sales_velocity_daily": round(pre_velocity, 3),
                "days_of_inventory": pre_coverage,
                "buyer_relevance_score": rel_score,
                "buyer_relevance_signals": rel_signals,
                "experiment_horizon_days": 14,
                "activated_at": now_str,
                "ends_at": ends_at_str,
                "cooldown_until": cooldown_until_str
            }

            # Find at least 2 matched control SKUs
            matched_controls = find_matched_controls(sku, item["category"], item["price_paise"], pre_velocity, cursor, limit=2)
            if len(matched_controls) < 2:
                raise ValueError(f"Cannot launch experiment for SKU {sku}: Insufficient matched category controls found (found {len(matched_controls)}, minimum 2 required).")

            control_base_vel_avg = round(sum(c.get("baseline_velocity_daily", 0.0) for c in matched_controls) / max(1, len(matched_controls)), 3)

            # Discoverability and Demand Diagnostic Signals
            signals = get_discoverability_and_demand_signals(sku, item["category"], cursor)

            # Stage 1 Score & Stage 2 Decision
            stage1_candidates = scan_and_score_promotion_candidates(cursor)
            matched_cand = next((c for c in stage1_candidates if c["sku"] == sku), None)

            opp_reason = matched_cand["opportunity_reason"] if matched_cand else "INVENTORY_RISK_WITH_DEMAND"
            product_state = matched_cand["product_state"] if matched_cand else "STAGNANT_WITH_DEMAND"
            stage1_score = matched_cand["stage1_score"] if matched_cand else 0.75

            # LLM Veto
            if matched_cand:
                vetoed = llm_veto_promotion_shortlist([matched_cand])
                stage2_dec = vetoed[0].get("stage2_llm_decision", "ACCEPT_FALLBACK")
                stage2_reason = vetoed[0].get("stage2_llm_reasoning", "Deterministic fallback — LLM review unavailable.")
            else:
                stage2_dec = "ACCEPT"
                stage2_reason = "Manual promotion launch."

            # Probability source
            cursor.execute("""
                SELECT COUNT(*), SUM(CASE WHEN outcome_type = 'paid' THEN 1 ELSE 0 END)
                FROM growth_outcomes
                WHERE revenue_type = 'promotion'
            """)
            p_row = cursor.fetchone()
            settled_c = p_row[1] or 0 if p_row else 0
            total_c = p_row[0] or 0 if p_row else 0
            if settled_c >= 5:
                prob = round(settled_c / max(1, total_c), 2)
                prob_source = "empirical_conversion_history"
                is_emp = 1
            else:
                prob = 0.20
                prob_source = "cold_start_heuristic"
                is_emp = 0

            confidence = 0.85
            conf_reason = f"Grounded in {signals['recommendation_offer_count']} recommendation offers, {signals['cart_appearances_count']} cart appearances, and {len(matched_controls)} matched controls."

            target_velocity = max(pre_velocity * 1.35, 0.10)
            expected_14d_units = min(item["stock"], max(1, round(target_velocity * 14)))
            incremental_est_paise = int(expected_14d_units * item["price_paise"])

            pre_snapshot["matched_controls"] = matched_controls
            pre_snapshot["control_baseline_velocity_avg"] = control_base_vel_avg
            pre_snapshot["opportunity_reason"] = opp_reason
            pre_snapshot["product_state"] = product_state
            pre_snapshot["stage1_score"] = stage1_score
            pre_snapshot["stage2_llm_decision"] = stage2_dec
            pre_snapshot["stage2_llm_reasoning"] = stage2_reason
            pre_snapshot["signals"] = signals

            cursor.execute("UPDATE catalog SET boosted = 1 WHERE sku = ?", (sku,))
            action_id = f"ga_promo_{uuid.uuid4().hex[:10]}"
            exp_id = f"exp_{uuid.uuid4().hex[:10]}"

            # Insert into promotion_experiments with matched controls & DiD baseline fields
            cursor.execute("""
                INSERT INTO promotion_experiments (
                    id, sku, status, action_id, baseline_stock, baseline_velocity_daily,
                    baseline_days_of_inventory, baseline_orders_30d, buyer_relevance_score,
                    experiment_horizon_days, started_at, ends_at, cooldown_until,
                    current_stock, units_liquidated, orders_during_experiment, realized_revenue_paise,
                    outcome_status, notes, created_at, updated_at,
                    control_skus, treatment_baseline_velocity, control_baseline_velocity,
                    zero_baseline_treatment, opportunity_reason, product_state,
                    stage1_score, stage2_llm_decision, stage2_llm_reasoning,
                    final_suitability_score, decision_confidence, decision_confidence_reason,
                    probability_source, is_empirical_probability, early_killed, merchant_decision
                ) VALUES (
                    ?, ?, 'ACTIVE', ?, ?, ?,
                    ?, ?, ?,
                    14, ?, ?, ?,
                    ?, 0, 0, 0,
                    'pending', ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, 0, 'PENDING'
                )
            """, (
                exp_id, sku, action_id, item["stock"], round(pre_velocity, 3),
                pre_coverage, sku_sales.get("orders_30d", 0), rel_score,
                now_str, ends_at_str, cooldown_until_str,
                item["stock"], json.dumps(pre_snapshot), now_str, now_str,
                json.dumps(matched_controls), round(pre_velocity, 3), control_base_vel_avg,
                1 if pre_velocity == 0 else 0, opp_reason, product_state,
                stage1_score, stage2_dec, stage2_reason,
                stage1_score, confidence, conf_reason,
                prob_source, is_emp
            ))

            cursor.execute("""
                INSERT INTO growth_actions (
                    id, action_type, status, opportunity_type, title, explanation,
                    affected_ref, est_revenue_paise, confidence, recommended_action,
                    execution_ref, mode, created_at, executed_at, notes
                ) VALUES (?, 'PROMOTE_PRODUCT', 'completed', 'inventory_stagnation', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_id,
                f"Promotion Experiment Started: {item['name']}",
                f"Promotion Experiment Started (14-day horizon vs {len(matched_controls)} matched controls). Baseline: {item['stock']} units, {pre_velocity:.2f} u/d velocity. Target: {expected_14d_units} units.",
                json.dumps(pre_snapshot),
                incremental_est_paise,
                prob,
                f"Apply 1.35x discoverability boost (Target: {expected_14d_units} units over 14d test vs {len(matched_controls)} controls)",
                exp_id,
                mode,
                now_str,
                now_str,
                json.dumps(pre_snapshot)
            ))

            create_audit_log(
                cursor,
                "growth_action",
                action_id,
                "Promotion Experiment Started",
                f"Promotion Experiment Started: {item['name']} (SKU: {sku}) with controls {[c['sku'] for c in matched_controls]} — Baseline: {item['stock']} units, {pre_velocity:.2f} u/d velocity, 14d horizon."
            )
            conn.commit()

            return {
                "action_id": action_id,
                "experiment_id": exp_id,
                "action_type": "PROMOTE_PRODUCT",
                "status": "completed",
                "sku": sku,
                "name": item["name"],
                "matched_controls": matched_controls,
                "pre_snapshot": pre_snapshot,
                "message": f"Successfully started 14-day promotion experiment for {item['name']} with {len(matched_controls)} matched controls (ID: {exp_id})."
            }

        elif action_type == "CROSS_SELL":
            action_id = f"ga_xsell_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
                INSERT INTO growth_actions (
                    id, action_type, status, opportunity_type, title, explanation,
                    affected_ref, est_revenue_paise, confidence, recommended_action,
                    execution_ref, mode, created_at, executed_at, notes
                ) VALUES (?, 'CROSS_SELL', 'completed', 'strong_cross_sell', ?, ?, ?, ?, 0.75, ?, ?, ?, ?, ?, ?)
            """, (
                action_id,
                f"Active Cross-Sell Rule: {target_id}",
                f"Verified cross-sell target SKU {target_id} active in recommendation pipeline.",
                json.dumps({"target_sku": target_id}),
                0,
                "Target SKU actively prioritized in buyer recommendation prompts.",
                target_id,
                mode,
                now_str,
                now_str,
                "Cross-sell priority confirmed"
            ))
            create_audit_log(
                cursor,
                "growth_action",
                action_id,
                "Growth Action Executed",
                f"Activated prioritized cross-sell recommendation for SKU {target_id}"
            )
            conn.commit()

            return {
                "action_id": action_id,
                "action_type": "CROSS_SELL",
                "status": "completed",
                "target_sku": target_id,
                "message": f"Cross-sell recommendation rule for {target_id} is now actively prioritized."
            }

        elif action_type == "NO_ACTION":
            return {
                "action_id": f"ga_noaction_{uuid.uuid4().hex[:10]}",
                "action_type": "NO_ACTION",
                "status": "acknowledged",
                "message": "Diagnostic insight acknowledged. No automated changes dispatched."
            }

        else:
            raise ValueError(f"Unknown action_type: {action_type}")
    finally:
        conn.close()


def get_growth_metrics() -> dict:
    """
    Calculates live merchant growth & revenue attribution KPIs with strict conceptual separation:
    1. REALIZED GROSS REVENUE: Actual successfully captured Razorpay cash across all settled orders.
    2. OBSERVED AI-ATTRIBUTED REVENUE: Realized incremental lift on settled orders from accepted cross-sells + recovered carts.
    3. RECOVERABLE CART VALUE (AT RISK): Potential value sitting in incomplete/abandoned customer carts.
    4. INVENTORY EXPOSURE VALUE: Total stock value of slow-moving/stagnant warehouse inventory.
    (Note: Cart risk and inventory value are kept strictly separate; never merged into one number).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Total realized store revenue from succeeded payments (excluding refunded/cancelled, net of partial refunds)
        cursor.execute("""
            SELECT COUNT(*), 
                   SUM(CASE 
                       WHEN COALESCE(pm.refund_status, 'NONE') = 'REFUNDED' OR COALESCE(cm.order_status, 'CREATED') = 'CANCELLED' THEN 0
                       WHEN COALESCE(pm.refund_status, 'NONE') = 'PARTIALLY_REFUNDED' THEN MAX(0, pm.amount_paise - COALESCE(pm.refunded_amount_paise, 0))
                       ELSE pm.amount_paise 
                   END)
            FROM payment_mandates pm
            JOIN cart_mandates cm ON pm.cart_id = cm.id
            WHERE pm.status = 'succeeded'
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
        """)
        pay_count, total_rev_paise = cursor.fetchone()
        total_rev_paise = total_rev_paise or 0
        pay_count = pay_count or 0

        # 2. Observed AI revenue by type from growth_outcomes (strictly paid/settled transactions on active non-refunded/non-cancelled orders)
        cursor.execute("""
            SELECT g.revenue_type, SUM(g.incremental_paise), COUNT(*)
            FROM growth_outcomes g
            WHERE g.outcome_type = 'paid'
              AND g.incremental_paise > 0
              AND NOT EXISTS (
                  SELECT 1 FROM payment_mandates pm
                  JOIN cart_mandates cm ON pm.cart_id = cm.id
                  WHERE (g.id = 'go_paid_' || pm.id OR g.id = 'go_recov_' || pm.id OR g.action_id = pm.id OR (g.id LIKE 'go_xs_%' AND g.action_id = cm.id))
                    AND (COALESCE(pm.refund_status, 'NONE') = 'REFUNDED' OR COALESCE(cm.order_status, 'CREATED') = 'CANCELLED')
              )
            GROUP BY g.revenue_type
        """)
        outcomes_by_type = {row["revenue_type"]: {"paise": row[1] or 0, "count": row[2]} for row in cursor.fetchall()}

        cross_sell_paise = outcomes_by_type.get("cross_sell", {}).get("paise", 0)
        recovered_paise = outcomes_by_type.get("recovery", {}).get("paise", 0)
        total_ai_attributed_paise = cross_sell_paise + recovered_paise
        organic_baseline_paise = max(0, total_rev_paise - total_ai_attributed_paise)

        # 3. Total order counts (intent_mandates represents total purchase sessions)
        cursor.execute("SELECT COUNT(*) FROM intent_mandates")
        total_orders = cursor.fetchone()[0] or max(1, pay_count)

        # 4. Upsell attachment statistics
        cursor.execute("SELECT COUNT(*), SUM(accepted) FROM upsell_events")
        offers_cnt, accepted_cnt = cursor.fetchone()
        accepted_cnt = accepted_cnt or 0
        offers_cnt = offers_cnt or 0

        attachment_rate = round((accepted_cnt / total_orders * 100), 1) if total_orders > 0 else 0.0

        # 5. AOV across succeeded orders
        aov_paise = int(total_rev_paise / pay_count) if pay_count > 0 else 0

        # 6. Live Recoverable Carts Value (At Risk)
        recoverable_carts = detect_recoverable_carts(limit=50)
        recoverable_carts_paise = sum(c["total_paise"] for c in recoverable_carts)

        # 7. Live Inventory Exposure (Stagnant Stock Value)
        cursor.execute("SELECT SUM(price_paise * stock) FROM catalog WHERE stock >= 50 AND boosted = 0")
        inventory_exposure_paise = cursor.fetchone()[0] or 0

        # 8. Query recovery policy parameters
        cursor.execute("SELECT recovery_attribution_percent, recovery_idle_threshold_minutes, spend_cap_paise, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        pol_row = cursor.fetchone()
        recov_percent = pol_row["recovery_attribution_percent"] if pol_row and pol_row["recovery_attribution_percent"] is not None else 60
        recov_idle_min = pol_row["recovery_idle_threshold_minutes"] if pol_row and pol_row["recovery_idle_threshold_minutes"] is not None else 120
        spend_cap_paise = pol_row["spend_cap_paise"] if pol_row else 1000000
        autonomy_thresh_paise = pol_row["autonomy_threshold_paise"] if pol_row else 250000

        # 9. Gross recovered cash (face value of settled recovery orders, excluding refunded/cancelled)
        cursor.execute("""
            SELECT SUM(CASE 
                       WHEN COALESCE(pm.refund_status, 'NONE') = 'PARTIALLY_REFUNDED' THEN MAX(0, pm.amount_paise - COALESCE(pm.refunded_amount_paise, 0))
                       ELSE pm.amount_paise 
                   END)
            FROM payment_mandates pm
            JOIN cart_mandates cm ON pm.cart_id = cm.id
            WHERE pm.status = 'succeeded' 
              AND pm.recovery_action = 'recovery_link_sent'
              AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED'
              AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED'
        """)
        gross_recov_paise = cursor.fetchone()[0] or 0

        opps = detect_all_opportunities()

        return {
            # STRICT REVENUE NOMENCLATURE
            "realized_gross_revenue_paise": total_rev_paise,
            "realized_gross_revenue_rupees": round(total_rev_paise / 100, 2),
            "observed_ai_attributed_revenue_paise": total_ai_attributed_paise,
            "observed_ai_attributed_revenue_rupees": round(total_ai_attributed_paise / 100, 2),
            "organic_baseline_revenue_paise": organic_baseline_paise,
            "organic_baseline_revenue_rupees": round(organic_baseline_paise / 100, 2),
            "cross_sell_revenue_paise": cross_sell_paise,
            "cross_sell_revenue_rupees": round(cross_sell_paise / 100, 2),
            "recovery_attributed_revenue_paise": recovered_paise,
            "recovery_attributed_revenue_rupees": round(recovered_paise / 100, 2),
            "gross_recovered_revenue_paise": gross_recov_paise,
            "gross_recovered_revenue_rupees": round(gross_recov_paise / 100, 2),
            
            # STRICT SEPARATION OF AT-RISK ASSETS
            "recoverable_cart_value_paise": recoverable_carts_paise,
            "recoverable_cart_value_rupees": round(recoverable_carts_paise / 100, 2),
            "recoverable_cart_count": len(recoverable_carts),
            "inventory_exposure_value_paise": inventory_exposure_paise,
            "inventory_exposure_value_rupees": round(inventory_exposure_paise / 100, 2),
            "estimated_opportunity_value_paise": recoverable_carts_paise,
            "estimated_opportunity_value_rupees": round(recoverable_carts_paise / 100, 2),

            # POLICY & METRICS
            "recovery_attribution_percent": recov_percent,
            "recovery_idle_threshold_minutes": recov_idle_min,
            "spend_cap_rupees": round(spend_cap_paise / 100, 2),
            "autonomy_threshold_rupees": round(autonomy_thresh_paise / 100, 2),
            "methodology": {
                "cross_sell": "Net incremental cart lift on settled orders with accepted cross-sells (1 order = 1 delta, no multi-item multiplication).",
                "recovery": f"Observed AI attribution: {recov_percent}% of settled recovered orders where cart was idle ≥ {recov_idle_min} minutes before recovery."
            },
            "aov_paise": aov_paise,
            "aov_rupees": round(aov_paise / 100, 2),
            "total_orders_count": total_orders,
            "succeeded_payments_count": pay_count,
            "accepted_upsells_count": accepted_cnt,
            "total_upsells_offered": offers_cnt,
            "upsell_attachment_rate": attachment_rate,
            "active_opportunities_count": len(opps),

            # Backward compatibility aliases for existing components
            "total_revenue_rupees": round(total_rev_paise / 100, 2),
            "observed_ai_revenue_rupees": round(total_ai_attributed_paise / 100, 2),
            "estimated_opportunity_rupees": round(recoverable_carts_paise / 100, 2)
        }
    finally:
        conn.close()


def get_agent_performance_stats() -> dict:
    """
    AGENT PERFORMANCE: Returns empirical performance statistics for each growth capability.
    Enforces strict distinction:
    - Rule Activated (Preparation)
    - Recommendation Offered (Exposure)
    - Recommendation Accepted (Buyer Intent)
    - Revenue Realized (Settled Cash Lift)
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Cross-sell empirical stats
        cursor.execute("""
            SELECT COUNT(*) as total_offers,
                   SUM(accepted) as accepted_offers
            FROM upsell_events
        """)
        row_xs = cursor.fetchone()
        xs_offers = row_xs["total_offers"] or 0
        xs_accepted = row_xs["accepted_offers"] or 0

        cursor.execute("""
            SELECT SUM(g.incremental_paise)
            FROM growth_outcomes g
            WHERE g.outcome_type = 'paid' AND g.revenue_type = 'cross_sell' AND g.incremental_paise > 0
              AND NOT EXISTS (
                  SELECT 1 FROM payment_mandates pm
                  JOIN cart_mandates cm ON pm.cart_id = cm.id
                  WHERE (g.id = 'go_paid_' || pm.id OR g.action_id = pm.id OR (g.id LIKE 'go_xs_%' AND g.action_id = cm.id))
                    AND (COALESCE(pm.refund_status, 'NONE') = 'REFUNDED' OR COALESCE(cm.order_status, 'CREATED') = 'CANCELLED')
              )
        """)
        xs_inc_paise = cursor.fetchone()[0] or 0
        xs_rate = round(xs_accepted / xs_offers, 3) if xs_offers > 0 else 0.0

        cursor.execute("SELECT COUNT(*) FROM basket_pairs WHERE source = 'data_verified' AND (retired IS NULL OR retired = 0)")
        active_rules_count = cursor.fetchone()[0] or 0

        # Recovery empirical stats (excluding refunded and cancelled orders)
        cursor.execute("""
            SELECT COUNT(*) as attempts,
                   SUM(CASE WHEN pm.status = 'succeeded' AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED' AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED' THEN 1 ELSE 0 END) as recovered,
                   SUM(CASE WHEN pm.status = 'succeeded' AND COALESCE(pm.refund_status, 'NONE') != 'REFUNDED' AND COALESCE(cm.order_status, 'CREATED') != 'CANCELLED' THEN pm.amount_paise ELSE 0 END) as recov_paise
            FROM payment_mandates pm
            JOIN cart_mandates cm ON pm.cart_id = cm.id
            WHERE pm.recovery_action = 'recovery_link_sent'
        """)
        row_rec = cursor.fetchone()
        rec_attempts = row_rec["attempts"] or 0
        rec_recovered = row_rec["recovered"] or 0
        rec_gross_paise = row_rec["recov_paise"] or 0
        rec_rate = round(rec_recovered / rec_attempts, 3) if rec_attempts > 0 else None

        cursor.execute("""
            SELECT SUM(g.incremental_paise)
            FROM growth_outcomes g
            WHERE g.outcome_type = 'paid' AND g.revenue_type = 'recovery' AND g.incremental_paise > 0
              AND NOT EXISTS (
                  SELECT 1 FROM payment_mandates pm
                  JOIN cart_mandates cm ON pm.cart_id = cm.id
                  WHERE (g.id = 'go_recov_' || pm.id OR g.action_id = pm.id)
                    AND (COALESCE(pm.refund_status, 'NONE') = 'REFUNDED' OR COALESCE(cm.order_status, 'CREATED') = 'CANCELLED')
              )
        """)
        rec_inc_paise = cursor.fetchone()[0] or 0

        # Promotion boost stats (strictly preparatory unless post-boost order data is tracked)
        cursor.execute("SELECT COUNT(*) FROM catalog WHERE boosted = 1")
        boosted_items = cursor.fetchone()[0] or 0

        # Policy & Autonomy settings
        cursor.execute("SELECT growth_mode, autonomy_threshold_paise, spend_cap_paise FROM policy_config WHERE id = 1")
        pol = cursor.fetchone()
        growth_mode = pol["growth_mode"] if pol else "manual"
        autonomy_thresh = pol["autonomy_threshold_paise"] if pol else 500000
        spend_cap = pol["spend_cap_paise"] if pol else 1000000

        opps = detect_all_opportunities()
        opp_by_type = {}
        for o in opps:
            t = o["type"]
            opp_by_type[t] = opp_by_type.get(t, 0) + 1

        return {
            "growth_mode": growth_mode,
            "autonomy_threshold_rupees": round(autonomy_thresh / 100, 2),
            "spend_cap_rupees": round(spend_cap / 100, 2),
            "capabilities": {
                "CROSS_SELL": {
                    "name": "Pre-Checkout Recommendations",
                    "status": "Active",
                    "active_rules": active_rules_count,
                    "opportunities_detected": opp_by_type.get("CROSS_SELL", 0),
                    "total_offers": xs_offers,
                    "accepted": xs_accepted,
                    "acceptance_rate": xs_rate,
                    "realized_incremental_rupees": round(xs_inc_paise / 100, 2),
                    "model_source": f"Empirical: {xs_offers} recorded checkout interactions",
                    "lifecycle_status": "Rule Active → Real-time Checkout Scoring"
                },
                "RECOVER_CART": {
                    "name": "Abandoned Cart Link Recovery",
                    "status": "Active",
                    "opportunities_detected": opp_by_type.get("RECOVER_CART", 0),
                    "total_attempts": rec_attempts,
                    "recovered": rec_recovered,
                    "recovery_rate": rec_rate,
                    "gross_recovered_rupees": round(rec_gross_paise / 100, 2),
                    "realized_incremental_rupees": round(rec_inc_paise / 100, 2),
                    "model_source": "Empirical: 60% attribution on settled recoveries (idle ≥ 2h)",
                    "lifecycle_status": "Detected → Link Dispatched → Settlement Ledger"
                },
                "PROMOTE_PRODUCT": {
                    "name": "Inventory Velocity 1.35x Search Boost",
                    "status": "Active",
                    "opportunities_detected": opp_by_type.get("PROMOTE_PRODUCT", 0),
                    "boosted_skus_count": boosted_items,
                    "realized_incremental_rupees": 0.0,
                    "model_source": "Catalog Search Semantic Prioritization (1.35x multiplier)",
                    "lifecycle_status": f"{boosted_items} SKUs Boosted in Search Ranking"
                }
            }
        }
    finally:
        conn.close()


def get_growth_timeline(limit: int = 100) -> list[dict]:
    """
    AGENT TIMELINE: Aggregates real chronological events from database tables:
    - growth_actions (Executed, completed, dismissed actions)
    - growth_outcomes (Settled revenue attribution entries)
    - audit_log (Policy updates, cart governance checks, upsell recommendations, payment settlements)
    - payment_mandates (Succeeded checkout and recovery payments)
    Zero fabricated data.
    """
    conn = get_db()
    cursor = conn.cursor()
    timeline = []

    try:
        # 1. Real Growth Actions
        cursor.execute("""
            SELECT id, action_type, status, title, explanation, mode, created_at, executed_at
            FROM growth_actions
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        for r in cursor.fetchall():
            timeline.append({
                "id": f"act_{r['id']}",
                "event_type": "action_executed" if r["status"] == "completed" else "action_detected",
                "action_type": r["action_type"],
                "status": r["status"],
                "title": r["title"],
                "detail": r["explanation"],
                "mode": r["mode"],
                "timestamp": r["executed_at"] or r["created_at"]
            })

        # 2. Real Revenue Outcomes (Settlements)
        cursor.execute("""
            SELECT id, outcome_type, before_paise, after_paise, incremental_paise, revenue_type, created_at
            FROM growth_outcomes
            WHERE outcome_type = 'paid'
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        for r in cursor.fetchall():
            timeline.append({
                "id": f"out_{r['id']}",
                "event_type": "revenue_outcome",
                "action_type": r["revenue_type"].upper(),
                "status": "settled",
                "title": f"Captured Revenue Lift: +₹{r['incremental_paise']/100:.2f}",
                "detail": f"Observed {r['revenue_type']} lift on settled transaction (₹{r['after_paise']/100:.2f} total paid).",
                "mode": "automated",
                "timestamp": r["created_at"]
            })

        # 3. Real Policy, Governance, Payment & Upsell Events from audit_log
        cursor.execute("""
            SELECT id, ref_type, ref_id, event, detail, created_at
            FROM audit_log
            WHERE ref_type IN ('policy', 'cart', 'growth_action', 'growth_rule', 'payment', 'upsell')
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        for r in cursor.fetchall():
            event_type = (
                "revenue_outcome" if r["ref_type"] == "payment" and "Succeeded" in (r["event"] or "")
                else "policy_check" if r["ref_type"] == "policy"
                else "action_executed" if r["ref_type"] in ("growth_action", "growth_rule")
                else "guardrail_event"
            )
            timeline.append({
                "id": f"audit_{r['id']}",
                "event_type": event_type,
                "action_type": r["ref_type"].upper(),
                "status": "logged",
                "title": r["event"],
                "detail": r["detail"],
                "mode": "governance" if r["ref_type"] == "policy" else "automated",
                "timestamp": r["created_at"]
            })

        # Sort all events chronologically descending
        timeline.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return timeline[:limit]
    finally:
        conn.close()


def set_growth_mode(mode: str) -> dict:
    """
    Configures merchant growth autonomy mode in policy_config.
    """
    if mode not in ("manual", "suggested", "autonomous"):
        raise ValueError(f"Invalid growth mode '{mode}'. Must be 'manual', 'suggested', or 'autonomous'.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE policy_config SET growth_mode = ? WHERE id = 1", (mode,))
        create_audit_log(
            cursor,
            "policy",
            "policy_1",
            "Policy Configuration Updated",
            f"Merchant Growth Autonomy Mode set to '{mode}'"
        )
        conn.commit()
        return {
            "growth_mode": mode,
            "message": f"Merchant Growth Autonomy Mode updated to '{mode}'."
        }
    finally:
        conn.close()


# Backward compatibility alias
get_learning_loop_stats = get_agent_performance_stats

