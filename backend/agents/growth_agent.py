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

    # Layer 2: LLM picks the best among candidates and writes a contextual reason
    client = OpenAI(api_key=api_key)

    candidate_lines = []
    for c in candidates:
        is_boosted = " [BOOSTED PARTNER]" if c.get("boosted") else ""
        if c.get("source") == "data_verified" and c.get("lift") is not None:
            evidence = f"Data-Verified ({c['lift']:.2f}x lift across {c.get('co_occurrence_count', 0)} orders)"
        else:
            evidence = f"AI-Suggested Prior ({c.get('reasoning') or 'Curated complement'})"

        candidate_lines.append(
            f"- SKU: {c['sku']}, Name: {c['name']}, Price: ₹{c['price_paise']/100:.0f}, Evidence: {evidence}{is_boosted}"
        )

    candidate_str = "\n".join(candidate_lines)

    cart_summary = ", ".join(
        f"{item.get('name', item.get('sku'))} (×{item.get('qty', 1)}, ₹{item.get('price_paise', 0)/100:.0f})"
        for item in cart_items
    )

    system_instruction = f"""
    You are an AI Growth Merchandising Agent for an e-commerce store. Your job is to select the single best
    cross-sell recommendation from a pre-vetted list computed by our Hybrid Growth Engine.

    Current cart contents: {cart_summary}

    Candidate cross-sell items (all real, in-stock catalog items):
    {candidate_str}

    Rules:
    1. Pick EXACTLY ONE SKU from the candidate list above. Do not invent or alter any SKU.
    2. Prefer Data-Verified rules and boosted partner items when relevance is comparable.
    3. Write a single natural, specific 1-sentence customer-facing reason explaining why this item pairs with the cart.
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
