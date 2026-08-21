import os
import json
from pydantic import BaseModel
from google import genai
from google.genai import types

class ResolutionResponse(BaseModel):
    action: str
    reason: str

def decide_resolution(natural_language_request: str, cart_state: dict) -> dict:
    """
    Calls Gemini to decide if a cancellation request is valid and actionable.
    Returns a dict with 'action' ("refund" or "deny") and 'reason'.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "yourgeminikeyhere":
        raise ValueError("GEMINI_API_KEY is not set in .env")
        
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an AI Resolution Agent. Your job is to process a user's cancellation/refund request.
    
    Here is the current state of the order:
    {json.dumps(cart_state, indent=2)}
    
    Rules:
    1. If the user is asking to cancel or refund, and the cart is `reversible: true`, and the payment `status: succeeded`, you MUST approve the refund. Set action="refund".
    2. If the user is asking to cancel but `reversible: false` or the payment has not succeeded, you MUST deny the request. Set action="deny".
    3. If the user's request is completely unrelated to cancellation or refunds, set action="deny".
    4. Provide a polite 'reason' explaining your decision based on the order state.
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=natural_language_request,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=ResolutionResponse,
            temperature=0.1
        )
    )
    
    try:
        data = json.loads(response.text)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned invalid JSON: {response.text}") from e
