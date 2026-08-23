from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from backend.engine.mandates import (
    create_intent_mandate, create_cart_mandate, create_payment_mandate,
    append_audit_log, get_cart_state
)
from backend.engine.guardrail import validate_cart
from backend.integrations.razorpay_client import create_order, create_payment_link
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

class UpdateCartRequest(BaseModel):
    cart_id: str
    items: list[CartItemInput]


def _record_upsell_event(cart_id: str, suggested_sku: str, accepted: bool,
                          cart_total_before: int, cart_total_after: int):
    """Write a row to upsell_events for conversion tracking."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO upsell_events
               (cart_id, suggested_sku, accepted, cart_total_before_paise,
                cart_total_after_paise, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cart_id, suggested_sku, 1 if accepted else 0,
             cart_total_before, cart_total_after,
             datetime.utcnow().isoformat() + "Z")
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/agent-checkout")
def agent_checkout(req: AgentCheckoutRequest):
    """
    Full agent checkout pipeline:
      1. Buyer Agent parses NL request with conversation history & active cart → structured cart
      2. OOS detection → Substitution Agent (if needed) — returned before guardrail
      3. Guardrail Engine validates cart
      4. Growth Agent cross-sell (post-guardrail, pre-Razorpay)
    """
    try:
        # ── Step 1: Buyer Agent with Memory ──────────────────────────────
        history_dicts = [m.model_dump() for m in req.conversation_history] if req.conversation_history else None
        agent_output = generate_cart_proposal(
            natural_language_request=req.query,
            custom_spend_cap_paise=req.spend_cap_paise,
            conversation_history=history_dicts,
            current_cart=req.current_cart
        )


        # ── Step 2: Create Intent Mandate ────────────────────────────────
        intent = create_intent_mandate(
            raw_request=req.query,
            goal=agent_output["goal"],
            spend_cap_paise=agent_output["spend_cap_paise"]
        )


        proposed_items = agent_output["proposed_items"]
        oos_items = agent_output.get("oos_items", [])
        total_paise = sum(item["price_paise"] * item["qty"] for item in proposed_items)

        # ── Step 3: OOS / Substitution check ────────────────────────────
        # If any items are OOS, pause and offer a substitute before guardrail.
        if oos_items:
            oos_item = oos_items[0]  # Handle one at a time
            budget_remaining = agent_output["spend_cap_paise"] - total_paise
            substitute = find_substitute(oos_item, budget_remaining)

            if substitute:
                append_audit_log(
                    "substitution", intent["id"], "Substitution Offered",
                    f"OOS: {oos_item['sku']} — Substitute: {substitute['sku']} ({substitute['name']}) "
                    f"at ₹{substitute['price_paise']/100:.0f}. Reason: {substitute['reason']}"
                )
                return {
                    "status": "substitute_offered",
                    "intent_id": intent["id"],
                    "intent": {"id": intent["id"], "goal": intent["goal"],
                               "spend_cap_paise": intent["spend_cap_paise"]},
                    "oos_item": {
                        "sku": oos_item["sku"],
                        "name": oos_item.get("name", oos_item["sku"])
                    },
                    "substitute": substitute,
                    "remaining_items": proposed_items,          # items excluding the OOS one
                    "total_paise_without_oos": total_paise,
                }
            else:
                # No substitute found — drop OOS item and proceed
                append_audit_log(
                    "intent", intent["id"], "OOS Item Dropped",
                    f"SKU {oos_item['sku']} is OOS and no substitute was found. Proceeding without it."
                )

        # ── Step 4: Guardrail Check ──────────────────────────────────────
        if not proposed_items:
            return {
                "status": "blocked",
                "reason": "No valid items found for your request. Please try a different query.",
                "cart_id": None,
                "intent": {"id": intent["id"], "goal": intent["goal"],
                           "spend_cap_paise": intent["spend_cap_paise"]},
                "proposed_items": [],
                "total_paise": 0
            }

        validation_result = validate_cart(intent["id"], proposed_items, total_paise)

        # ── Step 5: Create Cart Mandate ──────────────────────────────────
        cart = create_cart_mandate(
            intent_id=intent["id"],
            items=proposed_items,
            total_paise=total_paise,
            status=validation_result["status"],
            reason=validation_result["reason"],
            reversible=validation_result["reversible"]
        )

        if cart["status"] == "blocked":
            return {
                "status": "blocked",
                "reason": cart["reason"],
                "cart_id": cart["id"],
                "intent": {"id": intent["id"], "goal": intent["goal"],
                           "spend_cap_paise": intent["spend_cap_paise"]},
                "proposed_items": proposed_items,
                "total_paise": total_paise
            }

        # ── Step 6: Growth Agent cross-sell ─────────────────────────────
        upsell = generate_upsell(proposed_items)
        if upsell:
            # Verify the suggested SKU exists and get its name (double-check)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sku, name, price_paise, category FROM catalog WHERE sku = ?",
                (upsell["sku"],)
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                upsell["name"] = row["name"]
                upsell["price_paise"] = row["price_paise"]
                upsell["category"] = row["category"]
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
            "intent": {"id": intent["id"], "goal": intent["goal"],
                       "spend_cap_paise": intent["spend_cap_paise"]},
            "proposed_items": proposed_items,
            "total_paise": total_paise,
            "guardrail_reason": validation_result["reason"],
            "upsell": upsell
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
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "metadata": meta_obj
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

        # Create Razorpay Order
        order = create_order(
            amount_paise=final_total_paise,
            receipt_id=final_cart_id,
            notes={"cart_id": final_cart_id}
        )

        # Create Payment Link
        payment_link = create_payment_link(
            amount_paise=final_total_paise,
            order_id=order["id"],
            description="CartPilot Order"
        )

        # Create Payment Mandate
        payment_mandate = create_payment_mandate(
            cart_id=final_cart_id,
            razorpay_order_id=order["id"],
            amount_paise=final_total_paise
        )

        return {
            "status": "approved",
            "payment_url": payment_link["short_url"],
            "payment_link": payment_link["short_url"],
            "cart_id": final_cart_id,
            "payment_mandate_id": payment_mandate["id"],
            "razorpay_order_id": order["id"],
            "amount_paise": final_total_paise
        }


    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        # Create Razorpay Order for add-on
        order = create_order(
            amount_paise=item_total_paise,
            receipt_id=addon_cart["id"],
            notes={"parent_cart_id": req.parent_cart_id, "type": "post_purchase_addon"}
        )

        # Create Payment Link
        payment_link = create_payment_link(
            amount_paise=item_total_paise,
            order_id=order["id"],
            description=f"Add-on: {row['name']}"
        )

        # Create Payment Mandate
        payment_mandate = create_payment_mandate(
            cart_id=addon_cart["id"],
            razorpay_order_id=order["id"],
            amount_paise=item_total_paise
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

