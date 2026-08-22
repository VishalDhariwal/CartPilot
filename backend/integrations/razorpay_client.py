import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in .env")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def create_order(amount_paise: int, receipt_id: str, notes: dict) -> dict:
    order_data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt_id,
        "notes": notes
    }
    return client.order.create(data=order_data)

def create_payment_link(amount_paise: int, order_id: str, cart_id: str = None, description: str = "CartPilot Order") -> dict:
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

def verify_webhook_signature(body: str, signature: str):
    client.utility.verify_webhook_signature(
        body,
        signature,
        RAZORPAY_WEBHOOK_SECRET
    )

def refund_payment(payment_id: str, amount_paise: int) -> dict:
    """
    Refunds a specific Razorpay payment.
    amount_paise must match the amount captured exactly, or be less for a partial refund.
    """
    return client.payment.refund(payment_id, {"amount": amount_paise})
