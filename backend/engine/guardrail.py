import json
from backend.db import get_db

def validate_cart(intent_id: str, items: list, total_paise: int) -> dict:
    """
    Validates the proposed cart against the global policy configuration.
    Returns a dict with 'status' ("approved", "pending_confirmation", or "blocked"), 'reason', and 'reversible'.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories, autonomy_threshold_paise FROM policy_config WHERE id = 1")
        policy = cursor.fetchone()
        
        if not policy:
            return {
                "status": "blocked",
                "reason": "System error: Policy configuration not found.",
                "reversible": True
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

        # 1. Check Hard Spend Cap
        if total_paise > effective_spend_cap:
            return {
                "status": "blocked",
                "reason": f"Cart total (₹{total_paise/100:.2f}) exceeds spend cap (₹{effective_spend_cap/100:.0f}).",
                "reversible": True
            }
            
        # 2. Check SKU Categories
        for item in items:
            cursor.execute("SELECT category FROM catalog WHERE sku = ?", (item["sku"],))
            cat_row = cursor.fetchone()
            if not cat_row:
                return {
                    "status": "blocked",
                    "reason": f"SKU {item['sku']} not found in catalog.",
                    "reversible": True
                }
            if cat_row["category"] not in allowed_categories:
                return {
                    "status": "blocked",
                    "reason": f"SKU {item['sku']} is in category '{cat_row['category']}' which is not allowed by active merchant policy.",
                    "reversible": True
                }
                
        # 3. Check Autonomy Threshold (Reserve Pay Spending-Limit Pattern)
        if total_paise >= autonomy_threshold_paise:
            return {
                "status": "pending_confirmation",
                "reason": f"High-Value Order (₹{total_paise/100:.2f}) meets or exceeds merchant autonomy threshold (₹{autonomy_threshold_paise/100:.0f}). Requires explicit authorization.",
                "reversible": True
            }

        return {
            "status": "approved",
            "reason": f"Within spend cap (₹{total_paise/100:.2f} <= ₹{spend_cap_paise/100:.0f}); all SKUs allowed; auto-approved under autonomy threshold (₹{autonomy_threshold_paise/100:.0f}).",
            "reversible": True
        }
    finally:
        conn.close()

