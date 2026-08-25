from fastapi import APIRouter, HTTPException
from backend.engine.mandates import get_recovery_message

router = APIRouter()

@router.get("/{cart_id}")
def get_recovery(cart_id: str):
    """
    Phase 6: Recovery API
    Returns the AI's recommendation for a failed payment.
    """
    try:
        message_data = get_recovery_message(cart_id)
        if not message_data:
            raise HTTPException(status_code=404, detail="Payment Mandate not found for this cart.")
            
        if message_data["status"] != "failed":
            return {
                "status": message_data["status"],
                "message": "Payment has not failed, so no recovery recommendation is needed."
            }
            
        return {
            "status": "failed",
            "failure_reason": message_data["failure_reason"],
            "recommendation": message_data["recovery_action"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
