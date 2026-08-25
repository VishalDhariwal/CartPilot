from fastapi import APIRouter, Request, HTTPException
import razorpay
from backend.integrations.razorpay_client import verify_webhook_signature
from backend.engine.mandates import update_payment_mandate_status

router = APIRouter()

@router.post("/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        verify_webhook_signature(body.decode("utf-8"), signature)
    except razorpay.errors.SignatureVerificationError:
        print("⚠️ Webhook signature verification failed!")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"⚠️ Error verifying signature: {e}")
        raise HTTPException(status_code=400, detail="Error verifying signature")

    payload = await request.json()
    event = payload.get("event")

    if event in ["payment.captured", "payment.failed", "payment_link.paid", "order.paid"]:
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        plink_entity = payload.get('payload', {}).get('payment_link', {}).get('entity', {})
        
        order_id = payment_entity.get('order_id')
        notes = payment_entity.get('notes', {}) or plink_entity.get('notes', {})
        custom_order_id = notes.get('order_id')
        cart_id = notes.get('cart_id') or plink_entity.get('reference_id')
        payment_id = payment_entity.get('id')
        
        target_order_id = custom_order_id or order_id

        if event in ["payment.captured", "payment_link.paid", "order.paid"]:
            print(f"✅ Webhook Event: {event} for order {target_order_id} / cart {cart_id}")
            update_payment_mandate_status(
                razorpay_order_id=target_order_id,
                cart_id=cart_id,
                status="succeeded",
                payment_id=payment_id
            )
            
        elif event == "payment.failed":
            failure_reason = payment_entity.get('error_description', 'Payment failed')
            print(f"❌ Webhook Event: payment.failed for order {target_order_id} / cart {cart_id} - Reason: {failure_reason}")
            
            from backend.agents.recovery_agent import analyze_failure
            recovery_data = analyze_failure(failure_reason)
            recommendation = recovery_data["recommendation"]
            
            update_payment_mandate_status(
                razorpay_order_id=target_order_id,
                cart_id=cart_id,
                status="failed",
                failure_reason=failure_reason,
                payment_id=payment_id,
                recovery_action=recommendation
            )

    elif event in ["refund.processed", "refund.created", "refund.failed", "refund.speed_changed"]:
        refund_entity = payload.get('payload', {}).get('refund', {}).get('entity', {})
        refund_id = refund_entity.get('id')
        print(f"🔄 Webhook Event: {event} for refund {refund_id}")
        
        from backend.engine.resolution_engine import settle_refund_webhook
        settle_refund_webhook(
            razorpay_refund_id=refund_id,
            event_type=event,
            refund_entity=refund_entity
        )

    return {"status": "ok"}
