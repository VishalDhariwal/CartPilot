import os
import json
from pydantic import BaseModel
from openai import OpenAI

class ResolutionDecision(BaseModel):
    action: str
    reason: str

def decide_resolution(natural_language_request: str, order_state: dict) -> dict:
    """
    Calls ChatGPT to determine what action to take (e.g. cancel, escalate) based on the user's request and order state.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")
        
    client = OpenAI(api_key=api_key)
    
    system_instruction = f"""
    You are an AI Resolution Agent for an e-commerce store.
    A user is contacting you regarding an existing order.
    
    Here is the current state of their order from the database:
    {json.dumps(order_state, indent=2)}
    
    Rules:
    1. Determine the appropriate action to take based on the user's request.
    2. The valid actions are:
       - 'cancel': If the user clearly wants to cancel the order and it is eligible for cancellation (cart is reversible, payment succeeded).
       - 'escalate': If the user is asking for something complex, or wants to cancel an order that is no longer reversible.
       - 'inform': If the user is just asking for status or policy, or we cannot fulfill the request.
    3. Provide a short 'reason' explaining why you chose this action.
    """
    
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": natural_language_request}
        ],
        response_format=ResolutionDecision,
        temperature=0.1
    )
    
    data = completion.choices[0].message.parsed
    return data.model_dump()
