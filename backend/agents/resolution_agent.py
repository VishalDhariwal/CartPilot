import os
import json
from pydantic import BaseModel
from openai import OpenAI

class ResolutionDecision(BaseModel):
    action: str
    reason: str

def decide_resolution(natural_language_request: str, order_state: dict) -> dict:
    """
    Determines what action to take (e.g. cancel, escalate) based on the user's request and order state using OpenAI or Gemini.
    """
    from backend.engine.llm import generate_structured
    
    system_instruction = f"""
    You are the Autonomous AI Resolution & Refund Agent for CartPilot.
    A customer is contacting you regarding an existing order.
    
    Here is the exact live order state from the database:
    {json.dumps(order_state, indent=2)}
    
    Decision Rules:
    1. 'cancel':
       - Choose 'cancel' whenever the user wants to cancel the order, request a refund, or reverse their purchase (e.g. "I would like to cancel my order and request a refund", "cancel order", "please refund").
       - If `cart.reversible` is 1 (or true) AND `payment.status` is 'succeeded' AND `payment.recovery_action` is not 'refunded', this order is 100% ELIGIBLE for instant cancellation and automated refund. You MUST select 'cancel'.
    
    2. 'escalate':
       - Choose 'escalate' ONLY if the order is no longer reversible (`cart.reversible` is 0), already refunded, or involves an unresolvable fraud/technical dispute.
    
    3. 'inform':
       - Choose 'inform' ONLY if the user is asking a general question (e.g. "what is your refund policy?") without requesting an actual order cancellation or refund.
    
    4. Reason:
       - Provide a concise 1-sentence confirmation (e.g. "Your cancellation request has been verified against merchant policy and approved for immediate Razorpay refund.").
    """
    
    data = generate_structured(
        prompt=natural_language_request,
        schema=ResolutionDecision,
        system_prompt=system_instruction
    )
    return data.model_dump()
