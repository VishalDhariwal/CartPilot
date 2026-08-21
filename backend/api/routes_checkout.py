from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.engine.mandates import create_intent_mandate, create_cart_mandate, create_payment_mandate
from backend.engine.guardrail import validate_cart
from backend.integrations.razorpay_client import create_order, create_payment_link
from backend.agents.buyer_agent import generate_cart_proposal

router = APIRouter()

class AgentCheckoutRequest(BaseModel):
    query: str

@router.post("/agent-checkout")
def agent_checkout(req: AgentCheckoutRequest):
    """
    Phase 3: Real Buyer Agent Slice.
    This takes a natural language query, uses Gemini to create an Intent and Cart,
    validates it via Guardrail, and generates a Razorpay Order and Payment Link.
    """
    try:
        # 1. Call Buyer Agent
        agent_output = generate_cart_proposal(req.query)
        
        # 2. Create Intent Mandate
        intent = create_intent_mandate(
            raw_request=req.query,
            goal=agent_output["goal"],
            spend_cap_paise=agent_output["spend_cap_paise"]
        )
        
        proposed_items = agent_output["proposed_items"]
        total_paise = sum(item["price_paise"] * item["qty"] for item in proposed_items)
        
        # 3. Guardrail Check
        validation_result = validate_cart(intent["id"], proposed_items, total_paise)
        
        # 4. Create Cart Mandate
        cart = create_cart_mandate(
            intent_id=intent["id"],
            items=proposed_items,
            total_paise=total_paise,
            status=validation_result["status"],
            reason=validation_result["reason"],
            reversible=validation_result["reversible"]
        )
        
        # If Blocked, stop here
        if cart["status"] == "blocked":
            return {"status": "blocked", "reason": cart["reason"], "cart_id": cart["id"]}
            
        # 5. Create Razorpay Order
        order = create_order(
            amount_paise=cart["total_paise"],
            receipt_id=cart["id"],
            notes={"cart_id": cart["id"]}
        )
        
        # 6. Create Payment Link
        payment_link = create_payment_link(
            amount_paise=cart["total_paise"],
            order_id=order["id"],
            description="Phase 3 Agent Order"
        )
        
        # 7. Create Payment Mandate
        payment_mandate = create_payment_mandate(
            cart_id=cart["id"],
            razorpay_order_id=order["id"],
            amount_paise=cart["total_paise"]
        )
        
        return {
            "status": "approved",
            "payment_url": payment_link["short_url"],
            "intent_id": intent["id"],
            "cart_id": cart["id"],
            "payment_mandate_id": payment_mandate["id"],
            "agent_goal": agent_output["goal"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hardcoded-checkout")
def hardcoded_checkout():

    """
    Phase 2: Thin End-to-End Slice.
    This creates a hardcoded Intent and Cart, validates it via Guardrail,
    and if approved, generates a Razorpay Order and Payment Link.
    All steps write to the audit trail.
    """
    try:
        # 1. Hardcoded Intent
        intent = create_intent_mandate(
            raw_request="order me 2kg atta and a mixer whistle, budget 1500",
            goal="grocery + kitchenware purchase",
            spend_cap_paise=150000
        )
        
        # 2. Hardcoded Cart Proposal
        proposed_items = [
            {"sku": "ATTA-2KG", "qty": 1, "price_paise": 12000},
            {"sku": "MIXER-WHISTLE", "qty": 1, "price_paise": 30000}
        ]
        total_paise = sum(item["price_paise"] * item["qty"] for item in proposed_items)
        
        # 3. Guardrail Check
        validation_result = validate_cart(intent["id"], proposed_items, total_paise)
        
        # 4. Create Cart Mandate
        cart = create_cart_mandate(
            intent_id=intent["id"],
            items=proposed_items,
            total_paise=total_paise,
            status=validation_result["status"],
            reason=validation_result["reason"],
            reversible=validation_result["reversible"]
        )
        
        # If Blocked, stop here
        if cart["status"] == "blocked":
            return {"status": "blocked", "reason": cart["reason"], "cart_id": cart["id"]}
            
        # 5. Create Razorpay Order
        order = create_order(
            amount_paise=cart["total_paise"],
            receipt_id=cart["id"],
            notes={"cart_id": cart["id"]}
        )
        
        # 6. Create Payment Link
        payment_link = create_payment_link(
            amount_paise=cart["total_paise"],
            order_id=order["id"],
            description="Phase 2 Test Order"
        )
        
        # 7. Create Payment Mandate
        payment_mandate = create_payment_mandate(
            cart_id=cart["id"],
            razorpay_order_id=order["id"],
            amount_paise=cart["total_paise"]
        )
        
        return {
            "status": "approved",
            "payment_url": payment_link["short_url"],
            "intent_id": intent["id"],
            "cart_id": cart["id"],
            "payment_mandate_id": payment_mandate["id"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
