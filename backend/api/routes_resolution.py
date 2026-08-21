from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.engine.mandates import get_cart_state, execute_refund
from backend.agents.resolution_agent import decide_resolution

router = APIRouter()

class CancelRequest(BaseModel):
    cart_id: str
    query: str

@router.post("/cancel")
def cancel_order(req: CancelRequest):
    """
    Phase 5: Resolution Agent flow.
    Takes a cancellation request, uses Gemini to decide if it's valid,
    and executes a refund if the cart is reversible and payment succeeded.
    """
    try:
        # 1. Get current cart state
        cart_state = get_cart_state(req.cart_id)
        if not cart_state:
            raise HTTPException(status_code=404, detail="Cart not found")
            
        # 2. Ask Resolution Agent to decide
        decision = decide_resolution(req.query, cart_state)
        
        # 3. Execute action if approved
        if decision["action"] == "refund":
            refund_response = execute_refund(req.cart_id)
            return {
                "status": "refunded",
                "reason": decision["reason"],
                "refund_id": refund_response.get("id")
            }
        else:
            return {
                "status": "denied",
                "reason": decision["reason"]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
