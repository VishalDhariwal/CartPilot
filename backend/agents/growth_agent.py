import os
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.recommendations.lift_engine import find_cross_sell

load_dotenv()


class UpsellChoice(BaseModel):
    suggest: bool
    sku: str
    reason: str


def generate_upsell(cart_items: list) -> dict | None:
    """
    Data-driven cross-sell recommendation using Market Basket Analysis:
      Layer 1 (Lift Engine): query basket_pairs derived from historical orders
                             (support, confidence, lift calculation + boost multiplier)
      Layer 2 (Growth Agent): given top-3 ranked candidates, LLM selects best
                             and writes natural, contextual copy grounded in the cart.

    Returns dict with keys:
      sku, name, price_paise, category, lift, support, final_score, reason, candidates
    """
    if not cart_items:
        return None

    # Layer 1: Query Market Basket Lift Engine for top 3 candidates
    candidates = find_cross_sell(cart_items, top_k=3)

    if not candidates:
        return None

    # If only 1 candidate or no LLM key, use pre-calculated lift reason
    api_key = os.getenv("OPENAI_API_KEY")
    if len(candidates) == 1 or not api_key:
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "lift": c.get("lift", 1.0),
            "support": c.get("support", 0.0),
            "final_score": c.get("final_score", 1.0),
            "reason": c.get("reason", "Frequently purchased together with items in your cart."),
            "candidates": candidates,
        }

    # Layer 2: LLM picks the best among top-3 candidates and writes a natural reason
    client = OpenAI(api_key=api_key)

    candidate_str = "\n".join(
        f"- SKU: {c['sku']}, Name: {c['name']}, Price: ₹{c['price_paise']/100:.0f}, "
        f"Lift Score: {c.get('lift', 1.0):.2f}x affinity with {c.get('trigger_name', 'cart')}"
        + (" [BOOSTED PARTNER]" if c.get("boosted") else "")
        for c in candidates
    )

    cart_summary = ", ".join(
        f"{item.get('name', item.get('sku'))} (×{item.get('qty', 1)}, ₹{item.get('price_paise', 0)/100:.0f})"
        for item in cart_items
    )

    system_instruction = f"""
    You are an AI Growth Agent for an e-commerce store. Your job is to select the single best
    cross-sell recommendation from a pre-vetted list computed by our Market Basket Lift Engine.

    Current cart contents: {cart_summary}

    Candidate cross-sell items (all real, in-stock catalog items with measured affinity):
    {candidate_str}

    Rules:
    1. Pick EXACTLY ONE SKU from the candidate list above. Do not invent or alter any SKU.
    2. Prefer higher lift scores and boosted partner items when quality is comparable.
    3. Write a single natural, specific 1-sentence reason that explains why this item pairs with the cart contents.
    4. Set suggest=true.
    """

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": "Pick the best complementary cross-sell item for this cart."}
            ],
            response_format=UpsellChoice,
            temperature=0.2
        )

        choice = completion.choices[0].message.parsed
        if choice.suggest and choice.sku:
            candidate_map = {c["sku"]: c for c in candidates}
            if choice.sku in candidate_map:
                chosen = candidate_map[choice.sku]
                return {
                    "sku": chosen["sku"],
                    "name": chosen["name"],
                    "price_paise": chosen["price_paise"],
                    "category": chosen["category"],
                    "lift": chosen.get("lift", 1.0),
                    "support": chosen.get("support", 0.0),
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
        "lift": c.get("lift", 1.0),
        "support": c.get("support", 0.0),
        "final_score": c.get("final_score", 1.0),
        "reason": c.get("reason", "Top complementary item based on customer purchase history."),
        "candidates": candidates,
    }
