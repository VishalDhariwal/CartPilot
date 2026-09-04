from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from backend.engine.mandates import (
    create_intent_mandate, create_cart_mandate, create_payment_mandate,
    append_audit_log, get_cart_state, update_payment_mandate_status
)
from backend.engine.guardrail import validate_cart
from backend.engine.payment_engine import (
    execute_payment_mandate,
    verify_and_settle_payment,
    get_public_checkout_config,
    CartAlreadyConsumedError,
)

from backend.agents.buyer_agent import generate_cart_proposal

from backend.agents.growth_agent import generate_upsell
from backend.agents.substitution_agent import find_substitute
from backend.db import get_db

router = APIRouter()


class ChatHistoryMessage(BaseModel):
    role: str
    content: str

class AgentCheckoutRequest(BaseModel):
    query: str
    spend_cap_paise: Optional[int] = None
    conversation_history: Optional[list[ChatHistoryMessage]] = None
    current_cart: Optional[list[dict]] = None

class FinalizeRequest(BaseModel):
    cart_id: str
    accept_upsell: bool = False
    upsell_accepted: Optional[bool] = None
    upsell_sku: Optional[str] = None

    def is_upsell_accepted(self) -> bool:
        if self.upsell_accepted is not None:
            return self.upsell_accepted
        return self.accept_upsell


class AcceptSubstituteRequest(BaseModel):
    intent_id: str
    original_sku: str
    substitute_sku: Optional[str] = None   # None = user declined, drop the item
    remaining_items: list                   # All other items (without the OOS item)
    total_paise_without_oos: int

class CartItemInput(BaseModel):
    sku: str
    qty: int
    selected_size: Optional[str] = None

class UpdateCartRequest(BaseModel):
    cart_id: str
    items: list[CartItemInput]


def _record_upsell_event(cart_id: str, suggested_sku: str, accepted: bool,
                          cart_total_before: int, cart_total_after: int):
    """Write a row to upsell_events and record incremental revenue in growth_outcomes."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            """INSERT INTO upsell_events
               (cart_id, suggested_sku, accepted, cart_total_before_paise,
                cart_total_after_paise, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cart_id, suggested_sku, 1 if accepted else 0,
             cart_total_before, cart_total_after,
             now_str)
        )
        
        if accepted:
            inc_paise = max(0, cart_total_after - cart_total_before)
            outcome_id = f"go_xs_{uuid.uuid4().hex[:10]}"
            cursor.execute(
                """INSERT INTO growth_outcomes
                   (id, action_id, outcome_type, before_paise, after_paise, incremental_paise, revenue_type, created_at)
                   VALUES (?, ?, 'accepted', ?, ?, ?, 'cross_sell', ?)""",
                (outcome_id, None, cart_total_before, cart_total_after, inc_paise, now_str)
            )

        conn.commit()
    finally:
        conn.close()


@router.post("/agent-checkout")
def agent_checkout(req: AgentCheckoutRequest):
    """
    Full LangGraph-powered agent checkout pipeline:
      1. LangGraph AI Buyer Orchestrator executes intent understanding, catalog search,
         budget self-correction (up to 3 revisions), guardrail validation, and 4-tier recommendations.
      2. Returns structured cart, intent, recommendations, and execution decision trace.
    """
    try:
        from backend.agents.buyer_graph import run_buyer_journey
        history_dicts = [m.model_dump() for m in req.conversation_history] if req.conversation_history else None

        # Execute LangGraph Buyer Journey
        state = run_buyer_journey(
            query=req.query,
            spend_cap_paise=req.spend_cap_paise,
            conversation_history=history_dicts,
            auto_authorize=False,
            current_cart=req.current_cart
        )

        intent_obj = {
            "id": state.get("intent_id") or "intent_unknown",
            "goal": state.get("goal") or req.query,
            "spend_cap_paise": state.get("spend_cap_paise") or 1000000
        }

        # Handle Guardrail Blocked
        if state.get("guardrail_status") == "blocked" or not state.get("proposed_items"):
            return {
                "status": "blocked",
                "reason": state.get("guardrail_reason") or "No valid items found matching active merchant policy.",
                "message": state.get("assistant_message") or state.get("guardrail_reason"),
                "cart_id": state.get("cart_id"),
                "intent": intent_obj,
                "proposed_items": state.get("proposed_items", []),
                "total_paise": state.get("cart_total_paise", 0),
                "revision_count": state.get("revision_count", 0),
                "decision_trace": state.get("decision_trace", [])
            }

        # Build Upsell / Growth Recommendations
        recs = state.get("recommendations", [])
        upsell = None
        if recs:
            upsell = {
                "sku": recs[0]["sku"],
                "name": recs[0]["name"],
                "price_paise": recs[0]["price_paise"],
                "category": recs[0]["category"],
                "image_url": recs[0].get("image_url", ""),
                "description": recs[0].get("description", ""),
                "metadata": recs[0].get("metadata", {}),
                "reason": recs[0].get("reason", "Frequently purchased together."),
                "candidates": recs
            }

        return {
            "status": "upsell_offered" if upsell else "approved",
            "cart_id": state.get("cart_id"),
            "intent": intent_obj,
            "message": state.get("assistant_message"),
            "proposed_items": state.get("proposed_items", []),
            "total_paise": state.get("cart_total_paise", 0),
            "guardrail_reason": state.get("guardrail_reason"),
            "upsell": upsell,
            "revision_count": state.get("revision_count", 0),
            "buyer_authorization_status": state.get("buyer_authorization_status"),
            "decision_trace": state.get("decision_trace", [])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/update-cart")
def update_cart(req: UpdateCartRequest):
    """
    Allows the user to edit items and quantities in their proposed cart.
    Re-validates against the Guardrail Engine, logs the change, and re-computes Growth upsells.
    """
    try:
        state = get_cart_state(req.cart_id)
        if not state or not state["cart"]:
            raise HTTPException(status_code=404, detail="Cart not found")

        original_cart = state["cart"]

        if not req.items or len(req.items) == 0:
            return {
                "status": "blocked",
                "reason": "Cart cannot be empty. Please keep at least one item or start a new order.",
                "cart_id": original_cart["id"]
            }

        conn = get_db()
        cursor = conn.cursor()
        enriched_items = []
        for item in req.items:
            if item.qty <= 0:
                continue
            cursor.execute("SELECT sku, name, price_paise, category, stock, image_url, description, metadata FROM catalog WHERE sku = ?", (item.sku,))
            row = cursor.fetchone()
            if not row:
                continue
            meta_obj = {}
            if row["metadata"]:
                try:
                    meta_obj = json.loads(row["metadata"])
                except Exception:
                    meta_obj = {}
            enriched_items.append({
                "sku": row["sku"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "qty": item.qty,
                "category": row["category"],
                "stock": row["stock"],
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "metadata": meta_obj,
                "selected_size": item.selected_size
            })
        conn.close()

        if not enriched_items:
            return {
                "status": "blocked",
                "reason": "All item quantities were 0. Cart cannot be empty.",
                "cart_id": original_cart["id"]
            }

        total_paise = sum(item["price_paise"] * item["qty"] for item in enriched_items)

        # Validate through Guardrail
        validation = validate_cart(original_cart["intent_id"], enriched_items, total_paise)

        # Create updated cart mandate
        new_cart = create_cart_mandate(
            intent_id=original_cart["intent_id"],
            items=enriched_items,
            total_paise=total_paise,
            status=validation["status"],
            reason=validation["reason"],
            reversible=validation["reversible"]
        )

        append_audit_log(
            "cart", new_cart["id"], "Cart Edited by Customer",
            f"Updated to {len(enriched_items)} item(s), new total: ₹{total_paise/100:.0f}. Guardrail: {validation['reason']}"
        )

        # Record upsell event when cart value expands via recommendation additions
        if total_paise > original_cart["total_paise"] and new_cart["status"] != "blocked":
            try:
                orig_raw = original_cart["items"]
                orig_parsed = json.loads(orig_raw) if isinstance(orig_raw, str) else orig_raw
                orig_skus = {it.get("sku") for it in orig_parsed if isinstance(it, dict)}
                added_skus = [it["sku"] for it in enriched_items if it["sku"] not in orig_skus]
                for added_sku in added_skus:
                    _record_upsell_event(
                        cart_id=new_cart["id"],
                        suggested_sku=added_sku,
                        accepted=True,
                        cart_total_before=original_cart["total_paise"],
                        cart_total_after=total_paise
                    )
            except Exception as e:
                print(f"Error recording upsell event in update_cart: {e}")

        if new_cart["status"] == "blocked":
            return {
                "status": "blocked",
                "reason": new_cart["reason"],
                "cart_id": new_cart["id"],
                "proposed_items": enriched_items,
                "total_paise": total_paise
            }

        # Re-evaluate upsell for the edited cart
        upsell = generate_upsell(enriched_items)
        if upsell:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT sku, name, price_paise, category, image_url, description FROM catalog WHERE sku = ?", (upsell["sku"],))
            row = cursor.fetchone()
            conn.close()
            if row:
                upsell.update({
                    "name": row["name"],
                    "price_paise": row["price_paise"],
                    "category": row["category"],
                    "image_url": row["image_url"] or upsell.get("image_url", ""),
                    "description": row["description"] or upsell.get("description", "")
                })
                append_audit_log(
                    "upsell", new_cart["id"], "Upsell Offered",
                    f"SKU: {upsell['sku']} ({upsell['name']}) — ₹{upsell['price_paise']/100:.0f}. Reason: {upsell['reason']}"
                )
            else:
                upsell = None

        return {
            "status": "upsell_offered",
            "cart_id": new_cart["id"],
            "proposed_items": enriched_items,
            "total_paise": total_paise,
            "guardrail_reason": validation["reason"],
            "upsell": upsell
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accept-substitute")
def accept_substitute(req: AcceptSubstituteRequest):
    """
    Handle the user's response to a substitution offer.
    - If accepted: add the substitute to the cart, run guardrail, return upsell offer.
    - If declined (substitute_sku=None): proceed with remaining items only.
    Both outcomes are logged. Guardrail is always re-run.
    """
    try:
        items = list(req.remaining_items)
        total_paise = req.total_paise_without_oos

        if req.substitute_sku:
            # User accepted the substitute — fetch its details
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM catalog WHERE sku = ?", (req.substitute_sku,))
            sub_row = cursor.fetchone()
            conn.close()

            if not sub_row:
                raise HTTPException(status_code=404, detail="Substitute SKU not found in catalog")

            items.append({
                "sku": sub_row["sku"],
                "name": sub_row["name"],
                "qty": 1,
                "price_paise": sub_row["price_paise"],
                "category": sub_row["category"],
                "image_url": sub_row["image_url"] or "",
                "description": sub_row["description"] or ""
            })
            total_paise += sub_row["price_paise"]

            append_audit_log(
                "substitution", req.intent_id, "Substitute Accepted",
                f"Customer accepted {sub_row['sku']} ({sub_row['name']}) "
                f"at ₹{sub_row['price_paise']/100:.0f} as substitute. "
                f"New cart total: ₹{total_paise/100:.0f}"
            )
        else:
            append_audit_log(
                "substitution", req.intent_id, "Substitute Declined",
                f"Customer declined the substitute. Proceeding with {len(items)} remaining items."
            )

        if not items:
            return {
                "status": "blocked",
                "reason": "Cart is empty after declining the substitute.",
                "cart_id": None
            }

        # Always run guardrail on the final item list
        validation = validate_cart(req.intent_id, items, total_paise)

        cart = create_cart_mandate(
            intent_id=req.intent_id,
            items=items,
            total_paise=total_paise,
            status=validation["status"],
            reason=validation["reason"],
            reversible=validation["reversible"]
        )

        if cart["status"] == "blocked":
            return {
                "status": "blocked",
                "reason": cart["reason"],
                "cart_id": cart["id"]
            }

        # Offer cross-sell now that cart is approved
        upsell = generate_upsell(items)
        if upsell:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sku, name, price_paise, category FROM catalog WHERE sku = ?",
                (upsell["sku"],)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                upsell.update({"name": row["name"], "price_paise": row["price_paise"], "category": row["category"]})
                append_audit_log(
                    "upsell", cart["id"], "Upsell Offered",
                    f"SKU: {upsell['sku']} ({upsell['name']}) — ₹{upsell['price_paise']/100:.0f}. "
                    f"Reason: {upsell['reason']}"
                )
            else:
                upsell = None

        return {
            "status": "upsell_offered",
            "cart_id": cart["id"],
            "proposed_items": items,
            "total_paise": total_paise,
            "guardrail_reason": validation["reason"],
            "upsell": upsell
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConfirmMandateRequest(BaseModel):
    cart_id: str


@router.post("/confirm-mandate")
def confirm_mandate(req: ConfirmMandateRequest):
    """
    Explicitly approves a cart mandate in 'pending_confirmation' status.
    Transitions status to 'approved' and logs the authorization in audit_log.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM cart_mandates WHERE id = ?", (req.cart_id,))
        cart = cursor.fetchone()
        if not cart:
            raise HTTPException(status_code=404, detail="Cart mandate not found")

        cursor.execute("UPDATE cart_mandates SET status = 'approved' WHERE id = ?", (req.cart_id,))
        conn.commit()

        items = json.loads(cart["items"]) if isinstance(cart["items"], str) else cart["items"]
        total_paise = cart["total_paise"]

        append_audit_log(
            "cart", req.cart_id, "Autonomy Threshold Mandate Confirmed",
            f"High-value order (₹{total_paise/100:.2f}, {len(items)} item(s)) explicitly confirmed by merchant/buyer. Approved for checkout."
        )

        return {
            "status": "approved",
            "cart_id": req.cart_id,
            "message": "Cart mandate confirmed and approved for payment."
        }
    finally:
        conn.close()


@router.post("/finalize")
def finalize_checkout(req: FinalizeRequest):
    """
    Finalize checkout: accept or decline upsell, re-run guardrail if accepted,
    create Razorpay order + payment link, record upsell_events for measurement.
    """
    try:
        state = get_cart_state(req.cart_id)
        if not state or not state["cart"]:
            raise HTTPException(status_code=404, detail="Cart not found")

        original_cart = state["cart"]
        if original_cart["status"] not in ["approved", "pending_confirmation"]:
            raise HTTPException(status_code=400, detail="Cannot finalize a blocked cart")

        final_cart_id = original_cart["id"]
        final_total_paise = original_cart["total_paise"]
        cart_total_before = original_cart["total_paise"]

        if original_cart["status"] == "pending_confirmation":
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE cart_mandates SET status = 'approved' WHERE id = ?", (final_cart_id,))
            conn.commit()
            conn.close()
            append_audit_log(
                "cart", final_cart_id, "Autonomy Threshold Mandate Confirmed",
                f"High-value order (₹{final_total_paise/100:.2f}) confirmed during checkout; payment order initiated."
            )


        if not req.is_upsell_accepted():
            append_audit_log(
                "upsell", final_cart_id, "Upsell Declined",
                "Customer chose to proceed with original cart without the upsell item"
            )
            # Record event: declined
            if req.upsell_sku:
                _record_upsell_event(
                    cart_id=final_cart_id,
                    suggested_sku=req.upsell_sku,
                    accepted=False,
                    cart_total_before=cart_total_before,
                    cart_total_after=cart_total_before  # no change
                )
        else:
            if not req.upsell_sku:
                raise HTTPException(status_code=400, detail="upsell_sku is required when accepting upsell")

            # Fetch upsell item from catalog
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM catalog WHERE sku = ?", (req.upsell_sku,))
            upsell_row = cursor.fetchone()
            conn.close()

            if not upsell_row:
                raise HTTPException(status_code=404, detail="Upsell item not found in catalog")

            # Build new item list
            items = json.loads(original_cart["items"])
            items.append({
                "sku": upsell_row["sku"],
                "name": upsell_row["name"],
                "qty": 1,
                "price_paise": upsell_row["price_paise"],
                "category": upsell_row["category"]
            })
            new_total = sum(item["price_paise"] * item["qty"] for item in items)

            # Re-validate through the SAME Guardrail Engine — no bypass
            validation = validate_cart(original_cart["intent_id"], items, new_total)

            # Create a new cart mandate for the expanded cart
            new_cart = create_cart_mandate(
                intent_id=original_cart["intent_id"],
                items=items,
                total_paise=new_total,
                status=validation["status"],
                reason=validation["reason"],
                reversible=validation["reversible"]
            )

            if new_cart["status"] == "blocked":
                append_audit_log(
                    "upsell", new_cart["id"], "Upsell Blocked by Guardrail",
                    f"Upsell SKU {req.upsell_sku} pushed cart over limit. {validation['reason']}"
                )
                # Record event: attempted but blocked (count as declined for measurement)
                _record_upsell_event(
                    cart_id=new_cart["id"],
                    suggested_sku=req.upsell_sku,
                    accepted=False,
                    cart_total_before=cart_total_before,
                    cart_total_after=cart_total_before
                )
                return {
                    "status": "blocked",
                    "reason": new_cart["reason"],
                    "fallback_cart_id": original_cart["id"],
                    "message": "Upsell was blocked by the guardrail. You can still complete the original order."
                }

            append_audit_log(
                "upsell", new_cart["id"], "Upsell Accepted",
                f"SKU {req.upsell_sku} ({upsell_row['name']}) added. "
                f"New total: ₹{new_total/100:.0f}. Guardrail: {validation['reason']}"
            )
            # Record event: accepted
            _record_upsell_event(
                cart_id=new_cart["id"],
                suggested_sku=req.upsell_sku,
                accepted=True,
                cart_total_before=cart_total_before,
                cart_total_after=new_total
            )

            final_cart_id = new_cart["id"]
            final_total_paise = new_cart["total_paise"]

        # Execute Payment through Authoritative PaymentEngine Choke Point
        pay_res = execute_payment_mandate(
            cart_id=final_cart_id,
            description="CartPilot Order",
            notes={"cart_id": final_cart_id}
        )

        return {
            "status": "approved",
            "payment_url": pay_res["payment_link_url"],
            "payment_link": pay_res["payment_link_url"],
            "cart_id": final_cart_id,
            "payment_mandate_id": pay_res["payment_mandate_id"],
            "razorpay_order_id": pay_res["razorpay_order_id"],
            "amount_paise": pay_res["amount_paise"],
            "amount_rupees": pay_res.get("amount_rupees", round(pay_res["amount_paise"] / 100, 2)),
            "key_id": pay_res.get("key_id", ""),
            "currency": pay_res.get("currency", "INR")
        }


    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateOrderRequest(BaseModel):
    cart_id: str


class VerifyPaymentRequest(BaseModel):
    cart_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/create-order")
def create_checkout_order(req: CreateOrderRequest):
    """
    Creates a real Razorpay order for an approved cart mandate.
    Returns key_id, razorpay_order_id, amount_paise, and currency for Razorpay Standard Checkout SDK.
    """
    try:
        pay_res = execute_payment_mandate(
            cart_id=req.cart_id,
            description="CartPilot Order",
            notes={"cart_id": req.cart_id}
        )
        return {
            "success": True,
            "cart_id": req.cart_id,
            "razorpay_order_id": pay_res["razorpay_order_id"],
            "amount_paise": pay_res["amount_paise"],
            "amount_rupees": pay_res.get("amount_rupees", round(pay_res["amount_paise"] / 100, 2)),
            "currency": pay_res.get("currency", "INR"),
            "key_id": pay_res.get("key_id", ""),
            "payment_mandate_id": pay_res["payment_mandate_id"],
            "payment_link_url": pay_res["payment_link_url"]
        }
    except CartAlreadyConsumedError:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM payment_mandates WHERE cart_id = ?", (req.cart_id,))
            existing_pm = cursor.fetchone()
            if existing_pm and existing_pm["status"] == "created":
                cfg = get_public_checkout_config()
                return {
                    "success": True,
                    "cart_id": req.cart_id,
                    "razorpay_order_id": existing_pm["razorpay_order_id"],
                    "amount_paise": existing_pm["amount_paise"],
                    "amount_rupees": round(existing_pm["amount_paise"] / 100, 2),
                    "currency": "INR",
                    "key_id": cfg["key_id"],
                    "payment_mandate_id": existing_pm["id"],
                    "payment_link_url": f"/pay?cart_id={req.cart_id}&order_id={existing_pm['razorpay_order_id']}&amount={existing_pm['amount_paise']}"
                }
            raise HTTPException(status_code=400, detail="Cart has already been consumed or settled.")
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.post("/verify")
def verify_payment(req: VerifyPaymentRequest):
    """
    Verifies cryptographic Razorpay payment signature and settles order.
    """
    try:
        res = verify_and_settle_payment(
            cart_id=req.cart_id,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config")
def get_checkout_config():
    """
    Returns public Razorpay configuration (Key ID only) for client-side checkout.
    """
    return get_public_checkout_config()


class PostPurchaseAddRequest(BaseModel):

    parent_cart_id: str
    sku: str
    qty: int = 1
    selected_size: Optional[str] = None


@router.post("/post-purchase-add")
def post_purchase_add(req: PostPurchaseAddRequest):
    """
    1-Click Post-Purchase Add-on:
    When a customer accepts a complementary recommendation after completing their initial order,
    this creates a companion add-on order mandate linked to the parent order, generates a Razorpay payment link,
    and logs the post-purchase revenue expansion.
    """
    try:
        parent_state = get_cart_state(req.parent_cart_id)
        if not parent_state or not parent_state["cart"]:
            raise HTTPException(status_code=404, detail="Parent order not found")

        parent_cart = parent_state["cart"]
        intent_id = parent_cart["intent_id"]

        # Fetch product
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT sku, name, price_paise, category, stock, image_url, description, metadata FROM catalog WHERE sku = ?", (req.sku,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Product {req.sku} not found")

        meta_obj = {}
        if row["metadata"]:
            try:
                meta_obj = json.loads(row["metadata"])
            except Exception:
                meta_obj = {}

        item_total_paise = row["price_paise"] * req.qty
        addon_items = [{
            "sku": row["sku"],
            "name": row["name"],
            "price_paise": row["price_paise"],
            "qty": req.qty,
            "category": row["category"],
            "image_url": row["image_url"] or "",
            "description": row["description"] or "",
            "metadata": meta_obj,
            "selected_size": req.selected_size
        }]

        # Validate through Guardrail
        validation = validate_cart(intent_id, addon_items, item_total_paise)
        if validation["status"] == "blocked":
            return {
                "status": "blocked",
                "reason": validation["reason"],
                "message": "Post-purchase add-on blocked by policy guardrails."
            }

        # Create companion cart mandate
        addon_cart = create_cart_mandate(
            intent_id=intent_id,
            items=addon_items,
            total_paise=item_total_paise,
            status="approved",
            reason=f"Post-purchase 1-click add-on to order {req.parent_cart_id}",
            reversible=True
        )

        # Execute Payment through Authoritative PaymentEngine Choke Point
        pay_res = execute_payment_mandate(
            cart_id=addon_cart["id"],
            description=f"Add-on: {row['name']}",
            notes={"parent_cart_id": req.parent_cart_id, "type": "post_purchase_addon"}
        )

        append_audit_log(
            "upsell", addon_cart["id"], "Post-Purchase Add-on Created",
            f"Customer added {row['name']} (₹{item_total_paise/100:.0f}) as post-purchase companion to {req.parent_cart_id}."
        )

        _record_upsell_event(
            cart_id=addon_cart["id"],
            suggested_sku=req.sku,
            accepted=True,
            cart_total_before=parent_cart["total_paise"],
            cart_total_after=parent_cart["total_paise"] + item_total_paise
        )

        return {
            "status": "approved",
            "cart_id": addon_cart["id"],
            "parent_cart_id": req.parent_cart_id,
            "items": addon_items,
            "proposed_items": addon_items,
            "total_paise": item_total_paise,
            "payment_url": payment_link["short_url"],
            "payment_link": payment_link["short_url"],
            "payment_mandate_id": payment_mandate["id"],
            "razorpay_order_id": order["id"],
            "amount_paise": item_total_paise
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class OrchestratedCheckoutRequest(BaseModel):
    query: str
    spend_cap_paise: Optional[int] = None
    session_id: Optional[str] = None
    auto_authorize: bool = False
    conversation_history: Optional[list[ChatHistoryMessage]] = None
    current_cart: Optional[list[dict]] = None


@router.post("/orchestrated-checkout")
def orchestrated_checkout(req: OrchestratedCheckoutRequest):
    """
    Executes the LangGraph AI Buyer Orchestrator pipeline.
    Combines multi-step intent understanding, budget self-correction, guardrails,
    4-tier recommendations, buyer authorization gates, and Razorpay checkout.
    """
    try:
        from backend.agents.buyer_graph import run_buyer_journey
        history_dicts = [m.model_dump() for m in req.conversation_history] if req.conversation_history else None
        
        final_state = run_buyer_journey(
            query=req.query,
            spend_cap_paise=req.spend_cap_paise,
            session_id=req.session_id,
            auto_authorize=req.auto_authorize,
            conversation_history=history_dicts,
            current_cart=req.current_cart
        )
        
        return {
            "status": final_state.get("guardrail_status"),
            "buyer_authorization_status": final_state.get("buyer_authorization_status"),
            "cart_id": final_state.get("cart_id"),
            "intent_id": final_state.get("intent_id"),
            "goal": final_state.get("goal"),
            "spend_cap_paise": final_state.get("spend_cap_paise"),
            "total_paise": final_state.get("cart_total_paise"),
            "proposed_items": final_state.get("proposed_items"),
            "oos_items": final_state.get("oos_items"),
            "revision_count": final_state.get("revision_count"),
            "guardrail_reason": final_state.get("guardrail_reason"),
            "recommendations": final_state.get("recommendations"),
            "checkout_status": final_state.get("checkout_status"),
            "payment_status": final_state.get("payment_status"),
            "razorpay_order_id": final_state.get("razorpay_order_id"),
            "payment_link_url": final_state.get("payment_link_url"),
            "payment_url": final_state.get("payment_link_url"),
            "recovery_state": final_state.get("recovery_state"),
            "decision_trace": final_state.get("decision_trace")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Dynamic LLM Demand-Driven Starter Prompts ──────────────────────────────
_TRENDING_PROMPTS_CACHE = {
    "timestamp": 0,
    "data": []
}

class TrendingPromptItem(BaseModel):
    emoji: str
    category: str
    prompt: str
    tag: Optional[str] = None

class TrendingPromptsResponse(BaseModel):
    prompts: List[TrendingPromptItem]

TrendingPromptsResponse.model_rebuild()


@router.get("/trending-prompts")
def get_trending_prompts(refresh: bool = False):
    """
    Synthesizes real-time, high-demand starter shopping prompts using the LLM
    grounded in live in-stock catalog inventory.
    """
    global _TRENDING_PROMPTS_CACHE
    import time
    now = time.time()

    # Cache for 15 minutes unless forced refresh
    if not refresh and _TRENDING_PROMPTS_CACHE["data"] and (now - _TRENDING_PROMPTS_CACHE["timestamp"] < 900):
        return {"prompts": _TRENDING_PROMPTS_CACHE["data"]}

    try:
        from backend.db import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, name, price_paise FROM catalog WHERE stock > 0 ORDER BY RANDOM() LIMIT 20"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        CAT_CONFIG = {
            "beauty": ("💄", "Beauty & Fragrances", "Trending"),
            "fragrances": ("💄", "Beauty & Fragrances", "Trending"),
            "skin-care": ("💄", "Beauty & Personal Care", "Trending"),
            "laptops": ("💻", "Laptops & Tech", "High Demand"),
            "smartphones": ("📱", "Mobile & Tech", "High Demand"),
            "mobile-accessories": ("📱", "Mobile Accessories", "Essential"),
            "mens-shirts": ("👕", "Fashion & Apparel", "Style Pick"),
            "mens-watches": ("⌚", "Watches & Accessories", "Style Pick"),
            "groceries": ("🥑", "Daily Essentials", "Popular"),
            "kitchen-accessories": ("🍳", "Home & Living", "Fresh"),
            "sports-accessories": ("⚽", "Fitness & Sports", "Trending"),
        }

        prompts = []
        used_cats = set()
        for r in rows:
            cat = r.get("category", "")
            if cat in CAT_CONFIG and cat not in used_cats and len(prompts) < 4:
                emoji, cat_label, tag = CAT_CONFIG[cat]
                price = round((r.get("price_paise", 3000) / 100) * 1.25)
                prompts.append({
                    "emoji": emoji,
                    "category": cat_label,
                    "prompt": f"I want {r['name']} and companion items within ₹{price:,}",
                    "tag": tag
                })
                used_cats.add(cat)

        if len(prompts) >= 3:
            _TRENDING_PROMPTS_CACHE["timestamp"] = now
            _TRENDING_PROMPTS_CACHE["data"] = prompts
            return {"prompts": prompts}
    except Exception as e:
        print(f"⚠️ Error building dynamic catalog prompts: {e}")
        fallback = [
            {
                "emoji": "💄",
                "category": "Beauty & Fragrances",
                "prompt": "I want Essence Mascara and Dior Sauvage perfume within ₹3,500",
                "tag": "Trending"
            },
            {
                "emoji": "💻",
                "category": "Laptops & Tech",
                "prompt": "Show me a Lenovo Yoga or MacBook Pro laptop under ₹15,000",
                "tag": "High Demand"
            },
            {
                "emoji": "👟",
                "category": "Footwear & Fashion",
                "prompt": "Looking for Nike running shoes and a stylish watch under ₹5,000",
                "tag": "Style Pick"
            },
            {
                "emoji": "📱",
                "category": "Mobile & Accessories",
                "prompt": "Buy an iPhone and fast charger bundle within my budget",
                "tag": "Essential"
            }
        ]
        return {"prompts": _TRENDING_PROMPTS_CACHE["data"] or fallback}


# ─── Mock Razorpay Payment Simulator & Auto-Settlement ──────────────────────

class MockPayPayload(BaseModel):
    cart_id: Optional[str] = None
    order_id: Optional[str] = None
    amount_paise: Optional[int] = None


@router.post("/mock-pay")
@router.get("/mock-pay/{cart_id}")
@router.get("/mock-pay")
def mock_complete_payment(
    cart_id: Optional[str] = None,
    order_id: Optional[str] = None,
    amount_paise: Optional[int] = None,
    payload: Optional[MockPayPayload] = None
):
    """
    Simulates instantaneous Razorpay payment authorization and settlement.
    Creates or updates the payment mandate, generates a mock payment ID (pay_mock_...),
    inserts order into historical_orders, and logs cryptographic audit trails.
    """
    c_id = (payload.cart_id if payload and payload.cart_id else None) or cart_id
    o_id = (payload.order_id if payload and payload.order_id else None) or order_id
    amt = (payload.amount_paise if payload and payload.amount_paise else None) or amount_paise

    conn = get_db()
    cursor = conn.cursor()
    try:
        pm_row = None
        if c_id:
            cursor.execute(
                "SELECT id, cart_id, razorpay_order_id, amount_paise, status FROM payment_mandates WHERE cart_id = ?",
                (c_id,)
            )
            pm_row = cursor.fetchone()

        if not pm_row and o_id:
            cursor.execute(
                "SELECT id, cart_id, razorpay_order_id, amount_paise, status FROM payment_mandates WHERE razorpay_order_id = ?",
                (o_id,)
            )
            pm_row = cursor.fetchone()

        # If payment mandate not found, ensure cart mandate exists first
        if not pm_row:
            cart_row = None
            if c_id:
                cursor.execute("SELECT id, total_paise FROM cart_mandates WHERE id = ?", (c_id,))
                cart_row = cursor.fetchone()

            if not cart_row:
                # Find most recent cart or create a demo cart mandate
                cursor.execute("SELECT id, total_paise FROM cart_mandates ORDER BY created_at DESC LIMIT 1")
                cart_row = cursor.fetchone()
                if cart_row:
                    c_id = cart_row["id"]
                else:
                    # Create one-off demo cart mandate
                    intent_id = f"intent_demo_{uuid.uuid4().hex[:8]}"
                    now_str = datetime.utcnow().isoformat() + "Z"
                    new_exp = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
                    cursor.execute(
                        """INSERT INTO intent_mandates (id, raw_query, goal, spend_cap_paise, created_at)
                           VALUES (?, 'Demo Store Checkout', 'Demo Purchase', ?, ?)""",
                        (intent_id, amt or 149900, now_str)
                    )
                    c_id = f"cart_demo_{uuid.uuid4().hex[:8]}"
                    cursor.execute(
                        """INSERT INTO cart_mandates (id, intent_id, items, total_paise, status, expires_at, created_at)
                           VALUES (?, ?, '[]', ?, 'approved', ?, ?)""",
                        (c_id, intent_id, amt or 149900, new_exp, now_str)
                    )
                    conn.commit()

            # Refresh cart mandate TTL and approved status to guarantee payment execution
            new_exp = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
            cursor.execute(
                "UPDATE cart_mandates SET status = 'approved', expires_at = ?, consumed_at = NULL WHERE id = ?",
                (new_exp, c_id)
            )
            conn.commit()

            # Execute payment mandate choke point
            conn.close()
            try:
                pay_res = execute_payment_mandate(
                    cart_id=c_id,
                    description="CartPilot Test Payment",
                    notes={"cart_id": c_id, "channel": "fake_razorpay_simulator"}
                )
            except Exception as e:
                print(f"ℹ️ Direct payment execution fallback: {e}")
                # Direct insertion fallback if inventory check or race condition occurs
                conn_fb = get_db()
                cur_fb = conn_fb.cursor()
                fallback_pay_id = f"pay_{uuid.uuid4().hex}"
                fallback_order_id = f"order_mock_{uuid.uuid4().hex[:14]}"
                now_str = datetime.utcnow().isoformat() + "Z"
                cur_fb.execute(
                    """INSERT OR REPLACE INTO payment_mandates
                       (id, cart_id, razorpay_order_id, amount_paise, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'created', ?, ?)""",
                    (fallback_pay_id, c_id, fallback_order_id, amt or 149900, now_str, now_str)
                )
                conn_fb.commit()
                conn_fb.close()

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, cart_id, razorpay_order_id, amount_paise, status FROM payment_mandates WHERE cart_id = ?",
                (c_id,)
            )
            pm_row = cursor.fetchone()

        target_cart_id = pm_row["cart_id"] if pm_row else c_id
        target_order_id = (pm_row["razorpay_order_id"] if pm_row else None) or o_id or f"order_mock_{uuid.uuid4().hex[:14]}"
        total_p = (pm_row["amount_paise"] if pm_row else None) or amt or 149900

        mock_pid = f"pay_mock_{uuid.uuid4().hex[:14]}"

        # Close conn before calling update_payment_mandate_status as it opens its own connection
        conn.close()

        update_payment_mandate_status(
            razorpay_order_id=target_order_id,
            cart_id=target_cart_id,
            status="succeeded",
            payment_id=mock_pid
        )

        # Update cart mandate status
        conn2 = get_db()
        cursor2 = conn2.cursor()
        cursor2.execute("UPDATE cart_mandates SET status = 'completed' WHERE id = ?", (target_cart_id,))
        conn2.commit()
        conn2.close()

        return {
            "success": True,
            "status": "succeeded",
            "cart_id": target_cart_id,
            "razorpay_payment_id": mock_pid,
            "razorpay_order_id": target_order_id,
            "amount_paise": total_p,
            "amount_rupees": round(total_p / 100, 2),
            "message": "Payment automatically completed via simulated Razorpay gateway.",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



