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

    # Candidate 0 is mathematically the top vector embedding match
    c = candidates[0]
    sim_pct = int(c.get("similarity_score", 0.9) * 100)
    boost_note = " (partner item)" if c.get("boosted") else ""
    reason = f"Best in-stock alternative for {original_name} with {sim_pct}% catalog similarity{boost_note}."

    return {
        "sku": c["sku"],
        "name": c["name"],
        "price_paise": c["price_paise"],
        "category": c["category"],
        "similarity_score": c.get("similarity_score", 0.0),
        "final_score": c.get("final_score", 0.0),
        "reason": reason,
        "candidates": candidates,
        "original_sku": original_sku,
        "original_name": original_name,
    }
