"""
CartPilot Customer Resolution & Refund API Routes
=================================================
Exposes endpoints for customer order cancellation, return workflow, and refund evaluation.
Integrates AI intent parsing with the deterministic Resolution Engine.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.engine.mandates import get_cart_state
from backend.agents.resolution_agent import classify_customer_intent
from backend.engine.resolution_engine import (
    evaluate_resolution_eligibility,
    create_and_execute_refund,
    ResolutionAction
)

router = APIRouter()


class CancelRequest(BaseModel):
    cart_id: str
    query: str
    amount_paise: Optional[int] = None


@router.post("/evaluate")
def evaluate_resolution(req: CancelRequest):
    """
    Evaluates customer intent and deterministic eligibility without mutating state.
    """
    try:
        cart_state = get_cart_state(req.cart_id)
        if not cart_state:
            raise HTTPException(status_code=404, detail="Cart not found")

        intent_obj = classify_customer_intent(req.query, cart_state)
        req_amount = req.amount_paise or intent_obj.requested_amount_paise

        eval_result = evaluate_resolution_eligibility(
            cart_id=req.cart_id,
            intent=intent_obj.intent,
            requested_amount_paise=req_amount
        )

        return {
            "intent": intent_obj.intent,
            "intent_reason": intent_obj.reason,
            "explanation": intent_obj.explanation,
            "eligibility": eval_result.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel")
def cancel_order(req: CancelRequest):
    """
    Executes the full resolution lifecycle:
    1. AI classifies unstructured customer intent.
    2. Deterministic engine evaluates commercial eligibility.
    3. Executes authorized cancellation, return review, or gateway refund.
    """
    try:
        cart_state = get_cart_state(req.cart_id)
        if not cart_state:
            raise HTTPException(status_code=404, detail="Cart not found")

        # 1. Parse intent via AI
        intent_obj = classify_customer_intent(req.query, cart_state)
        req_amount = req.amount_paise or intent_obj.requested_amount_paise

        # 2. Evaluate eligibility deterministically
        eval_result = evaluate_resolution_eligibility(
            cart_id=req.cart_id,
            intent=intent_obj.intent,
            requested_amount_paise=req_amount
        )

        # 3. Action routing
        if eval_result.action == ResolutionAction.INFORM_ONLY:
            return {
                "status": "inform",
                "reason": intent_obj.explanation or eval_result.reason,
                "order_status": eval_result.order_status,
                "fulfillment_status": eval_result.fulfillment_status,
                "return_status": eval_result.return_status,
                "refund_status": eval_result.refund_status,
                "intent": intent_obj.intent,
                "explanation": intent_obj.explanation
            }

        if eval_result.action in [ResolutionAction.INITIATE_REFUND, ResolutionAction.CANCEL_ORDER_ONLY]:
            exec_result = create_and_execute_refund(
                cart_id=req.cart_id,
                requested_amount_paise=eval_result.refundable_amount_paise,
                reason=intent_obj.reason or "Customer request"
            )
            return {
                "status": "refunded" if eval_result.action == ResolutionAction.INITIATE_REFUND else "cancelled",
                "order_status": exec_result.get("order_status"),
                "cancellation_status": exec_result.get("cancellation_status"),
                "fulfillment_status": exec_result.get("fulfillment_status"),
                "return_status": exec_result.get("return_status"),
                "refund_status": exec_result.get("refund_status"),
                "refund_id": exec_result.get("refund_id"),
                "amount_refunded_paise": exec_result.get("amount_refunded_paise", 0),
                "reason": exec_result.get("reason"),
                "intent": intent_obj.intent,
                "explanation": intent_obj.explanation
            }

        if eval_result.action in [ResolutionAction.CREATE_RETURN_REVIEW, ResolutionAction.CREATE_REFUND_REVIEW]:
            exec_result = create_and_execute_refund(
                cart_id=req.cart_id,
                requested_amount_paise=req_amount,
                reason=intent_obj.reason or "Review required"
            )
            return {
                "status": "review_required",
                "order_status": exec_result.get("order_status"),
                "fulfillment_status": exec_result.get("fulfillment_status"),
                "return_status": exec_result.get("return_status"),
                "refund_status": exec_result.get("refund_status"),
                "reason": eval_result.reason,
                "intent": intent_obj.intent,
                "explanation": intent_obj.explanation
            }

        # Ineligible / Escalate
        return {
            "status": "denied",
            "eligibility_status": eval_result.status,
            "reason": eval_result.reason,
            "order_status": eval_result.order_status,
            "fulfillment_status": eval_result.fulfillment_status,
            "return_status": eval_result.return_status,
            "refund_status": eval_result.refund_status,
            "intent": intent_obj.intent,
            "explanation": intent_obj.explanation
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
