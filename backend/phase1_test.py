import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
import razorpay
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in .env")

# Initialize Razorpay Client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

app = FastAPI(title="CartPilot Phase 1 Test")

@app.post("/create-test-order")
def create_test_order():
    """
    1. Creates a Razorpay test-mode Order for a fixed amount (₹420).
    2. Generates a Payment Link for that order.
    """
    amount_paise = 42000  # ₹420 in paise
    currency = "INR"
    receipt_id = "test_receipt_123"

    try:
        # Create Order
        order_data = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt_id,
            "notes": {
                "description": "Phase 1 test order"
            }
        }
        order = client.order.create(data=order_data)
        order_id = order['id']
        print(f"Created Order: {order_id}")

        # Create Payment Link
        # According to Razorpay docs, payment link creation uses invoices or payment_link API
        payment_link_data = {
            "amount": amount_paise,
            "currency": currency,
            "accept_partial": False,
            "description": "Payment for Phase 1 test order",
            "customer": {
                "name": "Test Customer",
                "email": "test@example.com",
                "contact": "+919876543210"
            },
            "notify": {
                "sms": False,
                "email": False
            },
            "reminder_enable": False,
            "notes": {
                "order_id": order_id
            }
        }
        payment_link = client.payment_link.create(payment_link_data)
        
        return {
            "order_id": order_id,
            "payment_link_id": payment_link['id'],
            "payment_url": payment_link['short_url']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    """
    Sets up a local webhook receiver that logs incoming payment.captured 
    and payment.failed events to the console.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        # Verify webhook signature
        client.utility.verify_webhook_signature(
            body.decode("utf-8"),
            signature,
            RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError:
        print("⚠️ Webhook signature verification failed!")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"⚠️ Error verifying signature: {e}")
        raise HTTPException(status_code=400, detail="Error verifying signature")

    # Parse payload
    payload = await request.json()
    event = payload.get("event")

    if event == "payment.captured":
        payment_entity = payload['payload']['payment']['entity']
        print("\n✅ Webhook Event: payment.captured")
        print(f"   Payment ID: {payment_entity.get('id')}")
        print(f"   Order ID: {payment_entity.get('order_id')}")
        print(f"   Amount: {payment_entity.get('amount')} paise")
    
    elif event == "payment.failed":
        payment_entity = payload['payload']['payment']['entity']
        print("\n❌ Webhook Event: payment.failed")
        print(f"   Payment ID: {payment_entity.get('id')}")
        print(f"   Order ID: {payment_entity.get('order_id')}")
        print(f"   Failure Reason: {payment_entity.get('error_description')}")
        print(f"   Amount: {payment_entity.get('amount')} paise")

    else:
        # Log other events optionally, but brief requested captured/failed
        print(f"ℹ️ Webhook Event Received: {event}")

    return {"status": "ok"}

if __name__ == "__main__":
    print("Starting Phase 1 Test Server...")
    print("Use /create-test-order to generate a payment link.")
    print("Ensure ngrok is forwarding to port 8000 and the webhook URL is configured.")
    uvicorn.run("phase1_test:app", host="127.0.0.1", port=8000, reload=True)
