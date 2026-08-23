import os
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db
from backend.recommendations.embedding_engine import find_substitutes

load_dotenv()


class SubstituteChoice(BaseModel):
    sku: str
    reason: str


def find_substitute(original_item: dict, budget_remaining_paise: int = None) -> dict | None:
    """
    When an item is missing or out of stock, uses the Semantic Embedding Engine
    to return top-ranked in-stock substitutes, and uses the Substitution Agent
    to select the best fit and write a natural, grounded explanation.

    Returns dict with keys:
      sku, name, price_paise, category, similarity_score, final_score, reason,
      candidates (top_k list), original_sku, original_name
    """
    original_sku = original_item.get("sku", "")
    original_name = original_item.get("name", original_sku)

    # 1. Query the Semantic Embedding Engine for top 3 ranked in-stock substitutes
    candidates = find_substitutes(
        missing_item_or_description=original_sku or original_name,
        budget_remaining_paise=budget_remaining_paise,
        top_k=3,
        min_similarity=0.40
    )

    if not candidates:
        return None

    # If only 1 candidate found, use its pre-computed embedding reason directly
    if len(candidates) == 1:
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "similarity_score": c.get("similarity_score", 0.0),
            "final_score": c.get("final_score", 0.0),
            "reason": c.get("reason", f"Best semantic in-stock match for {original_name}."),
            "candidates": candidates,
            "original_sku": original_sku,
            "original_name": original_name,
        }

    from backend.engine.llm import generate_structured, get_available_providers
    if not get_available_providers():
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "similarity_score": c.get("similarity_score", 0.0),
            "final_score": c.get("final_score", 0.0),
            "reason": c.get("reason", f"Best semantic match for {original_name}."),
            "candidates": candidates,
            "original_sku": original_sku,
            "original_name": original_name,
        }

    candidate_str = "\n".join(
        f"- SKU: {c['sku']}, Name: {c['name']}, Price: ₹{c['price_paise']/100:.0f}, "
        f"Similarity: {c.get('similarity_score', 0)*100:.0f}%"
        + (" [BOOSTED PARTNER]" if c.get("boosted") else "")
        for c in candidates
    )

    system_instruction = f"""
    You are an AI Substitution Agent for an e-commerce store.
    The customer's requested item is unavailable or out of stock:
    - Item: {original_name} ({original_sku})

    Here are the top semantic in-stock alternatives identified by our embedding engine:
    {candidate_str}

    Rules:
    1. You MUST choose EXACTLY ONE SKU from the list above. Never invent any other SKU.
    2. Prefer higher similarity and boosted partner items when quality/suitability is comparable.
    3. Write a single, helpful 1-sentence reason explaining why this replacement fits the customer's need.
    """

    try:
        choice = generate_structured(
            prompt=f"Pick the best substitute for {original_name}.",
            schema=SubstituteChoice,
            system_prompt=system_instruction
        )
        candidate_map = {c["sku"]: c for c in candidates}

        if choice.sku in candidate_map:
            chosen = candidate_map[choice.sku]
            return {
                "sku": chosen["sku"],
                "name": chosen["name"],
                "price_paise": chosen["price_paise"],
                "category": chosen["category"],
                "similarity_score": chosen.get("similarity_score", 0.0),
                "final_score": chosen.get("final_score", 0.0),
                "reason": choice.reason,
                "candidates": candidates,
                "original_sku": original_sku,
                "original_name": original_name,
            }
    except Exception as e:
        print(f"Error in substitution LLM selection: {e}")

    # Fallback to top ranked candidate
    c = candidates[0]
    return {
        "sku": c["sku"],
        "name": c["name"],
        "price_paise": c["price_paise"],
        "category": c["category"],
        "similarity_score": c.get("similarity_score", 0.0),
        "final_score": c.get("final_score", 0.0),
        "reason": c.get("reason", f"Closest semantic in-stock match for {original_name}."),
        "candidates": candidates,
        "original_sku": original_sku,
        "original_name": original_name,
    }
