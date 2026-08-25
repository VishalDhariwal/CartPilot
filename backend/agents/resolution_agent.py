"""
CartPilot AI Customer Intent & Resolution Classifier
===================================================
Uses LLM to understand and extract structured customer intent from natural language.
Bounded role: Only parses and summarizes customer intent — never decides financial eligibility.
"""

import json
from typing import Optional, Literal
from pydantic import BaseModel
from backend.engine.llm import generate_structured


class CustomerResolutionIntent(BaseModel):
    intent: Literal[
        "CANCEL_ORDER",
        "REQUEST_REFUND",
        "RETURN_ITEM",
        "REPORT_DAMAGED_ITEM",
        "ASK_REFUND_POLICY",
        "CHECK_REFUND_STATUS",
        "DISPUTE_CHARGE"
    ]
    reason: str
    requested_amount_paise: Optional[int] = None
    item_scope: Literal["full_order", "partial_item", "unknown"] = "full_order"
    explanation: str

CustomerResolutionIntent.model_rebuild()


class ResolutionDecision(BaseModel):
    action: str
    reason: str
    intent: Optional[str] = None
    requested_amount_paise: Optional[int] = None

ResolutionDecision.model_rebuild()


def classify_customer_intent(natural_language_request: str, order_state: Optional[dict] = None) -> CustomerResolutionIntent:
    """
    Parses unstructured customer support inquiries into a structured intent representation.
    The AI only understands customer intent — it NEVER decides financial or refund authorization.
    """
    system_instruction = """
You are CartPilot's AI Customer Intent & Resolution Classifier.
A customer is messaging regarding an existing shopping cart or order.
Analyze the customer's natural language message and classify their core intent into one of the following:

1. 'CANCEL_ORDER': Customer explicitly wants to cancel an in-progress or placed order before fulfillment.
2. 'REQUEST_REFUND': Customer is seeking financial refund/reversal.
3. 'RETURN_ITEM': Customer wants to return a physical item they received.
4. 'REPORT_DAMAGED_ITEM': Customer is reporting broken, defective, or incorrect items.
5. 'ASK_REFUND_POLICY': Customer is asking a general policy or informational question (e.g. "What is your refund policy?", "How many days for return?").
6. 'CHECK_REFUND_STATUS': Customer is asking about the status of an existing refund or tracking progress.
7. 'DISPUTE_CHARGE': Customer is escalating an unauthorized or disputed charge.

Extract the specific reason, any requested partial refund amount in paise (1 INR = 100 paise), the item scope, and a polite 1-sentence customer explanation.
Do NOT make financial approval decisions.
"""
    prompt_text = f"CUSTOMER MESSAGE:\n{natural_language_request}"
    if order_state:
        prompt_text += f"\n\nCONTEXTUAL ORDER METADATA:\n{json.dumps(order_state, indent=2)}"

    data = generate_structured(
        prompt=prompt_text,
        schema=CustomerResolutionIntent,
        system_prompt=system_instruction
    )
    return data


def decide_resolution(natural_language_request: str, order_state: dict) -> dict:
    """
    Backward-compatible wrapper:
    1. Classifies intent via AI.
    2. Returns legacy action dictionary with rich intent attributes.
    """
    intent_obj = classify_customer_intent(natural_language_request, order_state)
    
    if intent_obj.intent in ["CANCEL_ORDER", "REQUEST_REFUND"]:
        action = "cancel"
    elif intent_obj.intent in ["ASK_REFUND_POLICY", "CHECK_REFUND_STATUS"]:
        action = "inform"
    else:
        action = "escalate"

    return {
        "action": action,
        "reason": intent_obj.explanation or intent_obj.reason,
        "intent": intent_obj.intent,
        "requested_amount_paise": intent_obj.requested_amount_paise,
        "item_scope": intent_obj.item_scope
    }
