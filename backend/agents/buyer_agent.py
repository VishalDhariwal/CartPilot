import os
import json
from pydantic import BaseModel
from google import genai
from google.genai import types
from backend.db import get_db

class CartItem(BaseModel):
    sku: str
    qty: int
    price_paise: int

class AgentResponse(BaseModel):
    goal: str
    spend_cap_paise: int
    proposed_items: list[CartItem]

def get_catalog_str() -> str:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, name, price_paise, category FROM catalog")
    items = cursor.fetchall()
    conn.close()
    
    catalog_list = []
    for row in items:
        catalog_list.append(f"- SKU: {row['sku']}, Name: {row['name']}, Price: {row['price_paise']} paise, Category: {row['category']}")
    return "\n".join(catalog_list)

def generate_cart_proposal(natural_language_request: str) -> dict:
    """
    Calls Gemini to parse a natural language request into a structured intent and cart.
    Returns a dict with 'goal', 'spend_cap_paise', and 'proposed_items'.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "yourgeminikeyhere":
        raise ValueError("GEMINI_API_KEY is not set in .env")
        
    client = genai.Client(api_key=api_key)
    
    catalog_str = get_catalog_str()
    
    system_instruction = f"""
    You are an AI Buyer Agent. Your job is to convert a user's natural language shopping request into a structured cart proposal.
    
    Here is the available catalog:
    {catalog_str}
    
    Rules:
    1. Parse the user's intent into a short "goal" description.
    2. Extract the user's budget in rupees and convert it to paise (1 Rupee = 100 paise). If no budget is specified, use 150000. This is the "spend_cap_paise".
    3. Select items from the catalog that best match the user's request.
    4. ONLY use SKUs that exist in the catalog above. Do not hallucinate items.
    5. Ensure the price_paise for each item matches the catalog EXACTLY.
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=natural_language_request,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=AgentResponse,
            temperature=0.1
        )
    )
    
    # Parse the structured JSON response
    try:
        data = json.loads(response.text)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned invalid JSON: {response.text}") from e
