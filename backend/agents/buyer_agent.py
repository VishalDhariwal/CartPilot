import os
import json
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db

load_dotenv()


class CartItem(BaseModel):
    sku: str
    qty: int
    price_paise: int
    name: Optional[str] = None
    category: Optional[str] = None

class AgentResponse(BaseModel):
    goal: str
    spend_cap_paise: int
    proposed_items: list[CartItem]


from backend.recommendations.embedding_engine import find_substitutes


def get_catalog_str(client: OpenAI, query: str, spend_cap_paise: int) -> tuple[str, dict]:
    """
    Returns (catalog_str, {sku: item_dict}) using Hybrid Search:
      1. Dense Semantic Vector Search (SentenceTransformer all-MiniLM-L6-v2)
      2. Tokenized keyword search directly from user tokens.
    Sorted cheapest-first so the LLM naturally picks lower-priced in-stock items.
    """
    sku_map = {}

    # 1. Dense Semantic Vector Search across the entire catalog
    try:
        sem_matches = find_substitutes(query, budget_remaining_paise=spend_cap_paise, top_k=35, min_similarity=0.40)
        for m in sem_matches:
            sku_map[m["sku"]] = {
                "sku": m["sku"],
                "name": m["name"],
                "price_paise": m["price_paise"],
                "stock": m.get("stock", 50),
                "category": m["category"],
                "boosted": m.get("boosted", 0),
                "image_url": m.get("image_url", ""),
                "description": m.get("description", ""),
                "metadata": m.get("metadata", {})
            }
    except Exception as e:
        print(f"Semantic search fallback: {e}")


    # 2. Tokenized Keyword Search directly from user tokens (zero hardcoded word lists)
    conn = get_db()
    cursor = conn.cursor()
    words = [w.strip(".,!?'\"").lower() for w in query.split() if len(w.strip(".,!?'\"")) >= 3]
    stop_words = {
        "want", "need", "like", "order", "purchase", "item", "some", "with",
        "have", "please", "shop", "buy", "get", "give", "find", "show",
        "take", "search", "look", "from", "the", "and", "for", "that", "this"
    }
    keywords = [w for w in words if w not in stop_words]

    if keywords:
        query_parts = ["name LIKE ?" for _ in keywords]
        params = [f"%{kw}%" for kw in keywords]

        sql = (
            f"SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description, metadata "
            f"FROM catalog WHERE ({' OR '.join(query_parts)}) AND stock > 0 "
            f"ORDER BY price_paise ASC LIMIT 40"
        )
        cursor.execute(sql, tuple(params))
        for row in cursor.fetchall():
            item_dict = dict(row)
            if item_dict.get("metadata") and isinstance(item_dict["metadata"], str):
                try:
                    item_dict["metadata"] = json.loads(item_dict["metadata"])
                except Exception:
                    item_dict["metadata"] = {}
            sku_map[row["sku"]] = item_dict


    conn.close()

    if not sku_map:
        return "No items found matching your request.", {}

    sorted_items = sorted(sku_map.values(), key=lambda x: x["price_paise"])

    catalog_lines = []
    for item in sorted_items:
        catalog_lines.append(
            f"- SKU: {item['sku']}, Name: {item['name']}, "
            f"Price: {item['price_paise']} paise (₹{item['price_paise']/100:.0f}), "
            f"Stock: {item['stock']}, Category: {item['category']}"
            + (" [BOOSTED PARTNER]" if item.get("boosted") else "")
        )

    return "\n".join(catalog_lines), sku_map



def get_current_policy_spend_cap() -> int:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT spend_cap_paise FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        if row and row["spend_cap_paise"]:
            return row["spend_cap_paise"]
    except Exception:
        pass
    return 1000000


def generate_cart_proposal(natural_language_request: str, custom_spend_cap_paise: Optional[int] = None) -> dict:
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

    spend_cap_paise = custom_spend_cap_paise or get_current_policy_spend_cap()

    catalog_str, sku_map = get_catalog_str(client, natural_language_request, spend_cap_paise)

    if not sku_map or catalog_str == "No items found matching your request.":
        return {
            "goal": natural_language_request,
            "spend_cap_paise": spend_cap_paise,
            "proposed_items": [],
            "oos_items": []
        }


    system_instruction = f"""
    You are an AI Buyer Agent for an e-commerce store. Convert the user's natural language shopping request into a structured cart.

    Available catalog matches (sorted cheapest first):
    {catalog_str}

    STRICT RULES — violating any of these is a critical failure:
    1. ONLY use SKUs that appear in the catalog above. Never invent or guess SKUs.
    2. RELEVANCE: ONLY pick items that match what the user actually asked for. Never pick unrelated items (e.g. do not select milk or eggs if user asked for shirts or sneakers).
    3. The price_paise for each item MUST exactly match the catalog value shown above.
    4. The sum of (price_paise × qty) for ALL items MUST NOT exceed {spend_cap_paise} paise (₹{spend_cap_paise/100:.0f}).
    5. If multiple SKUs match a requested item type, prefer the CHEAPEST one unless the user explicitly asks for a premium/expensive variant.
    6. QUANTITY & VARIETY SELECTION:
       - If the user asks for a single product (e.g. 'i want to buy shirts', 'get me a smartwatch'), pick EXACTLY ONE best-matching SKU with quantity 1.
       - NEVER dump multiple different varieties of the same product into the cart unless the user specifically asked for multiple varieties or brands.
       - If the user specifies a quantity for a product (e.g. '2 packs of eggs'), pick ONE SKU and set qty = 2.
       - If the user requests multiple distinct items (e.g. 't-shirt, jeans, and belt'), pick exactly one best SKU for each distinct requested item.
    7. JSON OUTPUT:
       Return ONLY JSON matching the required schema.
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

    # Post-validate: enrich with full catalog metadata (name, category, images, sizes) and correct prices
    validated_items = []
    oos_items = []
    for item in result["proposed_items"]:
        if item["sku"] in sku_map:
            catalog_row = sku_map[item["sku"]]
            meta_obj = catalog_row.get("metadata", {})
            if isinstance(meta_obj, str):
                try:
                    meta_obj = json.loads(meta_obj)
                except Exception:
                    meta_obj = {}

            enriched_item = {
                "sku": catalog_row["sku"],
                "name": catalog_row["name"],
                "price_paise": catalog_row["price_paise"],
                "qty": max(1, item.get("qty", 1)),
                "category": catalog_row["category"],
                "image_url": catalog_row.get("image_url", ""),
                "description": catalog_row.get("description", ""),
                "metadata": meta_obj
            }
            if catalog_row["stock"] == 0:
                oos_items.append(enriched_item)
            else:
                validated_items.append(enriched_item)


    result["proposed_items"] = validated_items
    result["oos_items"] = oos_items

    return result
