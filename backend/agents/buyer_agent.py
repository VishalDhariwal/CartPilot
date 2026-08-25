import os
import json
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from backend.db import get_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))


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


def get_catalog_str(
    client: OpenAI,
    query: str,
    spend_cap_paise: int,
    current_cart: Optional[list] = None,
    conversation_history: Optional[list] = None
) -> tuple[str, dict]:
    """
    Returns (catalog_str, {sku: item_dict}) using Hybrid Search:
      1. Dense Semantic Vector Search (SentenceTransformer all-MiniLM-L6-v2)
      2. Tokenized keyword search across user query, current cart, and conversation context.
    Sorted cheapest-first so the LLM naturally picks lower-priced in-stock items.
    """
    sku_map = {}
    conn = get_db()
    cursor = conn.cursor()

    # 1. Always load all current cart items into sku_map so the LLM can reference/retain them
    if current_cart:
        for cart_item in current_cart:
            sku = cart_item.get("sku")
            if sku:
                cursor.execute(
                    "SELECT sku, name, price_paise, stock, category, merchant, boosted, image_url, description, metadata FROM catalog WHERE sku = ?",
                    (sku,)
                )
                row = cursor.fetchone()
                if row:
                    item_dict = dict(row)
                    if item_dict.get("metadata") and isinstance(item_dict["metadata"], str):
                        try:
                            item_dict["metadata"] = json.loads(item_dict["metadata"])
                        except Exception:
                            item_dict["metadata"] = {}
                    sku_map[sku] = item_dict

    # 2. Build multi-turn search context
    search_queries = [query]
    if conversation_history:
        for msg in conversation_history[-3:]:
            if msg.get("role") in ("user", "human"):
                search_queries.append(msg.get("content", ""))
    if current_cart:
        for it in current_cart:
            if it.get("name"):
                search_queries.append(it["name"])

    combined_search_text = " ".join(search_queries)

    # 3. Dense Semantic Vector Search across the entire catalog
    try:
        sem_matches = find_substitutes(combined_search_text, budget_remaining_paise=spend_cap_paise, top_k=35, min_similarity=0.35)
        for m in sem_matches:
            if m["sku"] not in sku_map:
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

    # 4. Tokenized Keyword Search directly from tokens
    words = [w.strip(".,!?'\"").lower() for w in combined_search_text.split() if len(w.strip(".,!?'\"")) >= 3]
    stop_words = {
        "want", "need", "like", "order", "purchase", "item", "some", "with",
        "have", "please", "shop", "buy", "get", "give", "find", "show",
        "take", "search", "look", "from", "the", "and", "for", "that", "this",
        "also", "too", "more", "make", "change", "replace", "instead"
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
            if row["sku"] not in sku_map:
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


def generate_cart_proposal(
    natural_language_request: str,
    custom_spend_cap_paise: Optional[int] = None,
    conversation_history: Optional[list] = None,
    current_cart: Optional[list] = None
) -> dict:
    """
    Calls the LLM to parse natural language requests with multi-turn conversation memory and active cart state.
    Supports additions ("also add mascara"), replacements ("instead of shirt give me jacket"),
    quantity adjustments ("make it 2"), and removals ("remove perfume").
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not openai_key and not gemini_key:
        raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is set in .env")

    spend_cap_paise = custom_spend_cap_paise or get_current_policy_spend_cap()

    catalog_str, sku_map = get_catalog_str(
        client=None,
        query=natural_language_request,
        spend_cap_paise=spend_cap_paise,
        current_cart=current_cart,
        conversation_history=conversation_history
    )

    if not sku_map or catalog_str == "No items found matching your request.":
        return {
            "goal": natural_language_request,
            "spend_cap_paise": spend_cap_paise,
            "proposed_items": [],
            "oos_items": []
        }

    # Format Current Cart context for the LLM
    if current_cart and len(current_cart) > 0:
        cart_lines = []
        for it in current_cart:
            cart_lines.append(
                f"- SKU: {it['sku']}, Name: {it.get('name', it.get('sku'))}, Qty: {it.get('qty', 1)}, Price: ₹{it.get('price_paise', 0)/100:.0f}"
            )
        current_cart_text = "\n".join(cart_lines)
    else:
        current_cart_text = "Empty (no items in cart yet)"

    system_instruction = f"""
    You are an AI Buyer Agent with conversational context and memory. Convert user shopping requests and conversational follow-ups into a structured cart.

    CUSTOMER'S CURRENT CART:
    {current_cart_text}

    AVAILABLE CATALOG MATCHES (sorted cheapest first):
    {catalog_str}

    CONVERSATIONAL CONTEXT RULES:
    1. ADDITIVE REQUESTS (e.g. "also add perfume", "and a smartwatch", "add running shoes"):
       - Retain all existing items in the cart and ADD the newly requested items.
    2. REPLACEMENT / CORRECTION (e.g. "instead of shoes give me boots", "change shirt to black one"):
       - Remove the referenced item and replace it with the new choice.
    3. QUANTITY ADJUSTMENT (e.g. "make it 2 shirts", "add 1 more"):
       - Update the qty of the existing item in the cart.
    4. REMOVAL (e.g. "remove the perfume"):
       - Omit the removed item from the proposed items list.
    5. BRAND NEW SHOPPING INTENT (e.g. "clear cart and buy laptops", "start new order with sneakers"):
       - Discard prior cart items and create a fresh proposal for the new request.

    STRICT RULES:
    1. ONLY use SKUs that appear in the catalog above. Never invent or guess SKUs.
    2. RELEVANCE: ONLY pick items that match what the user actually asked for.
    3. The price_paise for each item MUST exactly match the catalog value shown above.
    4. The sum of (price_paise × qty) for ALL items MUST NOT exceed {spend_cap_paise} paise (₹{spend_cap_paise/100:.0f}).
    5. If multiple SKUs match a requested item type, prefer the CHEAPEST one unless the user explicitly asks for a premium/expensive variant.
    6. Pick EXACTLY ONE best-matching SKU for each distinct requested product with the appropriate quantity.
    7. JSON OUTPUT: Return ONLY JSON matching the required schema.
    """

    # Format Conversation Context
    history_text = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-6:]:
            role = "Agent" if msg.get("role") in ("agent", "assistant") else "User"
            content = msg.get("content", "").strip()
            if content and not content.startswith("🛡️ **Spend Cap Updated"):
                clean_content = content.replace("🚫 **Guardrail Blocked**:", "Notice:").replace("🎉 **Payment Succeeded!**", "Payment completed.")
                history_lines.append(f"{role}: {clean_content}")
        if history_lines:
            history_text = "CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

    user_prompt = f"{history_text}CURRENT USER REQUEST:\n{natural_language_request}"

    from backend.engine.llm import generate_structured
    agent_response = generate_structured(
        prompt=user_prompt,
        schema=AgentResponse,
        system_prompt=system_instruction
    )
    result = agent_response.model_dump()

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

