import os
from pydantic import BaseModel
from openai import OpenAI

class RecoveryMessage(BaseModel):
    message: str

def analyze_failure(raw_error_reason: str) -> dict:
    """
    Calls ChatGPT to translate a raw Razorpay webhook error into a friendly, actionable recovery message.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")
        
    client = OpenAI(api_key=api_key)
    
    system_instruction = f"""
    You are an AI Payment Recovery Agent for an e-commerce store.
    A user's payment just failed. The raw error reason from the payment gateway is:
    "{raw_error_reason}"
    
    Your job is to translate this technical error into a short, friendly, and actionable 1-2 sentence message for the user.
    Do not use technical jargon. Tell them exactly what they should do next (e.g. try a different card, check balance, etc).
    """
    
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Generate the friendly recovery message."}
        ],
        response_format=RecoveryMessage,
        temperature=0.3
    )
    
    data = completion.choices[0].message.parsed
    return {"recommendation": data.message}
