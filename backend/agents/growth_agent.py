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

    from backend.engine.llm import generate_structured
    try:
        choice = generate_structured(
            prompt="Pick the best complementary cross-sell item for this cart.",
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
