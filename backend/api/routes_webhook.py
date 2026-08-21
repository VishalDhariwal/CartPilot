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

    if event in ["payment.captured", "payment.failed"]:
        payment_entity = payload['payload']['payment']['entity']
        order_id = payment_entity.get('order_id')
        payment_id = payment_entity.get('id')
        
        if event == "payment.captured":
            print(f"✅ Webhook Event: payment.captured for order {order_id}")
            update_payment_mandate_status(
                razorpay_order_id=order_id,
                status="succeeded",
                payment_id=payment_id
            )
            
        elif event == "payment.failed":
            failure_reason = payment_entity.get('error_description')
            print(f"❌ Webhook Event: payment.failed for order {order_id} - Reason: {failure_reason}")
            update_payment_mandate_status(
                razorpay_order_id=order_id,
                status="failed",
                failure_reason=failure_reason,
                payment_id=payment_id
            )
            # Phase 6 will handle recovery action here

    return {"status": "ok"}
