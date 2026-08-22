import os
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db

load_dotenv()


class UpsellChoice(BaseModel):
    suggest: bool
    sku: str
    reason: str


def generate_upsell(cart_items: list) -> dict | None:
    """
    Cross-sell recommendation using two layers:
      Layer 1 (deterministic): query catalog_pairings for each cart item.
                               Filter: sku_b must be in-stock and not already in cart.
                               Prefer boosted=1 pairs first.
      Layer 2 (LLM): given the 2-3 best candidates, pick the single best one
                     for this specific cart and write a natural reason.

    Returns {sku, name, price_paise, category, reason} or None.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")

    conn = get_db()
    cursor = conn.cursor()

    cart_skus = {item["sku"] for item in cart_items}

    # Layer 1: Find all valid pairings for items in the cart
    candidates = []
    for item in cart_items:
        cursor.execute(
            """
            SELECT cp.sku_b, cp.reason_template, cp.boosted,
                   c.name, c.price_paise, c.category, c.stock
            FROM catalog_pairings cp
            JOIN catalog c ON c.sku = cp.sku_b
            WHERE cp.sku_a = ?
              AND c.stock > 0
              AND cp.sku_b NOT IN ({})
            ORDER BY cp.boosted DESC, c.price_paise ASC
            """.format(",".join("?" * len(cart_skus)) if cart_skus else "'__none__'"),
            (item["sku"], *cart_skus) if cart_skus else (item["sku"],)
        )
        rows = cursor.fetchall()
        for row in rows:
            candidates.append({
                "sku": row["sku_b"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "category": row["category"],
                "reason_template": row["reason_template"],
                "boosted": row["boosted"],
                "trigger_sku": item["sku"],
            })

    conn.close()

    if not candidates:
        return None

    # Deduplicate (same sku_b may come from multiple cart items) — keep the boosted version
    seen = {}
    for c in candidates:
        if c["sku"] not in seen or c["boosted"] > seen[c["sku"]]["boosted"]:
            seen[c["sku"]] = c
    unique_candidates = sorted(seen.values(), key=lambda x: (-x["boosted"], x["price_paise"]))

    # If only one candidate, skip the LLM and use the pre-authored reason
    if len(unique_candidates) == 1:
        c = unique_candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "reason": c["reason_template"],
        }

    # Layer 2: LLM picks the best among top-3 candidates and writes a natural reason
    client = OpenAI(api_key=api_key)

    top_candidates = unique_candidates[:3]
    candidate_str = "\n".join(
        f"- SKU: {c['sku']}, Name: {c['name']}, Price: ₹{c['price_paise']/100:.0f}, "
        f"Pre-authored reason: \"{c['reason_template']}\""
        + (" [BOOSTED]" if c["boosted"] else "")
        for c in top_candidates
    )

    cart_summary = ", ".join(
        f"{item['sku']} (×{item['qty']}, ₹{item['price_paise']/100:.0f})"
        for item in cart_items
    )

    system_instruction = f"""
    You are a Growth Agent for an e-commerce store. Your job is to pick the single best
    cross-sell item from a pre-vetted list and write a compelling, natural reason.

    The customer's current cart contains: {cart_summary}

    These are the only valid cross-sell candidates (all real, in-stock SKUs from our catalog):
    {candidate_str}

    Rules:
    1. Pick EXACTLY ONE SKU from the list above. Do not suggest any SKU not listed.
    2. Prefer BOOSTED items unless a non-boosted item is clearly more relevant to the cart.
    3. Write a single natural, specific 1-sentence reason that references what's actually in the cart.
    4. Set suggest=true unless there is genuinely no logical pairing (rare given the filtered list).
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Pick the best cross-sell item for this cart."}
        ],
        response_format=UpsellChoice,
        temperature=0.2
    )

    choice = completion.choices[0].message.parsed

    if not choice.suggest or not choice.sku:
        return None

    # Anti-hallucination guard: verify chosen SKU is in our candidate list
    candidate_map = {c["sku"]: c for c in top_candidates}
    if choice.sku not in candidate_map:
        # Fallback: use the top boosted candidate with its pre-authored reason
        c = top_candidates[0]
        return {
            "sku": c["sku"],
            "name": c["name"],
            "price_paise": c["price_paise"],
            "category": c["category"],
            "reason": c["reason_template"],
        }

    chosen = candidate_map[choice.sku]
    return {
        "sku": chosen["sku"],
        "name": chosen["name"],
        "price_paise": chosen["price_paise"],
        "category": chosen["category"],
        "reason": choice.reason,
    }
