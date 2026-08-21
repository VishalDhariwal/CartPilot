import json
from backend.db import get_db

def validate_cart(intent_id: str, items: list, total_paise: int) -> dict:
    """
    Validates the proposed cart against the global policy configuration.
    Returns a dict with 'status' ("approved" or "blocked"), 'reason', and 'reversible'.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT spend_cap_paise, allowed_categories FROM policy_config WHERE id = 1")
        policy = cursor.fetchone()
        
        if not policy:
            return {
                "status": "blocked",
                "reason": "System error: Policy configuration not found.",
                "reversible": True
            }
            
        spend_cap_paise = policy["spend_cap_paise"]
        allowed_categories = json.loads(policy["allowed_categories"])
        
        # 1. Check Spend Cap
        if total_paise > spend_cap_paise:
            return {
                "status": "blocked",
                "reason": f"Cart total ({total_paise} paise) exceeds global spend cap ({spend_cap_paise} paise).",
                "reversible": True
            }
            
        # 2. Check SKU Categories (This is a simplified check assuming we fetched catalog data before passing here,
        # but to be truly gated, guardrail should verify the SKUs independently).
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
                    "reason": f"SKU {item['sku']} is in category '{cat_row['category']}' which is not allowed.",
                    "reversible": True
                }
                
        return {
            "status": "approved",
            "reason": f"Within spend cap ({total_paise} <= {spend_cap_paise}); all SKUs in allowed categories.",
            "reversible": True
        }
    finally:
        conn.close()
