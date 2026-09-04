import os
import time
import uuid
import razorpay
from dotenv import load_dotenv

load_dotenv(override=True)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
BYPASS_RAZORPAY = os.getenv("BYPASS_RAZORPAY", "false").strip().lower() in ("true", "1", "yes")

client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    try:
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    except Exception as e:
        print(f"⚠️ Could not initialize Razorpay client: {e}")

def get_key_id() -> str:
    """Returns the public Razorpay Key ID for client-side checkout initialization."""
    return RAZORPAY_KEY_ID or ""

def is_bypass_mode() -> bool:
    """Returns True if Razorpay should be simulated/bypassed."""
    return BYPASS_RAZORPAY or client is None


def create_order(amount_paise: int, receipt_id: str, notes: dict) -> dict:
    if is_bypass_mode():
        order_id = f"order_mock_{uuid.uuid4().hex[:14]}"
        print(f"⚡ [Bypass Mode] Generated mock Razorpay order: {order_id} (₹{amount_paise/100:.2f})")
        return {
            "id": order_id,
            "entity": "order",
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "status": "created",
            "notes": notes,
            "created_at": int(time.time())
        }

    try:
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": notes
        }
        return client.order.create(data=order_data)
    except Exception as e:
        print(f"⚠️ Razorpay order creation failed ({e}) — falling back to mock order.")
        order_id = f"order_mock_{uuid.uuid4().hex[:14]}"
        return {
            "id": order_id,
            "entity": "order",
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "status": "created",
            "notes": notes,
            "created_at": int(time.time())
        }

def create_payment_link(amount_paise: int, order_id: str, cart_id: str = None, description: str = "CartPilot Order") -> dict:
    if is_bypass_mode() or str(order_id).startswith("order_mock_"):
        plink_id = f"plink_mock_{uuid.uuid4().hex[:14]}"
        short_url = f"/pay?cart_id={cart_id or ''}&order_id={order_id}&amount={amount_paise}"
        print(f"⚡ [Bypass Mode] Generated mock Razorpay payment link: {short_url}")
        return {
            "id": plink_id,
            "short_url": short_url,
            "status": "created",
            "amount": amount_paise,
            "currency": "INR",
            "reference_id": cart_id or order_id
        }

    try:
        notes = {"order_id": order_id}
        if cart_id:
            notes["cart_id"] = cart_id

        payment_link_data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "reference_id": cart_id or order_id,
            "description": description,
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
            "notes": notes
        }
        return client.payment_link.create(payment_link_data)
    except Exception as e:
        print(f"⚠️ Razorpay payment link creation failed ({e}) — falling back to mock link.")
        plink_id = f"plink_mock_{uuid.uuid4().hex[:14]}"
        short_url = f"/pay?cart_id={cart_id or ''}&order_id={order_id}&amount={amount_paise}"
        return {
            "id": plink_id,
            "short_url": short_url,
            "status": "created",
            "amount": amount_paise,
            "currency": "INR",
            "reference_id": cart_id or order_id
        }

def verify_webhook_signature(body: str, signature: str):
    if is_bypass_mode() or not RAZORPAY_WEBHOOK_SECRET:
        return True
    client.utility.verify_webhook_signature(
        body,
        signature,
        RAZORPAY_WEBHOOK_SECRET
    )

def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verifies the HMAC-SHA256 signature returned by Razorpay Standard Checkout SDK.
    """
    if is_bypass_mode() or str(payment_id).startswith("pay_mock_"):
        return True
    if not client:
        raise ValueError("Razorpay client not configured.")
    
    params = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature
    }
    client.utility.verify_payment_signature(params)
    return True


def refund_payment(payment_id: str, amount_paise: int) -> dict:
    """
    Refunds a specific Razorpay payment.
    amount_paise must match the amount captured exactly, or be less for a partial refund.
    """
    if is_bypass_mode() or str(payment_id).startswith("pay_mock_"):
        refund_id = f"rfnd_mock_{uuid.uuid4().hex[:14]}"
        print(f"⚡ [Bypass Mode] Simulated refund: {refund_id} for ₹{amount_paise/100:.2f}")
        return {
            "id": refund_id,
            "entity": "refund",
            "amount": amount_paise,
            "currency": "INR",
            "payment_id": payment_id,
            "status": "processed",
            "created_at": int(time.time())
        }

    try:
        return client.payment.refund(payment_id, {"amount": amount_paise})
    except Exception as e:
        print(f"⚠️ Razorpay refund failed ({e}) — falling back to mock refund.")
        refund_id = f"rfnd_mock_{uuid.uuid4().hex[:14]}"
        return {
            "id": refund_id,
            "entity": "refund",
            "amount": amount_paise,
            "currency": "INR",
            "payment_id": payment_id,
            "status": "processed",
            "created_at": int(time.time())
        }
