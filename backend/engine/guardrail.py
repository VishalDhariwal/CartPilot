import json
from typing import Optional, Tuple, List, Dict, Any
from backend.db import get_db

# ── Policy Constants & Ratios ───────────────────────────────────────────────
# Autonomy ratio for irreversible purchases (30% of standard autonomy threshold for auto-approval)
IRREVERSIBLE_AUTONOMY_RATIO: float = 0.30

# Maximum hard cap for irreversible items before triggering hard block (₹5,000 in paise)
IRREVERSIBLE_HARD_BLOCK_CAP_PAISE: int = 500000

# Explicit category classification for reversibility
IRREVERSIBLE_CATEGORIES = {
    "digital", "gift-cards", "custom", "customized", "clearance", "restricted_items", "perishable"
}


def is_category_allowed(category: str, allowed_categories: list) -> bool:
    """
    Checks if a product category is permitted under the active policy.
    Supports normalized string matching (e.g. 'skin-care' == 'skincare'),
    prefix/hierarchical matching ('clothing' covers 'mens-shirts', 'womens-dresses'),
    and wildcards.
    """
    if not category:
        return False
    if category == "restricted_items":
        return False
    if "*" in allowed_categories or "all" in allowed_categories:
        return True
    if category in allowed_categories:
        return True

    def normalize(c: str) -> str:
        return c.lower().replace("-", "").replace("_", "").replace(" ", "")

    norm_cat = normalize(category)
    norm_allowed = [normalize(a) for a in allowed_categories]

    if norm_cat in norm_allowed:
        return True

    # Substring / hierarchical containment
    for a, na in zip(allowed_categories, norm_allowed):
        if na in norm_cat or norm_cat in na:
            return True

    # Semantic category hierarchy
    category_synonyms = {
        "skincare": ["skincare", "skin-care", "beauty", "cosmetics"],
        "clothing": ["clothing", "mens-shirts", "womens-dresses", "tops", "mens-shoes", "womens-shoes", "shoes"],
        "home": ["home", "home-decoration", "kitchen-accessories", "furniture"],
        "sports": ["sports", "sports-accessories"],
        "accessories": ["accessories", "mobile-accessories", "sports-accessories", "sunglasses", "womens-jewellery", "womens-bags", "mens-watches", "womens-watches"],
        "electronics": ["electronics", "laptops", "smartphones", "tablets", "mobile-accessories"],
    }
    for parent, children in category_synonyms.items():
        if normalize(parent) in norm_allowed:
            if any(normalize(ch) == norm_cat for ch in children):
                return True

    return False


def recompute_and_sanitize_cart(raw_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """
    Zero-Trust Guardrail Recomputation:
    Never trusts prices, totals, names, or categories handed in by the LLM.
    Looks up authoritative data directly from the catalog table for each SKU and quantity:
      1. Fetches real price_paise, category, name, and live stock.
      2. Validates live inventory (stock >= qty).
      3. Recomputes item total = price_paise * qty.
      4. Calculates the true authoritative cart total_paise = sum(item_total).
    
    Returns: (sanitized_items, authoritative_total_paise, list_of_errors)
    """
    if not raw_items:
        return [], 0, ["Cart has no items."]

    conn = get_db()
    cursor = conn.cursor()
    try:
        sanitized_items = []
        total_paise = 0
        errors = []

        for it in raw_items:
            sku = it.get("sku")
            if not sku:
                errors.append("Item missing SKU identifier.")
                continue

            try:
                qty = max(1, int(it.get("qty", 1)))
            except (ValueError, TypeError):
                qty = 1

            cursor.execute(
                "SELECT sku, name, price_paise, stock, category, merchant, image_url, description FROM catalog WHERE sku = ?",
                (sku,)
            )
            cat_row = cursor.fetchone()
            if not cat_row:
                errors.append(f"SKU '{sku}' not found in catalog.")
                continue

            price_paise = cat_row["price_paise"]
            stock = cat_row["stock"]
            name = cat_row["name"]
            category = cat_row["category"]

            if stock < qty:
                errors.append(f"SKU '{sku}' ({name}) has insufficient stock: requested {qty}, available {stock}.")
                continue

            item_total = price_paise * qty
            total_paise += item_total

            sanitized_items.append({
                "sku": sku,
                "name": name,
                "qty": qty,
                "price_paise": price_paise,
                "category": category,
                "item_total_paise": item_total,
                "image_url": cat_row["image_url"] or "",
                "description": cat_row["description"] or ""
            })

        return sanitized_items, total_paise, errors
    finally:
        conn.close()


def classify_reversibility(items: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Deterministic Reversibility Classifier:
    Examines product categories against static IRREVERSIBLE_CATEGORIES.
    Returns (is_reversible, reason).
    """
    for it in items:
        cat = (it.get("category") or "").lower()
        if cat in IRREVERSIBLE_CATEGORIES:
            return False, f"Contains non-returnable / irreversible category '{cat}'."
    return True, "All items are standard returnable/reversible goods."


def validate_cart(intent_id: Optional[str], items: list, total_paise: Optional[int] = None) -> dict:
    """
    Zero-Trust Guardrail Engine:
    Validates cart against catalog authority and global policy.
    Supports 3-tier deterministic decision matrix:
      - 'approved': Auto-approved within spending and autonomy thresholds.
      - 'pending_confirmation': Held for human review / explicit approval.
      - 'blocked': Hard rejection with explainable logged reason.
    """
    # 1. Independent catalog lookup and recomputation
    sanitized_items, recomputed_total, sanitize_errors = recompute_and_sanitize_cart(items)
    if sanitize_errors:
        return {
            "status": "blocked",
            "reason": f"Inventory/Catalog Validation Failed: {'; '.join(sanitize_errors)}",
            "reversible": True,
            "sanitized_items": sanitized_items,
            "total_paise": recomputed_total
        }

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        policy = cursor.fetchone()
        
        if not policy:
            return {
                "status": "blocked",
                "reason": "System error: Policy configuration not found.",
                "reversible": True,
                "sanitized_items": sanitized_items,
                "total_paise": recomputed_total
            }
            
        spend_cap_paise = policy["spend_cap_paise"]
        allowed_categories = json.loads(policy["allowed_categories"])
        autonomy_threshold_paise = policy["autonomy_threshold_paise"] or 500000
        
        # Check Intent-Specific Spend Cap if provided
        effective_spend_cap = spend_cap_paise
        if intent_id:
            cursor.execute("SELECT spend_cap_paise FROM intent_mandates WHERE id = ?", (intent_id,))
            intent_row = cursor.fetchone()
            if intent_row and intent_row["spend_cap_paise"]:
                effective_spend_cap = min(spend_cap_paise, intent_row["spend_cap_paise"])

        # 2. Check Hard Spend Cap
        if recomputed_total > effective_spend_cap:
            return {
                "status": "blocked",
                "reason": f"Cart total (₹{recomputed_total/100:.2f}) exceeds spend cap (₹{effective_spend_cap/100:.0f}).",
                "reversible": True,
                "sanitized_items": sanitized_items,
                "total_paise": recomputed_total
            }
            
        # 3. Check SKU Allowed Categories
        for item in sanitized_items:
            cat = item.get("category", "")
            if not is_category_allowed(cat, allowed_categories):
                return {
                    "status": "blocked",
                    "reason": f"SKU '{item['sku']}' is in category '{cat}' which is not allowed by active merchant policy.",
                    "reversible": True,
                    "sanitized_items": sanitized_items,
                    "total_paise": recomputed_total
                }

        # 4. Classify Reversibility & Apply 3-Tier Thresholds
        is_reversible, rev_reason = classify_reversibility(sanitized_items)

        if not is_reversible:
            # Irreversible purchases have tighter autonomy ceiling and a hard upper block cap
            irreversible_auto_limit = int(autonomy_threshold_paise * IRREVERSIBLE_AUTONOMY_RATIO)
            
            # Hard Block for nonsensical/hallucinated high value irreversible orders
            if recomputed_total > IRREVERSIBLE_HARD_BLOCK_CAP_PAISE:
                return {
                    "status": "blocked",
                    "reason": f"Irreversible purchase (₹{recomputed_total/100:.2f}) exceeds maximum permitted irreversible ceiling (₹{IRREVERSIBLE_HARD_BLOCK_CAP_PAISE/100:.0f}). Rejected outright.",
                    "reversible": False,
                    "sanitized_items": sanitized_items,
                    "total_paise": recomputed_total
                }
            
            # Held for Review if over strict autonomy ratio
            if recomputed_total > irreversible_auto_limit:
                return {
                    "status": "pending_confirmation",
                    "reason": f"Irreversible purchase (₹{recomputed_total/100:.2f}) exceeds strict autonomy threshold (₹{irreversible_auto_limit/100:.0f}, {int(IRREVERSIBLE_AUTONOMY_RATIO*100)}% of standard limit). Requires explicit authorization.",
                    "reversible": False,
                    "sanitized_items": sanitized_items,
                    "total_paise": recomputed_total
                }

            return {
                "status": "approved",
                "reason": f"Within irreversible spend cap (₹{recomputed_total/100:.2f} <= ₹{irreversible_auto_limit/100:.0f}); all SKUs allowed and verified.",
                "reversible": False,
                "sanitized_items": sanitized_items,
                "total_paise": recomputed_total
            }

        # Standard Reversible Autonomy Threshold
        if recomputed_total >= autonomy_threshold_paise:
            return {
                "status": "pending_confirmation",
                "reason": f"High-Value Order (₹{recomputed_total/100:.2f}) meets or exceeds merchant autonomy threshold (₹{autonomy_threshold_paise/100:.0f}). Requires explicit authorization.",
                "reversible": True,
                "sanitized_items": sanitized_items,
                "total_paise": recomputed_total
            }

        return {
            "status": "approved",
            "reason": f"Within spend cap (₹{recomputed_total/100:.2f} <= ₹{spend_cap_paise/100:.0f}); all SKUs allowed; auto-approved under autonomy threshold (₹{autonomy_threshold_paise/100:.0f}).",
            "reversible": True,
            "sanitized_items": sanitized_items,
            "total_paise": recomputed_total
        }
    finally:
        conn.close()
