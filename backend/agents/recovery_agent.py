import os
from pydantic import BaseModel
from openai import OpenAI

class RecoveryMessage(BaseModel):
    message: str

def analyze_failure(raw_error_reason: str) -> dict:
    """
    Translates raw payment errors into friendly, actionable recovery messages using OpenAI or Gemini.
    """
    from backend.engine.llm import generate_structured
    
    system_instruction = f"""
    You are an AI Payment Recovery Agent for an e-commerce store.
    A user's payment just failed. The raw error reason from the payment gateway is:
    "{raw_error_reason}"
    
    Your job is to translate this technical error into a short, friendly, and actionable 1-2 sentence message for the user.
    Do not use technical jargon. Tell them exactly what they should do next (e.g. try a different card, check balance, etc).
    """
    
    data = generate_structured(
        prompt="Generate the friendly recovery message.",
        schema=RecoveryMessage,
        system_prompt=system_instruction
    )
    return {"recommendation": data.message}
