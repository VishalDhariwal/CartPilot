import os
import json
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db

class CartItem(BaseModel):
    sku: str
    qty: int = 1
    price_paise: int
    name: Optional[str] = None
    category: Optional[str] = None

class AgentResponse(BaseModel):
    goal: str
    spend_cap_paise: int
    proposed_items: list[CartItem]

class QueryIntent(BaseModel):
    keywords: list[str]


def get_catalog_str(client: OpenAI, query: str, spend_cap_paise: int) -> tuple[str, dict]:
    """
    Returns (catalog_str, {sku: item_dict}) for items matching the query,
    sorted cheapest-first so the LLM naturally picks lower-priced items.
    """
    system_instruction = """
    You are an AI Search Query Generator for an e-commerce catalog.
    Extract the most relevant search keywords from the user's shopping request.
    Include synonyms if necessary (e.g. if they say 'mobile', include 'smartphone').
    Return a list of 1-3 highly relevant keywords.
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": query}
        ],
        response_format=QueryIntent,
        temperature=0.1
    )

    keywords = completion.choices[0].message.parsed.keywords

    conn = get_db()
    cursor = conn.cursor()

    if not keywords:
        cursor.execute(
            "SELECT sku, name, price_paise, stock, category, merchant, boosted FROM catalog WHERE stock > 0 ORDER BY price_paise ASC LIMIT 60"
        )
    else:
        query_parts = []
        params = []
        for kw in keywords:
            query_parts.append("name LIKE ? OR category LIKE ?")
            params.extend([f"%{kw}%", f"%{kw}%"])

        # Only return items that are in stock, sorted cheapest-first
        sql = (
            f"SELECT sku, name, price_paise, stock, category, merchant, boosted "
            f"FROM catalog WHERE ({' OR '.join(query_parts)}) AND stock > 0 "
            f"ORDER BY price_paise ASC LIMIT 60"
        )
        cursor.execute(sql, tuple(params))

    items = cursor.fetchall()
    conn.close()

    catalog_lines = []
    sku_map = {}
    for row in items:
        sku_map[row["sku"]] = dict(row)
        catalog_lines.append(
            f"- SKU: {row['sku']}, Name: {row['name']}, "
            f"Price: {row['price_paise']} paise (₹{row['price_paise']/100:.0f}), "
            f"Stock: {row['stock']}, Category: {row['category']}"
        )

    if not catalog_lines:
        return "No items found.", {}

    return "\n".join(catalog_lines), sku_map


def generate_cart_proposal(natural_language_request: str) -> dict:
    """
    Calls the LLM to parse a natural language request into a structured cart.
    Enforces that the LLM stays within the spend cap and picks cheapest adequate matches.
    Crucially selects ONLY the requested items (single product -> 1 SKU with qty 1),
    not every matching catalog item.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=api_key)

    spend_cap_paise = 500000

    catalog_str, sku_map = get_catalog_str(client, natural_language_request, spend_cap_paise)

    system_instruction = f"""
    You are an AI Buyer Agent for an e-commerce store. Convert the user's natural language shopping request into a structured cart.

    Available catalog (sorted cheapest first):
    {catalog_str}

    STRICT RULES — violating any of these is a critical failure:
    1. ONLY use SKUs that appear in the catalog above. Never invent or guess SKUs.
    2. The price_paise for each item MUST exactly match the catalog value shown above.
    3. The sum of (price_paise × qty) for ALL items MUST NOT exceed {spend_cap_paise} paise (₹{spend_cap_paise/100:.0f}).
    4. If multiple SKUs match a requested item type, prefer the CHEAPEST one unless the user explicitly asks for a premium/expensive variant.
    5. QUANTITY & VARIETY SELECTION:
       - If the user asks for a single product (e.g. 'i want to buy cheese', 'get me milk', 'order a laptop'), pick EXACTLY ONE best-matching SKU with quantity 1.
       - NEVER dump multiple different varieties of the same product into the cart unless the user specifically asked for multiple varieties or brands (e.g. 'give me 3 kinds of cheese').
       - If the user specifies a quantity for a product (e.g. '2 packs of eggs'), pick ONE SKU and set qty = 2.
       - If the user requests multiple distinct items (e.g. 'cheese, bread, and milk'), pick exactly one best SKU for each distinct requested item.
    6. Parse the user's intent into a short "goal" description.
    7. Extract the user's budget in rupees and convert to paise (1 rupee = 100 paise). If not stated, use {spend_cap_paise}.
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": natural_language_request}
        ],
        response_format=AgentResponse,
        temperature=0.1
    )

    data = completion.choices[0].message.parsed
    result = data.model_dump()

    # Post-validate: enrich with full catalog metadata (name, category) and correct prices
    validated_items = []
    oos_items = []
    for item in result["proposed_items"]:
        if item["sku"] in sku_map:
            catalog_row = sku_map[item["sku"]]
            enriched_item = {
                "sku": catalog_row["sku"],
                "name": catalog_row["name"],
                "price_paise": catalog_row["price_paise"],
                "qty": max(1, item.get("qty", 1)),
                "category": catalog_row["category"]
            }
            if catalog_row["stock"] == 0:
                oos_items.append(enriched_item)
            else:
                validated_items.append(enriched_item)

    result["proposed_items"] = validated_items
    result["oos_items"] = oos_items

    return result
