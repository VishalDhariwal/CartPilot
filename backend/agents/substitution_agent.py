import os
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db

load_dotenv()


class SubstituteChoice(BaseModel):
    sku: str
    reason: str


def find_substitute(original_item: dict, budget_remaining_paise: int) -> dict | None:
    """
    When an item is OOS or over-budget, find the best in-catalog substitute.

    Algorithm (deterministic filter → LLM pick):
      1. Same category as the original item — hard filter.
      2. stock > 0 — hard filter.
      3. price_paise ≤ budget_remaining_paise — hard filter.
      4. Boosted items first, then sorted by price proximity to original.
      5. Feed top-5 candidates to LLM → one SKU + one-line reason.

    Returns dict with keys: sku, name, price_paise, category, reason, original_sku, original_name
    Returns None if no valid substitute exists.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")

    conn = get_db()
    cursor = conn.cursor()

    original_sku = original_item.get("sku", "")
    original_price = original_item.get("price_paise", 0)

    # Look up original item details for context
    cursor.execute("SELECT name, category FROM catalog WHERE sku = ?", (original_sku,))
    orig_row = cursor.fetchone()
    original_name = orig_row["name"] if orig_row else original_sku
    original_category = orig_row["category"] if orig_row else ""

    # If we don't know the category, we can't do a proper substitution
    if not original_category:
        conn.close()
        return None

    # Deterministic filter: same category, in stock, within budget
    # Sort: boosted first, then by price proximity to original
    cursor.execute(
        """
        SELECT sku, name, price_paise, stock, category, boosted,
               ABS(price_paise - ?) AS price_distance
        FROM catalog
        WHERE category = ?
          AND stock > 0
          AND price_paise <= ?
          AND sku != ?
        ORDER BY boosted DESC, price_distance ASC
        LIMIT 5
        """,
        (original_price, original_category, budget_remaining_paise, original_sku)
    )
    candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not candidates:
        return None

    # If only one candidate, use it directly without calling LLM
    if len(candidates) == 1:
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "reason": f"It's a great in-stock alternative to {original_name} in the same category.",
            "original_sku": original_sku,
            "original_name": original_name,
        }

    client = OpenAI(api_key=api_key)

    candidate_str = "\n".join(
        f"- SKU: {c['sku']}, Name: {c['name']}, Price: {c['price_paise']} paise (₹{c['price_paise']/100:.0f})"
        + (" [BOOSTED — merchant wants to move this]" if c["boosted"] else "")
        for c in candidates
    )

    system_instruction = f"""
    You are an AI Substitution Agent for an e-commerce store.

    The item the customer wanted is currently unavailable:
    - SKU: {original_sku}
    - Name: {original_name}
    - Category: {original_category}

    Here are the best available alternatives (all in the same category, all in stock):
    {candidate_str}

    Pick EXACTLY ONE substitute that best serves the customer's underlying need.
    Prefer boosted items when quality is comparable.
    Write a single, natural 1-sentence reason explaining why this substitute is a good replacement.
    Return only the sku and reason fields.
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Pick the best substitute."}
        ],
        response_format=SubstituteChoice,
        temperature=0.1
    )

    choice = completion.choices[0].message.parsed

    # Verify the chosen SKU is actually in our candidate list (anti-hallucination)
    candidate_skus = {c["sku"]: c for c in candidates}
    if choice.sku not in candidate_skus:
        # Fallback: just pick the first (boosted) candidate
        c = candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "reason": f"This is a great in-stock alternative to {original_name}.",
            "original_sku": original_sku,
            "original_name": original_name,
        }

    chosen = candidate_skus[choice.sku]
    return {
        "sku": chosen["sku"],
        "name": chosen["name"],
        "price_paise": chosen["price_paise"],
        "category": chosen["category"],
        "reason": choice.reason,
        "original_sku": original_sku,
        "original_name": original_name,
    }
