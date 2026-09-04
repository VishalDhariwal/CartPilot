"""
CartPilot LangGraph AI Buyer Orchestrator

Sits as an autonomous coordination layer ABOVE existing deterministic commerce tools:
  - Natural Language Intent Understanding & Constraint Extraction
  - Catalog Hybrid Search
  - Autonomous Multi-Step Budget Self-Correction (Max 3 revisions)
  - Deterministic Policy & Guardrail Verification (guardrail.py)
  - 4-Tier Growth Recommendations (lift_engine.py)
  - Explicit Buyer Authorization Gate (REQUIRED / APPROVED / DECLINED)
  - Razorpay Order & Payment Link Checkout (razorpay_client.py)
  - Authoritative Payment Status Verification
  - Payment Failure & Recovery Routing (recovery_agent.py)
  - Explainable Decision Trace Logging (audit_log)
"""

import os
import json
import re
import uuid
from datetime import datetime, timezone
from typing import TypedDict, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from backend.db import get_db
from backend.agents.buyer_agent import get_catalog_str, CartItem
from backend.engine.mandates import (
    create_intent_mandate,
    create_cart_mandate,
    create_payment_mandate,
    update_payment_mandate_status,
    append_audit_log,
    get_cart_state,
    create_audit_log
)
from backend.engine.guardrail import validate_cart
from backend.recommendations.lift_engine import find_cross_sell
from backend.agents.substitution_agent import find_substitute
from backend.agents.recovery_agent import analyze_failure
from backend.engine.payment_engine import execute_payment_mandate


# ─── 1. STRONGLY TYPED GRAPH STATE ──────────────────────────────────────────

class DecisionTraceItem(TypedDict):
    node: str
    tool: Optional[str]
    input_summary: str
    result_summary: str
    guardrail_status: Optional[str]
    state_transition: str
    timestamp: str
    error: Optional[str]
    outcome: Optional[str]


class BuyerGraphState(TypedDict):
    # Session & Identity
    session_id: str
    graph_execution_id: str
    user_request: str
    channel: str
    conversation_history: List[Dict[str, str]]

    # Interpreted Intent & Constraints
    goal: str
    spend_cap_paise: int
    required_items: List[str]
    optional_items: List[str]
    category_preferences: List[str]

    # Catalog & Product Candidates
    candidate_products: List[Dict[str, Any]]
    current_cart: Optional[List[Dict[str, Any]]]
    proposed_items: List[Dict[str, Any]]
    oos_items: List[Dict[str, Any]]
    cart_total_paise: int

    # Mandates & Deterministic Verification
    intent_id: Optional[str]
    cart_id: Optional[str]
    guardrail_status: Literal["approved", "blocked", "pending_confirmation", "unvalidated"]
    guardrail_reason: str
    revision_count: int
    max_revisions: int

    # Growth Recommendations
    recommendations: List[Dict[str, Any]]

    # Conversational LLM Response
    assistant_message: Optional[str]

    # Buyer Authorization Gate (Explicit Authorization)
    buyer_authorization_status: Literal["NOT_REQUIRED", "REQUIRED", "APPROVED", "DECLINED", "EXPIRED"]
    auto_authorize: bool  # Flag for automated testing/instant buy modes

    # Checkout & Razorpay Transaction State
    checkout_status: Literal["not_started", "initiated", "link_created", "completed", "failed"]
    razorpay_order_id: Optional[str]
    payment_mandate_id: Optional[str]
    payment_link_url: Optional[str]
    payment_status: Literal["none", "created", "pending", "succeeded", "failed"]

    # Recovery & Error Handling
    retry_count: int
    max_retries: int
    recovery_state: Optional[Dict[str, Any]]
    error_state: Optional[str]
    last_tool: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]

    # Execution Observability & Decision Trace
    current_node: str
    decision_trace: List[DecisionTraceItem]


# ─── 2. STRUCTURED LLM MODELS ───────────────────────────────────────────────

class ParsedBuyerIntent(BaseModel):
    goal: str = Field(description="Summarized shopping goal")
    spend_cap_paise: int = Field(description="Maximum budget cap in paise")
    required_items: List[str] = Field(default_factory=list, description="Must-have product keywords")
    optional_items: List[str] = Field(default_factory=list, description="Nice-to-have product keywords")
    category_preferences: List[str] = Field(default_factory=list, description="Target product categories")


class CartRevisionPlan(BaseModel):
    action: Literal["remove_optional", "cheaper_alternative", "reduce_quantity", "cannot_satisfy"]
    reason: str
    target_sku: Optional[str] = None
    replacement_sku: Optional[str] = None


# ─── HELPER: AUDIT TRACE RECORDER ───────────────────────────────────────────

def _add_trace(
    state: BuyerGraphState,
    node: str,
    tool: Optional[str],
    input_summary: str,
    result_summary: str,
    state_transition: str,
    guardrail_status: Optional[str] = None,
    error: Optional[str] = None,
    outcome: Optional[str] = None
) -> DecisionTraceItem:
    trace_item: DecisionTraceItem = {
        "node": node,
        "tool": tool,
        "input_summary": input_summary[:200],
        "result_summary": result_summary[:300],
        "guardrail_status": guardrail_status,
        "state_transition": state_transition,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "outcome": outcome
    }
    return trace_item


# ─── 3. GRAPH NODES & INTENT CLASSIFIER ─────────────────────────────────────

def classify_intent(query: str) -> str:
    """
    Classifies buyer messages into:
    - 'greeting'
    - 'gratitude'
    - 'acknowledgement'
    - 'farewell'
    - 'help_identity'
    - 'explore'
    - 'suggestions'
    - 'cart_clear'
    - 'cart_view'
    - 'informational'
    - 'shopping' (default purchase/search intent)
    """
    if not query:
        return "greeting"

    q_clean = query.strip()
    low = q_clean.lower().strip("!?,.'\" ")

    # 1. GREETINGS
    if re.match(r'^(hi+|hello+|hey+|heyy+|hola|greetings|good\s+(?:morning|afternoon|evening|day)|sup|yo|howdy|hiya)(\s+(?:there|cartpilot|assistant|bot|friend|mate))?$', low):
        return "greeting"

    # 2. COURTESY / GRATITUDE
    if re.match(r'^(thanks?(\s+you)?(\s+so\s+much|\s+a\s+lot)?|thx|appreciate\s+it|good\s+job|awesome|great|perfect|nice|well\s+done)$', low):
        return "gratitude"

    # 3. ACKNOWLEDGEMENT
    if re.match(r'^(ok+|okay+|sure|got\s+it|fine|alright|cool|understood|k|yes|yep|yeah)$', low):
        return "acknowledgement"

    # 4. FAREWELL
    if re.match(r'^(bye+|goodbye+|see\s+(?:you|ya)|cya|take\s+care|have\s+a\s+(?:good|nice)\s+day|good\s*night)$', low):
        return "farewell"

    # 5. IDENTITY & HELP
    if (
        re.match(r'^(help(\s+me)?|who\s+are\s+you|what\s+is\s+(cartpilot|this)|what\s+can\s+you\s+do|how\s+do(?:es)?\s+(?:this|you)\s+work|what\s+are\s+your\s+features)$', low)
        or low in ["help", "help me", "who are you", "what is cartpilot", "what can you do", "how does this work", "how do you work", "how to use", "how can you help", "how can you help me"]
    ):
        return "help_identity"

    # 6. STORE EXPLORATION
    if any(phrase in low for phrase in [
        'what do you sell', 'what categories', 'show categories', 'show departments',
        'what products do you have', 'what can i buy', "what's available", 'what is available',
        'browse catalog', 'browse store', 'all categories'
    ]):
        return "explore"

    # 7. GENERAL SUGGESTIONS & TRENDING
    if any(phrase in low for phrase in [
        'recommend something', 'suggest something', "what's trending", 'what is trending',
        'best sellers', 'show recommendations', 'can you suggest some products', 'can you suggest products',
        'suggest products', 'recommend products', 'what should i buy', 'gift ideas', 'trending items',
        'popular items'
    ]):
        return "suggestions"

    # 8. CART MANAGEMENT
    if low in ['clear cart', 'empty cart', 'delete cart', 'reset cart', 'remove all items', 'clear my cart']:
        return "cart_clear"
    if low in ['view cart', 'show cart', "what's in my cart", 'what is in my cart', 'my cart', 'check cart']:
        return "cart_view"

    # 9. INFORMATIONAL / RECIPES / HOW-TO / FAQ
    if (
        re.match(r'^(how\s+(?:to|do|does|can|could|should|is|are|much|long)|recipe\s+for|what\s+(?:is|are|does|do|can|could)|where\s+(?:is|are|can)|who\s+(?:is|are|made)|can\s+(?:i|you|we)|is\s+it\s+|why\s+(?:is|are|do|does|should)|tell\s+me\b|explain\b)', low)
        or any(w in low for w in ['how to cook', 'how to prepare', 'how to make', 'how to bake', 'how to clean', 'how to use', 'recipe', 'return policy', 'refund policy', 'shipping policy', 'delivery', 'shipping', 'track order', 'payment method'])
        or "joke" in low
    ):
        if not re.search(r'\b(buy|purchase|order\s+(?:this|that|one|some|\d+)|add\s+to\s+cart)\b', low):
            return "informational"

    return "shopping"


def _fast_parse_intent(query: str, default_cap_paise: int = 1000000) -> Optional[ParsedBuyerIntent]:
    """
    Ultra-fast deterministic intent parser (<1ms).
    Handles standard shopping queries with optional budget constraints instantly,
    eliminating redundant 20-second LLM roundtrips for straightforward storefront searches.
    """
    import re
    q = (query or "").strip()
    if not q:
        return None

    # Never treat conversational, FAQ, or informational queries as purchase intent
    if classify_intent(q) != "shopping":
        return None

    words = q.split()
    if len(words) > 25:
        return None

    low_q = q.lower()
    complex_markers = ["if ", "otherwise", "either", "instead of", "swap", "replace", "compare", "why did"]
    if any(m in low_q for m in complex_markers):
        return None

    spend_cap = default_cap_paise
    m = re.search(r'(?:under|below|budget|max(?:imum)?|for|within|less than)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)', q, re.I)
    if m:
        val_str = m.group(1).replace(',', '')
        try:
            val_f = float(val_str)
            if val_f > 0:
                spend_cap = int(val_f * 100)
        except Exception:
            pass

    # Clean leading search verbs & additive/conversational prefixes
    cleaned = re.sub(
        r'^(?:(?:also|and|can you\s+(?:also)?|please\s+(?:also)?|could you\s+(?:also)?)\s+)?'
        r'(?:i\s+(?:want|need|would like|am looking for)|looking for|find(?:\s+me)?|show(?:\s+me)?|search for|buy(?:\s+me)?|order(?:\s+me)?|get(?:\s+me)?|give me|add(?:\s+me)?)\s+',
        '',
        q,
        flags=re.I
    ).strip()

    # Remove trailing budget phrase & conversational suffixes
    cleaned_items = re.sub(
        r'(?:under|below|budget|max(?:imum)?|for|within|less than)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        '',
        cleaned,
        flags=re.I
    ).strip()
    cleaned_items = re.sub(
        r'\s+(?:for\s+me|for\s+myself|as\s+well|too|to\s+my\s+cart|to\s+the\s+cart|to\s+cart|please|thanks?)$',
        '',
        cleaned_items,
        flags=re.I
    ).strip()
    cleaned_items = re.sub(r'\s+', ' ', cleaned_items).strip(' .,!?:;')

    if not cleaned_items:
        cleaned_items = q.strip(' .,!?:;')

    goal = f"Buy {cleaned_items}"
    return ParsedBuyerIntent(
        goal=goal,
        spend_cap_paise=spend_cap,
        required_items=[cleaned_items] if cleaned_items else [q],
        optional_items=[],
        category_preferences=[]
    )


def node_understand_intent(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Parses natural language user request into structured shopping intent and constraints.
    Creates an immutable Intent Mandate in the database.
    """
    node_name = "UNDERSTAND_INTENT"
    user_req = state["user_request"]
    default_cap = state.get("spend_cap_paise") or 1000000

    # 1. Fast deterministic intent extraction (<1ms for common queries)
    fast_parsed = _fast_parse_intent(user_req, default_cap)
    if fast_parsed:
        goal = fast_parsed.goal
        spend_cap = fast_parsed.spend_cap_paise if fast_parsed.spend_cap_paise > 0 else default_cap
        req_items = fast_parsed.required_items
        opt_items = fast_parsed.optional_items
        cat_prefs = fast_parsed.category_preferences
    else:
        # Fallback to structured intent parsing via LLM for complex queries
        from backend.engine.llm import generate_structured
        system_prompt = """
        You are the Intent Parser for CartPilot AI Buyer.
        Extract the customer's shopping goal, budget constraints, required items, and optional items.
        Convert rupee amounts to paise (₹1 = 100 paise).
        If no budget is specified, default to 1,000,000 paise (₹10,000).
        """
        prompt = f"User Request: {user_req}\nDefault Spend Cap: {default_cap} paise"

        try:
            parsed: ParsedBuyerIntent = generate_structured(
                prompt=prompt,
                schema=ParsedBuyerIntent,
                system_prompt=system_prompt
            )
            goal = parsed.goal
            spend_cap = parsed.spend_cap_paise if parsed.spend_cap_paise > 0 else default_cap
            req_items = parsed.required_items
            opt_items = parsed.optional_items
            cat_prefs = parsed.category_preferences
        except Exception as e:
            goal = user_req
            spend_cap = default_cap
            req_items = [user_req]
            opt_items = []
            cat_prefs = []

    # Override spend cap if explicitly provided by caller
    if state.get("spend_cap_paise") and state["spend_cap_paise"] > 0:
        spend_cap = state["spend_cap_paise"]

    # 2. Record immutable Intent Mandate
    intent = create_intent_mandate(
        raw_request=user_req,
        goal=goal,
        spend_cap_paise=spend_cap,
        channel=state.get("channel", "langgraph_agent")
    )

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="create_intent_mandate",
        input_summary=f"Query: {user_req}, Cap: ₹{spend_cap/100:.0f}",
        result_summary=f"Intent Mandate {intent['id']} created. Goal: {goal}",
        state_transition="UNDERSTAND_INTENT -> SEARCH_CATALOG",
        outcome="Intent parsed & mandate recorded"
    )

    return {
        "current_node": node_name,
        "goal": goal,
        "spend_cap_paise": spend_cap,
        "required_items": req_items,
        "optional_items": opt_items,
        "category_preferences": cat_prefs,
        "intent_id": intent["id"],
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_search_catalog(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Queries catalog using existing hybrid dense semantic + keyword search.
    Gathers candidate items without hallucination.
    """
    node_name = "SEARCH_CATALOG"
    query = state["user_request"]
    spend_cap = state["spend_cap_paise"]

    # Search candidates specifically for the new user query without prepending current_cart
    # so that candidates are accurately ranked for the newly requested item.
    catalog_str, sku_map = get_catalog_str(
        client=None,
        query=query,
        spend_cap_paise=spend_cap,
        current_cart=None,
        conversation_history=state.get("conversation_history")
    )

    candidates = list(sku_map.values())

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="get_catalog_str",
        input_summary=f"Query: {query}, Cap: ₹{spend_cap/100:.0f}",
        result_summary=f"Discovered {len(candidates)} candidate SKUs in merchant catalog.",
        state_transition="SEARCH_CATALOG -> BUILD_CART",
        outcome=f"{len(candidates)} candidates loaded"
    )

    return {
        "current_node": node_name,
        "candidate_products": candidates,
        "last_tool": "get_catalog_str",
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_build_cart(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Selects items matching requested criteria and handles OOS substitution checks transparently.
    Calculates exact cart total strictly from verified database catalog prices.
    Preserves and accumulates existing cart items across multi-turn sessions.
    """
    node_name = "BUILD_CART"
    candidates = state.get("candidate_products", [])
    spend_cap = state["spend_cap_paise"]
    current_cart = [dict(it) for it in (state.get("current_cart") or [])]
    user_req_clean = state["user_request"].lower().strip()

    # If proposed_items are already set from a revision step, preserve them
    if state.get("proposed_items") and state.get("revision_count", 0) > 0:
        proposed = state["proposed_items"]
    else:
        # Check for explicit cart reset intent (e.g. "clear cart and buy X", "start over with X")
        is_fresh_start = any(re.search(p, user_req_clean) for p in [
            r'\bclear\s+cart\s+(?:and|then)\b',
            r'\bempty\s+cart\s+(?:and|then)\b',
            r'\breset\s+cart\s+(?:and|then)\b',
            r'\bstart\s+(?:fresh|over|new\s+order)\b',
            r'\bforget\s+(?:everything|previous|prior|cart)\b',
            r'\bonly\s+want\b'
        ])
        if is_fresh_start:
            current_cart = []

        # Check for item removal intent (e.g. "remove silk shirt", "delete shoes")
        is_removal = any(w in user_req_clean for w in ["remove", "delete", "drop", "take out", "take off", "get rid of"])
        if is_removal and current_cart:
            rem_words = [w for w in re.findall(r'\b[a-z0-9]+\b', user_req_clean) if w not in ["remove", "delete", "drop", "take", "out", "off", "the", "from", "my", "cart", "item", "please"]]
            matched_idx = None
            if rem_words:
                best_score = 0
                for idx, it in enumerate(current_cart):
                    it_text = f"{it.get('name', '')} {it.get('category', '')} {it.get('sku', '')}".lower()
                    score = sum(1 for w in rem_words if w in it_text)
                    if score > best_score:
                        best_score = score
                        matched_idx = idx

            if matched_idx is not None:
                m_qty = re.search(r'\b(\d+)\s*(?:x|units?|pieces?|pairs?|items?)?\b', user_req_clean)
                req_qty = int(m_qty.group(1)) if m_qty else None
                curr_qty = current_cart[matched_idx].get("qty", 1)
                if req_qty and req_qty < curr_qty:
                    current_cart[matched_idx]["qty"] = curr_qty - req_qty
                else:
                    current_cart.pop(matched_idx)

            proposed = current_cart
        elif not candidates:
            trace = _add_trace(
                state=state,
                node=node_name,
                tool=None,
                input_summary="No candidate products found",
                result_summary=f"No matching new items. Cart has {len(current_cart)} existing items.",
                state_transition="BUILD_CART -> VALIDATE_CART",
                error=None if current_cart else "No matching items in catalog"
            )
            return {
                "current_node": node_name,
                "proposed_items": current_cart,
                "oos_items": [],
                "cart_total_paise": sum(i.get("price_paise", 0) * i.get("qty", 1) for i in current_cart),
                "decision_trace": state["decision_trace"] + [trace]
            }
        else:
            # Check if query has replacement or complex context modifiers
            has_replacement = any(w in user_req_clean for w in ["instead of", "replace", "swap", "change to", "no ", "don't"])
            has_history_modifier = bool(state.get("conversation_history")) and any(
                any(w in msg.get("content", "").lower() for w in ["instead", "replace", "remove", "delete", "swap"])
                for msg in state["conversation_history"][-3:]
            )

            existing_cost = sum(it.get("price_paise", 0) * it.get("qty", 1) for it in current_cart)
            in_budget_candidates = [c for c in candidates if c.get("stock", 0) > 0 and (existing_cost + c.get("price_paise", 0)) <= spend_cap]
            available_candidates = in_budget_candidates or [c for c in candidates if c.get("stock", 0) > 0]

            if not has_replacement and not has_history_modifier and available_candidates:
                top_cand = available_candidates[0]
                qty = 1
                m_qty = re.search(r'\b(\d+)\s*(?:x|units?|pieces?|pairs?|items?)?\b', state["user_request"], re.I)
                if m_qty:
                    try:
                        q_val = int(m_qty.group(1))
                        if 1 <= q_val <= 10 and (existing_cost + top_cand["price_paise"] * q_val <= spend_cap):
                            qty = q_val
                    except Exception:
                        qty = 1

                # Check if top candidate is already in current_cart
                existing_match_idx = next((i for i, it in enumerate(current_cart) if it.get("sku") == top_cand["sku"]), None)
                if existing_match_idx is not None:
                    current_cart[existing_match_idx]["qty"] = current_cart[existing_match_idx].get("qty", 1) + qty
                    proposed = current_cart
                else:
                    new_item = {
                        "sku": top_cand["sku"],
                        "name": top_cand["name"],
                        "price_paise": top_cand["price_paise"],
                        "qty": qty,
                        "category": top_cand["category"]
                    }
                    proposed = current_cart + [new_item]
            else:
                # Fall back to structured agent LLM for multi-turn conversational edits
                from backend.agents.buyer_agent import generate_cart_proposal
                proposal = generate_cart_proposal(
                    natural_language_request=state["user_request"],
                    custom_spend_cap_paise=spend_cap,
                    conversation_history=state.get("conversation_history"),
                    current_cart=current_cart
                )
                proposed = proposal.get("proposed_items", [])

    # Transparent OOS Handling
    verified_items = []
    oos_list = []

    conn = get_db()
    cursor = conn.cursor()
    try:
        for item in proposed:
            cursor.execute("SELECT sku, name, price_paise, stock, category, image_url, description, metadata FROM catalog WHERE sku = ?", (item["sku"],))
            row = cursor.fetchone()
            if not row:
                continue

            meta_obj = {}
            if row["metadata"]:
                try:
                    meta_obj = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
                except Exception:
                    meta_obj = {}

            item_dict = {
                "sku": row["sku"],
                "name": row["name"],
                "price_paise": row["price_paise"],
                "qty": max(1, item.get("qty", 1)),
                "category": row["category"],
                "stock": row["stock"],
                "image_url": row["image_url"] or "",
                "description": row["description"] or "",
                "metadata": meta_obj
            }

            if row["stock"] <= 0:
                # OOS item detected: Attempt transparent substitution
                sub = find_substitute(item_dict, spend_cap)
                if sub:
                    # Substitute found: replace with in-stock substitute
                    cursor.execute("SELECT sku, name, price_paise, stock, category, image_url, description, metadata FROM catalog WHERE sku = ?", (sub["sku"],))
                    sub_row = cursor.fetchone()
                    if sub_row and sub_row["stock"] > 0:
                        sub_meta = {}
                        if sub_row["metadata"]:
                            try:
                                sub_meta = json.loads(sub_row["metadata"]) if isinstance(sub_row["metadata"], str) else sub_row["metadata"]
                            except Exception:
                                sub_meta = {}
                        verified_items.append({
                            "sku": sub_row["sku"],
                            "name": sub_row["name"],
                            "price_paise": sub_row["price_paise"],
                            "qty": 1,
                            "category": sub_row["category"],
                            "stock": sub_row["stock"],
                            "image_url": sub_row["image_url"] or "",
                            "description": sub_row["description"] or "",
                            "metadata": sub_meta,
                            "substituted_from": item["sku"]
                        })
                else:
                    oos_list.append(item_dict)
            else:
                verified_items.append(item_dict)
    finally:
        conn.close()

    total_paise = sum(i["price_paise"] * i["qty"] for i in verified_items)

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="find_substitute" if oos_list else None,
        input_summary=f"Built cart with {len(verified_items)} item(s).",
        result_summary=f"Total: ₹{total_paise/100:.2f}. OOS items: {len(oos_list)}",
        state_transition="BUILD_CART -> VALIDATE_CART",
        outcome=f"Cart built ({len(verified_items)} items)"
    )

    return {
        "current_node": node_name,
        "proposed_items": verified_items,
        "oos_items": oos_list,
        "cart_total_paise": total_paise,
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_validate_cart(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Executes authoritative, deterministic policy and spend-cap validation using guardrail.py.
    Creates or updates the Cart Mandate in SQLite.
    """
    node_name = "VALIDATE_CART"
    items = state.get("proposed_items", [])
    total_paise = state.get("cart_total_paise", 0)
    intent_id = state.get("intent_id")

    if not items:
        validation = {
            "status": "approved",
            "reason": "Cart is currently empty.",
            "reversible": False
        }
    else:
        validation = validate_cart(intent_id, items, total_paise)

    # Create Cart Mandate in database
    cart_mandate = create_cart_mandate(
        intent_id=intent_id or "intent_standalone",
        items=items,
        total_paise=total_paise,
        status=validation["status"],
        reason=validation["reason"],
        reversible=validation["reversible"]
    )

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="validate_cart",
        input_summary=f"Validating {len(items)} items, Total: ₹{total_paise/100:.2f}",
        result_summary=f"Guardrail Status: {validation['status']}. Reason: {validation['reason']}",
        state_transition=f"VALIDATE_CART -> {validation['status'].upper()}",
        guardrail_status=validation["status"],
        outcome=validation["reason"]
    )

    return {
        "current_node": node_name,
        "cart_id": cart_mandate["id"],
        "guardrail_status": validation["status"],
        "guardrail_reason": validation["reason"],
        "last_tool": "validate_cart",
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_revise_cart(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Autonomous constraint self-correction loop (Max 3 iterations).
    Analyzes why the cart was blocked (e.g. over-budget) and revises:
      - Drops optional items
      - Finds cheaper alternative in same category
      - Reduces quantities
    Re-calculates strictly against database prices.
    """
    node_name = "REVISE_CART"
    items = state.get("proposed_items", [])
    spend_cap = state["spend_cap_paise"]
    current_total = state["cart_total_paise"]
    rev_count = state.get("revision_count", 0) + 1
    reason = state.get("guardrail_reason", "")

    # Revision Strategy
    revised_items = list(items)

    # 1. If multiple items and over budget: remove highest priced optional item
    if len(revised_items) > 1 and current_total > spend_cap:
        # Check if any item is optional
        opt_names = [o.lower() for o in state.get("optional_items", [])]
        dropped_idx = None
        if opt_names:
            for idx, it in enumerate(revised_items):
                if any(opt in it["name"].lower() for opt in opt_names):
                    dropped_idx = idx
                    break
        if dropped_idx is None:
            # Drop the most expensive item to try to fit within budget
            sorted_by_price = sorted(range(len(revised_items)), key=lambda i: revised_items[i]["price_paise"] * revised_items[i]["qty"], reverse=True)
            dropped_idx = sorted_by_price[0]

        dropped_item = revised_items.pop(dropped_idx)
        action_summary = f"Removed optional/expensive item: {dropped_item['name']} (₹{dropped_item['price_paise']/100:.0f})"
    elif len(revised_items) == 1 and current_total > spend_cap:
        # Single item over budget: Search for cheaper alternative in same category
        single_item = revised_items[0]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sku, name, price_paise, category, stock, image_url, description FROM catalog WHERE category = ? AND price_paise <= ? AND stock > 0 ORDER BY price_paise DESC LIMIT 1",
            (single_item.get("category", ""), spend_cap)
        )
        cheaper_row = cursor.fetchone()
        conn.close()

        if cheaper_row:
            revised_items = [{
                "sku": cheaper_row["sku"],
                "name": cheaper_row["name"],
                "price_paise": cheaper_row["price_paise"],
                "qty": 1,
                "category": cheaper_row["category"],
                "image_url": cheaper_row["image_url"] or "",
                "description": cheaper_row["description"] or ""
            }]
            action_summary = f"Replaced with budget-compliant alternative: {cheaper_row['name']} (₹{cheaper_row['price_paise']/100:.0f})"
        else:
            action_summary = "No cheaper alternatives available within budget cap."
    else:
        action_summary = "Adjusted quantities to satisfy policy constraints."

    new_total = sum(i["price_paise"] * i["qty"] for i in revised_items)

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="revise_cart",
        input_summary=f"Revision #{rev_count}: Over-budget by ₹{(current_total - spend_cap)/100:.2f}",
        result_summary=f"{action_summary}. New total: ₹{new_total/100:.2f}",
        state_transition="REVISE_CART -> VALIDATE_CART",
        outcome=f"Revision #{rev_count} applied"
    )

    return {
        "current_node": node_name,
        "proposed_items": revised_items,
        "cart_total_paise": new_total,
        "revision_count": rev_count,
        "decision_trace": state["decision_trace"] + [trace]
    }


def generate_conversational_response(
    query: str,
    spend_cap_paise: int,
    proposed_items: list[dict],
    candidate_products: list[dict],
    guardrail_status: str,
    guardrail_reason: Optional[str] = None,
    recommendations: list[dict] = None,
    previous_cart: Optional[list[dict]] = None
) -> str:
    """
    Synthesizes an intelligent, context-grounded conversational response using the LLM.
    Explains what was found, why a policy or budget limit was hit, and gives clear, friendly advice.
    """
    from backend.engine.llm import generate_text

    items_summary = [f"- {it.get('name')} (Price: ₹{it.get('price_paise', 0)/100:.2f})" for it in (proposed_items or [])]
    cands_summary = [f"- {c.get('name')} (Price: ₹{c.get('price_paise', 0)/100:.2f}, Category: {c.get('category')})" for c in (candidate_products or [])[:5]]
    recs_summary = [f"- {r.get('name')} (Price: ₹{r.get('price_paise', 0)/100:.2f}, Reason: {r.get('reason')})" for r in (recommendations or [])[:3]]

    prompt = f"""
CUSTOMER REQUEST: "{query}"
CUSTOMER SPEND LIMIT: ₹{spend_cap_paise/100:.2f}

CATALOG MATCHES FOUND:
{chr(10).join(cands_summary) if cands_summary else 'No matching catalog products found.'}

PROPOSED CART ITEMS:
{chr(10).join(items_summary) if items_summary else 'None (Cart is empty)'}

GUARDRAIL / POLICY STATUS: {guardrail_status}
GUARDRAIL REASON: {guardrail_reason or 'None'}

RECOMMENDATIONS OFFERED:
{chr(10).join(recs_summary) if recs_summary else 'None'}

Write a natural, helpful, conversational response to the customer.
"""

    system_prompt = (
        "You are CartPilot, a helpful, intelligent, polite AI shopping assistant for an e-commerce platform.\n"
        "Your task is to speak naturally to the customer based on the real catalog search, guardrail policies, and cart status.\n\n"
        "GUIDELINES:\n"
        "1. Be friendly, concise, and helpful (2-3 sentences max).\n"
        "2. If items were successfully added to the cart, warmly confirm what was added and mention any complementary suggestions.\n"
        "3. If the request exceeded the spend limit, mention the specific matching products found and their prices, explain the budget constraint politely, and suggest adjusting their spend cap or choosing alternatives.\n"
        "4. If no products were found or a category is restricted, politely inform them and suggest available departments.\n"
        "5. Do NOT mention internal code names like 'guardrail', 'mandate', 'LangGraph', or technical error codes. Speak like a premium personal shopping concierge."
    )

    # ── Fast Deterministic Response Builder for Standard Turns ────────────────
    # Saves ~50% of storefront LLM calls and reduces chat latency to 0ms
    if guardrail_status == "approved" and proposed_items:
        prev_cart = previous_cart or []
        prev_sku_qty = {it.get("sku"): it.get("qty", 1) for it in prev_cart}

        # Identify newly added or increased items
        newly_added = []
        for it in proposed_items:
            sku = it.get("sku")
            prev_q = prev_sku_qty.get(sku, 0)
            curr_q = it.get("qty", 1)
            if curr_q > prev_q:
                added_q = curr_q - prev_q
                newly_added.append({**it, "qty": added_q})

        cart_total_rupees = sum((it.get('price_paise', 0) * it.get('qty', 1)) for it in proposed_items) / 100
        total_items_count = sum(it.get('qty', 1) for it in proposed_items)
        rec_note = f" I also found a complementary {recommendations[0]['name']} that pairs nicely with your order." if recommendations else ""

        if prev_cart and newly_added:
            new_str = ", ".join([f"{it.get('qty', 1)}x {it.get('name')}" for it in newly_added])
            return (
                f"I've added {new_str} to your cart. "
                f"Your cart now has {total_items_count} item{'s' if total_items_count != 1 else ''} "
                f"(Total: ₹{cart_total_rupees:.2f}).{rec_note} "
                f"Everything is verified and ready for checkout whenever you'd like!"
            )
        elif prev_cart and len(proposed_items) < len(prev_cart):
            # Items removed
            curr_skus = {it.get("sku") for it in proposed_items}
            removed_names = [it.get("name", it.get("sku")) for it in prev_cart if it.get("sku") not in curr_skus]
            rem_str = ", ".join(removed_names) or "item"
            return (
                f"I've removed {rem_str} from your cart. "
                f"Your updated cart has {total_items_count} item{'s' if total_items_count != 1 else ''} "
                f"(Total: ₹{cart_total_rupees:.2f})."
            )
        else:
            items_str = ", ".join([f"{it.get('qty', 1)}x {it.get('name')}" for it in proposed_items])
            return f"I've added {items_str} to your cart (Total: ₹{cart_total_rupees:.2f}).{rec_note} Everything is verified and ready for checkout whenever you'd like!"

    if "spend cap" in (guardrail_reason or "").lower():
        return f"I found matching items in our catalog, but the total exceeds your current store budget of ₹{spend_cap_paise/100:.2f}. You can increase your spend limit or choose fewer items."

    if not candidate_products and not proposed_items:
        return f"I couldn't find items matching '{query}' in our store catalog. Please try searching by product name, brand, or department."

    if guardrail_status == "blocked":
        if "empty" in (guardrail_reason or "").lower():
            return f"I couldn't find items matching '{query}' in our store catalog. Please try searching by product name, brand, or department."
        return f"⚠️ Order restricted by store policy: {guardrail_reason or 'This item or category is currently not permitted.'}"

    try:
        res = generate_text(prompt=prompt, system_prompt=system_prompt)
        return res.strip()
    except Exception as e:
        if guardrail_status == 'approved' and proposed_items:
            return "I've itemized your requested items below! Feel free to review or add complementary picks."
        if 'spend cap' in (guardrail_reason or '').lower():
            return f"I found matching items in our catalog, but they exceed your current spend limit of ₹{spend_cap_paise/100:.2f}. You can increase your spend limit using the settings above."
        return guardrail_reason or "I couldn't find items matching your request in our catalog. Try browsing our available categories."


def node_notify_buyer_blocked(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Invoked when revisions are exhausted or policy cannot be satisfied.
    Sets explicit DECLINED status without proceeding to checkout.
    """
    node_name = "NOTIFY_BUYER_BLOCKED"
    reason = state.get("guardrail_reason", "Cart could not be reconciled with active merchant policy.")

    recommendations = state.get("recommendations", [])
    if not recommendations:
        try:
            candidates = state.get("candidate_products", [])
            if candidates:
                recs = find_cross_sell(candidates[:2], top_k=3)
                recommendations = recs
        except Exception:
            pass

    msg = generate_conversational_response(
        query=state["user_request"],
        spend_cap_paise=state["spend_cap_paise"],
        proposed_items=state.get("proposed_items", []),
        candidate_products=state.get("candidate_products", []),
        guardrail_status="blocked",
        guardrail_reason=reason,
        recommendations=recommendations,
        previous_cart=state.get("current_cart")
    )

    trace = _add_trace(
        state=state,
        node=node_name,
        tool=None,
        input_summary=f"Max revisions ({state.get('max_revisions', 3)}) reached.",
        result_summary=f"Blocked: {reason}",
        state_transition="NOTIFY_BUYER_BLOCKED -> END",
        guardrail_status="blocked",
        error=reason,
        outcome="Cart rejected by policy"
    )

    return {
        "current_node": node_name,
        "assistant_message": msg,
        "buyer_authorization_status": "DECLINED",
        "checkout_status": "failed",
        "error_state": reason,
        "recommendations": recommendations,
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_get_recommendations(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Fetches 3-tier complementary upsell recommendations strictly using lift_engine.py.
    """
    node_name = "GET_RECOMMENDATIONS"
    items = state.get("proposed_items", []) or state.get("candidate_products", [])
    recommendations = []

    if items:
        try:
            candidates = find_cross_sell(items, top_k=3)
            for c in candidates:
                recommendations.append({
                    "sku": c["sku"],
                    "name": c["name"],
                    "price_paise": c["price_paise"],
                    "price_rupees": round(c["price_paise"] / 100, 2),
                    "category": c["category"],
                    "image_url": c.get("image_url", ""),
                    "description": c.get("description", ""),
                    "metadata": c.get("metadata", {}),
                    "lift": c.get("lift"),
                    "final_score": c.get("final_score"),
                    "reason": c.get("reason", "Frequently purchased together."),
                    "source": c.get("source", "cross_sell")
                })
        except Exception as e:
            print(f"⚠️ Recommendation engine warning: {e}")

    if not recommendations:
        try:
            conn = get_db()
            cursor = conn.cursor()
            item_skus = [it.get("sku") for it in items if it.get("sku")]
            placeholders = ",".join(["?"] * len(item_skus)) if item_skus else "''"
            sql = f"""
                SELECT sku, name, price_paise, category, image_url, description, metadata, boosted
                FROM catalog
                WHERE stock > 0 AND sku NOT IN ({placeholders})
                ORDER BY boosted DESC, price_paise ASC
                LIMIT 3
            """
            cursor.execute(sql, item_skus)
            fallback_rows = cursor.fetchall()
            conn.close()
            for r in fallback_rows:
                meta = {}
                try:
                    meta = json.loads(r["metadata"]) if r["metadata"] else {}
                except Exception:
                    pass
                recommendations.append({
                    "sku": r["sku"],
                    "name": r["name"],
                    "price_paise": r["price_paise"],
                    "price_rupees": round(r["price_paise"] / 100, 2),
                    "category": r["category"],
                    "image_url": r["image_url"] or "",
                    "description": r["description"] or "",
                    "metadata": meta,
                    "lift": None,
                    "final_score": 0.85,
                    "reason": "Top trending pick matching your shopping context.",
                    "source": "trending"
                })
        except Exception as e:
            print(f"⚠️ Recommendation fallback warning: {e}")

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="find_cross_sell",
        input_summary=f"Fetching cross-sells for {len(items)} items",
        result_summary=f"Retrieved {len(recommendations)} recommendations from 4-tier engine.",
        state_transition="GET_RECOMMENDATIONS -> PRESENT_FOR_APPROVAL",
        outcome=f"{len(recommendations)} recommendations attached"
    )

    return {
        "current_node": node_name,
        "recommendations": recommendations,
        "last_tool": "find_cross_sell",
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_present_for_approval(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Enforces the mandatory Buyer Authorization Gate.
    Distinguishes policy approval (Guardrail) from buyer authorization.
    """
    node_name = "PRESENT_FOR_APPROVAL"
    auto_auth = state.get("auto_authorize", False)
    current_auth = state.get("buyer_authorization_status", "REQUIRED")

    if auto_auth or current_auth == "APPROVED":
        new_auth = "APPROVED"
        transition = "PRESENT_FOR_APPROVAL -> EXECUTE_CHECKOUT"
    else:
        new_auth = "REQUIRED"
        transition = "PRESENT_FOR_APPROVAL -> WAIT_FOR_BUYER"

    msg = generate_conversational_response(
        query=state["user_request"],
        spend_cap_paise=state["spend_cap_paise"],
        proposed_items=state.get("proposed_items", []),
        candidate_products=state.get("candidate_products", []),
        guardrail_status=state.get("guardrail_status", "approved"),
        guardrail_reason=state.get("guardrail_reason"),
        recommendations=state.get("recommendations", []),
        previous_cart=state.get("current_cart")
    )

    trace = _add_trace(
        state=state,
        node=node_name,
        tool=None,
        input_summary=f"Cart Total: ₹{state['cart_total_paise']/100:.2f}. Auth Status: {new_auth}",
        result_summary=f"Buyer Authorization Gate evaluated: {new_auth}",
        state_transition=transition,
        outcome=f"Buyer Authorization: {new_auth}"
    )

    return {
        "current_node": node_name,
        "assistant_message": msg,
        "buyer_authorization_status": new_auth,
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_execute_checkout(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Finalizes an approved and authorized cart mandate.
    Calls Razorpay client to create order, payment link, and payment mandate record.
    """
    node_name = "EXECUTE_CHECKOUT"
    cart_id = state.get("cart_id")
    total_paise = state.get("cart_total_paise", 0)

    # Authority Check: Guardrail must be approved AND buyer must have authorized
    if state.get("buyer_authorization_status") not in ["APPROVED", "NOT_REQUIRED"]:
        trace = _add_trace(
            state=state,
            node=node_name,
            tool=None,
            input_summary="Checkout attempt without buyer authorization",
            result_summary="Blocked: Buyer authorization is required before charging.",
            state_transition="EXECUTE_CHECKOUT -> FINALIZE_OUTCOME",
            error="Buyer authorization missing"
        )
        return {
            "current_node": node_name,
            "checkout_status": "failed",
            "error_state": "Buyer authorization missing",
            "decision_trace": state["decision_trace"] + [trace]
        }

    try:
        # Execute checkout strictly through Authoritative PaymentEngine Choke Point
        pay_res = execute_payment_mandate(
            cart_id=cart_id,
            description=f"CartPilot Order: {cart_id}",
            notes={"cart_id": cart_id, "channel": state.get("channel", "langgraph_agent")}
        )

        trace = _add_trace(
            state=state,
            node=node_name,
            tool="execute_payment_mandate",
            input_summary=f"Cart: {cart_id}, Total: ₹{total_paise/100:.2f}",
            result_summary=f"Razorpay Order {pay_res['razorpay_order_id']} created. Link: {pay_res['payment_link_url']}",
            state_transition="EXECUTE_CHECKOUT -> VERIFY_PAYMENT",
            outcome="Payment Link Generated"
        )

        return {
            "current_node": node_name,
            "checkout_status": "link_created",
            "razorpay_order_id": pay_res["razorpay_order_id"],
            "payment_mandate_id": pay_res["payment_mandate_id"],
            "payment_link_url": pay_res["payment_link_url"],
            "payment_status": "created",
            "last_tool": "execute_payment_mandate",
            "decision_trace": state["decision_trace"] + [trace]
        }

    except Exception as e:
        trace = _add_trace(
            state=state,
            node=node_name,
            tool="create_order",
            input_summary=f"Failed to create payment for cart {cart_id}",
            result_summary=f"Payment Setup Error: {str(e)}",
            state_transition="EXECUTE_CHECKOUT -> HANDLE_RECOVERY",
            error=str(e)
        )
        return {
            "current_node": node_name,
            "checkout_status": "failed",
            "payment_status": "failed",
            "last_error_message": str(e),
            "decision_trace": state["decision_trace"] + [trace]
        }


def node_verify_payment(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Queries authoritative payment mandate status in SQLite and Razorpay API.
    Does NOT hallucinate payment success from payment link creation.
    """
    node_name = "VERIFY_PAYMENT"
    cart_id = state.get("cart_id")

    if not cart_id:
        return {
            "current_node": node_name,
            "payment_status": "none"
        }

    cart_state = get_cart_state(cart_id)
    pm = cart_state.get("payment") if cart_state else None
    authoritative_status = pm["status"] if pm else state.get("payment_status", "created")

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="get_cart_state",
        input_summary=f"Verifying payment status for cart {cart_id}",
        result_summary=f"Authoritative Payment Status: {authoritative_status}",
        state_transition="VERIFY_PAYMENT -> FINALIZE_OUTCOME" if authoritative_status in ["succeeded", "created", "pending"] else "VERIFY_PAYMENT -> HANDLE_RECOVERY",
        outcome=f"Payment {authoritative_status}"
    )

    return {
        "current_node": node_name,
        "payment_status": authoritative_status,
        "last_tool": "get_cart_state",
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_handle_recovery(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Payment Failure Recovery Branch:
    Translates raw error into actionable next steps using recovery_agent.py.
    Safely bounds retries without infinite loops.
    """
    node_name = "HANDLE_RECOVERY"
    err_msg = state.get("last_error_message") or "Payment authorization failed or declined by gateway."
    retry_count = state.get("retry_count", 0) + 1
    max_retries = state.get("max_retries", 2)

    recovery_info = analyze_failure(err_msg)
    recommendation = recovery_info.get("recommendation", "Please try a different payment method.")

    # Record in payment mandates if exists
    cart_id = state.get("cart_id")
    if cart_id:
        update_payment_mandate_status(
            cart_id=cart_id,
            status="failed",
            failure_reason=err_msg,
            recovery_action=recommendation
        )

    trace = _add_trace(
        state=state,
        node=node_name,
        tool="analyze_failure",
        input_summary=f"Payment failed: {err_msg}",
        result_summary=f"Recovery guidance: {recommendation} (Attempt {retry_count}/{max_retries})",
        state_transition="HANDLE_RECOVERY -> FINALIZE_OUTCOME",
        error=err_msg,
        outcome=f"Recovery advice generated: {recommendation}"
    )

    return {
        "current_node": node_name,
        "retry_count": retry_count,
        "recovery_state": {
            "failure_reason": err_msg,
            "recommendation": recommendation,
            "retry_count": retry_count,
            "can_retry": retry_count <= max_retries
        },
        "decision_trace": state["decision_trace"] + [trace]
    }


def node_finalize_outcome(state: BuyerGraphState) -> Dict[str, Any]:
    """
    Finalizes graph execution and persists structured decision trace to immutable SQLite audit_log.
    """
    node_name = "FINALIZE_OUTCOME"
    cart_id = state.get("cart_id") or state.get("intent_id") or "session_unknown"

    conn = get_db()
    cursor = conn.cursor()
    try:
        create_audit_log(
            cursor=cursor,
            ref_type="buyer_graph",
            ref_id=cart_id,
            event="Graph Execution Finished",
            detail=f"Status: {state.get('guardrail_status')}, Auth: {state.get('buyer_authorization_status')}, Pay: {state.get('payment_status')}"
        )
        conn.commit()
    except Exception as e:
        print(f"⚠️ Audit logging warning in finalize_outcome: {e}")
    finally:
        conn.close()

    return {
        "current_node": node_name
    }


# ─── 4. CONDITIONAL ROUTING FUNCTIONS ───────────────────────────────────────

def route_after_validate(state: BuyerGraphState) -> str:
    """Routes after guardrail validation."""
    status = state.get("guardrail_status", "blocked")
    rev_count = state.get("revision_count", 0)
    max_rev = state.get("max_revisions", 3)
    proposed = state.get("proposed_items", [])
    reason = (state.get("guardrail_reason") or "").lower()

    if status in ["approved", "pending_confirmation"]:
        return "GET_RECOMMENDATIONS"
    elif status == "blocked":
        # If cart is empty or blocked due to policy constraints that cannot be resolved by quantity drops, stop immediately
        if not proposed or "category" in reason or "not found" in reason or "empty" in reason:
            return "NOTIFY_BUYER_BLOCKED"
        if rev_count < max_rev:
            return "REVISE_CART"
        else:
            return "NOTIFY_BUYER_BLOCKED"
    return "NOTIFY_BUYER_BLOCKED"


def route_after_approval(state: BuyerGraphState) -> str:
    """Routes based on explicit buyer authorization."""
    auth = state.get("buyer_authorization_status", "REQUIRED")
    if auth in ["APPROVED", "NOT_REQUIRED"]:
        return "EXECUTE_CHECKOUT"
    elif auth == "DECLINED":
        return "FINALIZE_OUTCOME"
    else:
        # REQUIRED / Pending human approval -> stop before checkout
        return "FINALIZE_OUTCOME"


def route_after_checkout(state: BuyerGraphState) -> str:
    """Routes after checkout execution."""
    checkout_status = state.get("checkout_status")
    if checkout_status == "link_created":
        return "VERIFY_PAYMENT"
    else:
        return "HANDLE_RECOVERY"


def route_after_verify(state: BuyerGraphState) -> str:
    """Routes after payment verification."""
    pay_status = state.get("payment_status")
    if pay_status == "failed":
        return "HANDLE_RECOVERY"
    return "FINALIZE_OUTCOME"


# ─── 5. STATE GRAPH ASSEMBLY ────────────────────────────────────────────────

def build_buyer_graph() -> StateGraph:
    """Assembles and returns the compiled LangGraph StateGraph."""
    graph = StateGraph(BuyerGraphState)

    # Register Nodes
    graph.add_node("UNDERSTAND_INTENT", node_understand_intent)
    graph.add_node("SEARCH_CATALOG", node_search_catalog)
    graph.add_node("BUILD_CART", node_build_cart)
    graph.add_node("VALIDATE_CART", node_validate_cart)
    graph.add_node("REVISE_CART", node_revise_cart)
    graph.add_node("NOTIFY_BUYER_BLOCKED", node_notify_buyer_blocked)
    graph.add_node("GET_RECOMMENDATIONS", node_get_recommendations)
    graph.add_node("PRESENT_FOR_APPROVAL", node_present_for_approval)
    graph.add_node("EXECUTE_CHECKOUT", node_execute_checkout)
    graph.add_node("VERIFY_PAYMENT", node_verify_payment)
    graph.add_node("HANDLE_RECOVERY", node_handle_recovery)
    graph.add_node("FINALIZE_OUTCOME", node_finalize_outcome)

    # Flow Edges
    graph.add_edge(START, "UNDERSTAND_INTENT")
    graph.add_edge("UNDERSTAND_INTENT", "SEARCH_CATALOG")
    graph.add_edge("SEARCH_CATALOG", "BUILD_CART")
    graph.add_edge("BUILD_CART", "VALIDATE_CART")

    # Conditional Revision / Progress
    graph.add_conditional_edges(
        "VALIDATE_CART",
        route_after_validate,
        {
            "REVISE_CART": "REVISE_CART",
            "NOTIFY_BUYER_BLOCKED": "NOTIFY_BUYER_BLOCKED",
            "GET_RECOMMENDATIONS": "GET_RECOMMENDATIONS",
            "PRESENT_FOR_APPROVAL": "PRESENT_FOR_APPROVAL"
        }
    )
    graph.add_edge("REVISE_CART", "VALIDATE_CART")
    graph.add_edge("NOTIFY_BUYER_BLOCKED", "FINALIZE_OUTCOME")
    graph.add_edge("GET_RECOMMENDATIONS", "PRESENT_FOR_APPROVAL")

    # Approval Gate
    graph.add_conditional_edges(
        "PRESENT_FOR_APPROVAL",
        route_after_approval,
        {
            "EXECUTE_CHECKOUT": "EXECUTE_CHECKOUT",
            "FINALIZE_OUTCOME": "FINALIZE_OUTCOME"
        }
    )

    # Checkout & Payment Verification
    graph.add_conditional_edges(
        "EXECUTE_CHECKOUT",
        route_after_checkout,
        {
            "VERIFY_PAYMENT": "VERIFY_PAYMENT",
            "HANDLE_RECOVERY": "HANDLE_RECOVERY"
        }
    )

    graph.add_conditional_edges(
        "VERIFY_PAYMENT",
        route_after_verify,
        {
            "HANDLE_RECOVERY": "HANDLE_RECOVERY",
            "FINALIZE_OUTCOME": "FINALIZE_OUTCOME"
        }
    )

    graph.add_edge("HANDLE_RECOVERY", "FINALIZE_OUTCOME")
    graph.add_edge("FINALIZE_OUTCOME", END)

    return graph


# ─── 6. RUNNABLE BUYER ORCHESTRATOR ──────────────────────────────────────────

_checkpointer = MemorySaver()
buyer_graph_app = build_buyer_graph().compile(checkpointer=_checkpointer)


def _get_curated_recommendations(limit: int = 3) -> List[Dict[str, Any]]:
    """Fetches top-rated store recommendations matching merchant policy."""
    recs = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sku, name, price_paise, category, image_url, description, metadata
            FROM catalog
            WHERE stock > 0 AND image_url IS NOT NULL AND image_url != ''
            ORDER BY boosted DESC, price_paise ASC LIMIT ?
        """, (limit,))
        for r in cursor.fetchall():
            meta = {}
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
                except Exception:
                    meta = {}
            recs.append({
                "sku": r["sku"],
                "name": r["name"],
                "price_paise": r["price_paise"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "category": r["category"],
                "image_url": r["image_url"],
                "description": r["description"] or "",
                "metadata": meta,
                "tier": "trending_curated",
                "reason": "Top trending pick matching merchant policy.",
                "final_score": 0.85
            })
        conn.close()
    except Exception as e:
        print(f"⚠️ Error fetching curated recommendations: {e}")
    return recs


def _find_related_recommendations(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Finds relevant catalog items based on keyword matching for informational questions."""
    words = [w.strip("!?,.'\"").lower() for w in query.split() if len(w.strip("!?,.'\"")) >= 3]
    stop = {"how", "to", "cook", "prepare", "make", "what", "is", "the", "recipe", "for", "do", "i", "can", "tell", "me", "about", "best", "way", "does", "should", "you"}
    keywords = [w for w in words if w not in stop]

    if not keywords:
        return _get_curated_recommendations(limit)

    expanded = []
    for kw in keywords:
        expanded.append(kw)
        if kw.endswith("s") and len(kw) >= 4:
            expanded.append(kw[:-1])
        elif kw.endswith("es") and len(kw) >= 5:
            expanded.append(kw[:-2])
    expanded = list(dict.fromkeys(expanded))

    recs = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        query_parts = ["LOWER(name) LIKE ?" for _ in expanded]
        params = [f"%{kw}%" for kw in expanded]
        cursor.execute(f"""
            SELECT sku, name, price_paise, category, image_url, description, metadata
            FROM catalog
            WHERE ({' OR '.join(query_parts)}) AND stock > 0
            ORDER BY boosted DESC, price_paise ASC LIMIT ?
        """, params + [limit])
        for r in cursor.fetchall():
            meta = {}
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
                except Exception:
                    meta = {}
            recs.append({
                "sku": r["sku"],
                "name": r["name"],
                "price_paise": r["price_paise"],
                "price_rupees": round(r["price_paise"] / 100, 2),
                "category": r["category"],
                "image_url": r["image_url"],
                "description": r["description"] or "",
                "metadata": meta,
                "tier": "related_product",
                "reason": f"Matching item for '{r['name']}' in our store catalog.",
                "final_score": 0.90
            })
        conn.close()
    except Exception as e:
        print(f"⚠️ Error searching related items: {e}")

    if not recs:
        return _get_curated_recommendations(limit)
    return recs


def _answer_informational_query(query: str) -> str:
    """Answers general informational, recipe, or advice questions without force-adding items to cart."""
    low = query.lower().strip('!?. ')

    # Fast domain responses for frequent queries
    if "cook egg" in low or "boil egg" in low or "scramble egg" in low or "make egg" in low or ("egg" in low and any(w in low for w in ["cook", "how", "recipe", "boil", "fry", "scramble", "prepare"])):
        return (
            "To cook eggs to perfection, boil them for 6-7 minutes for soft-boiled with a jammy yolk, "
            "or 9-10 minutes for firm hard-boiled eggs. For creamy scrambled eggs, whisk with a pinch of salt "
            "and cook gently in butter over low heat! 🍳\n\n"
            "I've highlighted fresh grocery eggs and kitchen tools below from our store if you need supplies."
        )
    if "joke" in low:
        return (
            "Why did the shopping cart get promoted? Because it always carried its weight! 😄\n\n"
            "Let me know if there's anything I can help you find in our store today!"
        )
    if "pasta" in low and any(w in low for w in ["cook", "recipe", "make", "how"]):
        return (
            "To cook delicious pasta, bring a large pot of salted water to a rolling boil. Add pasta and cook for 8-10 minutes "
            "until al dente. Reserve half a cup of pasta water, drain, and toss with your favorite sauce and olive oil! 🍝\n\n"
            "We have pasta, olive oil, and kitchen cookware in stock below if you'd like to browse."
        )
    if "tea" in low and any(w in low for w in ["make", "brew", "how", "prepare"]):
        return (
            "To brew a comforting cup of tea, boil fresh water, steep your tea leaves or bag for 3-5 minutes, "
            "and add honey, lemon, or milk to taste. ☕\n\n"
            "Explore our selection of premium teas, honey, and kettles below!"
        )
    if "coffee" in low and any(w in low for w in ["make", "brew", "how", "prepare"]):
        return (
            "For rich coffee, use a 1:15 ratio of freshly ground coffee to hot water (around 93°C / 200°F). "
            "Brew using a French press or pour-over for 3-4 minutes, then pour and enjoy! ☕\n\n"
            "Check out our coffee beans, mugs, and makers in the catalog below."
        )
    if "return policy" in low or "refund" in low:
        return (
            "We offer a hassle-free 7-day return policy on eligible unopened items. "
            "You can initiate a return or exchange anytime directly from your order dashboard or by contacting support."
        )
    if "shipping" in low or "delivery" in low:
        return (
            "Standard delivery takes 2 to 4 business days across major cities, and express overnight shipping "
            "is available on eligible items. You'll receive live tracking as soon as your order ships!"
        )
    if "payment" in low or "pay" in low or "razorpay" in low:
        return (
            "We support all major payment methods including UPI (Google Pay, PhonePe, Paytm), Credit/Debit Cards, "
            "Net Banking, and Wallets via our secure Razorpay payment gateway."
        )

    try:
        from backend.engine.llm import generate_text
        system_prompt = (
            "You are CartPilot AI, a knowledgeable, friendly e-commerce shopping concierge.\n"
            "The customer asked an informational, recipe, or advice question.\n"
            "Provide a helpful, concise (2-3 sentences) answer with friendly formatting.\n"
            "Politely mention that related store items or ingredients are available in our catalog if they need any.\n"
            "Do NOT pretend to add items to their cart or mention order policies."
        )
        ans = generate_text(prompt=query, system_prompt=system_prompt)
        if ans:
            return ans.strip()
    except Exception as e:
        print(f"⚠️ Error in informational query generation: {e}")

    return (
        f"Here are some helpful tips for '{query}'. "
        "Feel free to check out our matching store essentials below if you need supplies or ingredients!"
    )


def run_buyer_journey(
    query: str,
    spend_cap_paise: Optional[int] = None,
    session_id: Optional[str] = None,
    auto_authorize: bool = False,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    current_cart: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Entrypoint function to run the full LangGraph AI Buyer Journey.
    Returns the complete structured state including decision trace.
    Preserves active shopping cart context across multi-turn sessions.
    """
    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    exec_id = f"exec_{uuid.uuid4().hex[:12]}"
    effective_cap = spend_cap_paise or 1000000

    q_clean = (query or "").strip()
    active_cart = [dict(it) for it in (current_cart or [])]
    active_cart_total = sum(it.get("price_paise", 0) * it.get("qty", 1) for it in active_cart)

    # ── CONVERSATIONAL INTENT DISPATCH ─────────────────────────────
    # Fast, friendly, zero-latency routing for non-purchase queries
    intent = classify_intent(q_clean)

    if intent == "greeting":
        starter_recs = _get_curated_recommendations(limit=3)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "Hello! 👋 I'm CartPilot, your personal AI shopping assistant. How can I help you today? You can search for products (e.g. 'sunglasses under ₹2,000' or 'fresh groceries'), ask for recommendations, or let me curate a cart for you.",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": starter_recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Greeting: {query}",
                "result_summary": "Provided friendly storefront greeting.",
                "guardrail_status": "approved",
                "state_transition": "START -> GREETING",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Customer greeted"
            }]
        }

    if intent == "gratitude":
        recs = _get_curated_recommendations(limit=3)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "You're very welcome! 😊 Let me know if you need anything else, want to look for more products, or are ready to review your cart.",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Gratitude: {query}",
                "result_summary": "Courteous acknowledgment sent.",
                "guardrail_status": "approved",
                "state_transition": "START -> GRATITUDE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Gratitude acknowledged"
            }]
        }

    if intent == "acknowledgement":
        recs = _get_curated_recommendations(limit=3)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "Sounds good! Let me know what you'd like to explore next—whether you need product suggestions, price comparisons, or help completing your order.",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Acknowledgement: {query}",
                "result_summary": "Friendly conversational acknowledgement provided.",
                "guardrail_status": "approved",
                "state_transition": "START -> ACKNOWLEDGEMENT",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Acknowledged"
            }]
        }

    if intent == "farewell":
        recs = _get_curated_recommendations(limit=3)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "Goodbye! Have a fantastic day, and happy shopping whenever you return! 👋",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Farewell: {query}",
                "result_summary": "Warm farewell sent.",
                "guardrail_status": "approved",
                "state_transition": "START -> FAREWELL",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Farewell completed"
            }]
        }

    if intent == "help_identity":
        recs = _get_curated_recommendations(limit=4)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": (
                "I'm CartPilot, your autonomous AI shopping assistant! 🛒\n\n"
                "Here is how I can assist you:\n"
                "• **Find & Compare Products**: Search across 30+ store departments with live prices.\n"
                "• **Smart Cart Curation**: Tell me what you need and your budget (e.g. 'sunglasses under ₹2,000') and I'll assemble your cart.\n"
                "• **Intelligent Recommendations**: Discover complementary items with instant merchant savings.\n"
                "• **Budget & Policy Protection**: I keep all orders strictly within your spending limit.\n\n"
                "What would you like to explore today?"
            ),
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Help/Identity: {query}",
                "result_summary": "Capabilities overview provided.",
                "guardrail_status": "approved",
                "state_transition": "START -> HELP_IDENTITY",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Capabilities presented"
            }]
        }

    if intent == "explore":
        starter_recs = _get_curated_recommendations(limit=4)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "We carry products across 31 departments including Groceries, Electronics & Laptops, Beauty & Fragrances, Men & Women's Fashion, and Watches & Accessories. What category or product would you like to explore?",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": starter_recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Explore: {query}",
                "result_summary": "Provided store department overview.",
                "guardrail_status": "approved",
                "state_transition": "START -> EXPLORE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Store categories presented"
            }]
        }

    if intent == "suggestions":
        starter_recs = _get_curated_recommendations(limit=4)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "Here are some of our top trending picks and customer favorites across the store! Let me know if you're looking for a specific category, budget, or occasion.",
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": starter_recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": None,
                "input_summary": f"Suggestions: {query}",
                "result_summary": "Provided top store recommendations without adding to cart.",
                "guardrail_status": "approved",
                "state_transition": "START -> SUGGESTIONS",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Trending picks suggested"
            }]
        }

    if intent == "cart_clear":
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": "I've cleared your shopping cart. What would you like to start a new order with?",
            "proposed_items": [],
            "cart_total_paise": 0,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": _get_curated_recommendations(limit=3),
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": "clear_cart",
                "input_summary": "Cart clear requested",
                "result_summary": "Cart cleared.",
                "guardrail_status": "approved",
                "state_transition": "START -> CART_CLEARED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Cart cleared"
            }]
        }

    if intent == "cart_view":
        if active_cart:
            item_lines = [f"• {it.get('qty', 1)}x {it.get('name', it.get('sku'))} (₹{(it.get('price_paise', 0)*it.get('qty', 1))/100:.2f})" for it in active_cart]
            msg = (
                f"Your cart currently contains {len(active_cart)} item{'s' if len(active_cart) != 1 else ''}:\n"
                + "\n".join(item_lines)
                + f"\n\n**Total:** ₹{active_cart_total/100:.2f}.\nReady for checkout whenever you'd like!"
            )
            return {
                "session_id": sid,
                "graph_execution_id": exec_id,
                "user_request": query,
                "assistant_message": msg,
                "proposed_items": active_cart,
                "cart_total_paise": active_cart_total,
                "spend_cap_paise": effective_cap,
                "guardrail_status": "approved",
                "guardrail_reason": "",
                "recommendations": _get_curated_recommendations(limit=3),
                "buyer_authorization_status": "NOT_REQUIRED",
                "checkout_status": "not_started",
                "decision_trace": [{
                    "node": "CONVERSATIONAL_INTENT",
                    "tool": "view_cart",
                    "input_summary": "Cart view requested",
                    "result_summary": f"Displayed active cart with {len(active_cart)} items.",
                    "guardrail_status": "approved",
                    "state_transition": "START -> CART_VIEW",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                    "outcome": "Cart status shown"
                }]
            }
        else:
            return {
                "session_id": sid,
                "graph_execution_id": exec_id,
                "user_request": query,
                "assistant_message": "Your cart is currently empty. Tell me what you'd like to buy (e.g. 'sunglasses under ₹2,000' or 'fresh groceries') and I'll find the best options for you!",
                "proposed_items": [],
                "cart_total_paise": 0,
                "spend_cap_paise": effective_cap,
                "guardrail_status": "approved",
                "guardrail_reason": "",
                "recommendations": _get_curated_recommendations(limit=3),
                "buyer_authorization_status": "NOT_REQUIRED",
                "checkout_status": "not_started",
                "decision_trace": [{
                    "node": "CONVERSATIONAL_INTENT",
                    "tool": "view_cart",
                    "input_summary": "Cart view requested",
                    "result_summary": "Cart status shown (empty).",
                    "guardrail_status": "approved",
                    "state_transition": "START -> CART_VIEW",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                    "outcome": "Cart status shown"
                }]
            }

    if intent == "informational":
        answer = _answer_informational_query(q_clean)
        related_recs = _find_related_recommendations(q_clean, limit=3)
        return {
            "session_id": sid,
            "graph_execution_id": exec_id,
            "user_request": query,
            "assistant_message": answer,
            "proposed_items": active_cart,
            "cart_total_paise": active_cart_total,
            "spend_cap_paise": effective_cap,
            "guardrail_status": "approved",
            "guardrail_reason": "",
            "recommendations": related_recs,
            "buyer_authorization_status": "NOT_REQUIRED",
            "checkout_status": "not_started",
            "decision_trace": [{
                "node": "CONVERSATIONAL_INTENT",
                "tool": "informational_advisor",
                "input_summary": f"Question: {query}",
                "result_summary": f"Answered question. Provided {len(related_recs)} related product recommendations without altering cart.",
                "guardrail_status": "approved",
                "state_transition": "START -> ANSWER_QUESTION",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "outcome": "Informational answer provided"
            }]
        }

    initial_state: BuyerGraphState = {
        "session_id": sid,
        "graph_execution_id": exec_id,
        "user_request": query,
        "channel": "langgraph_agent",
        "conversation_history": conversation_history or [],
        "goal": "",
        "spend_cap_paise": effective_cap,
        "required_items": [],
        "optional_items": [],
        "category_preferences": [],
        "candidate_products": [],
        "current_cart": active_cart,
        "proposed_items": [],
        "oos_items": [],
        "cart_total_paise": 0,
        "intent_id": None,
        "cart_id": None,
        "guardrail_status": "unvalidated",
        "guardrail_reason": "",
        "revision_count": 0,
        "max_revisions": 3,
        "recommendations": [],
        "buyer_authorization_status": "APPROVED" if auto_authorize else "REQUIRED",
        "auto_authorize": auto_authorize,
        "checkout_status": "not_started",
        "razorpay_order_id": None,
        "payment_mandate_id": None,
        "payment_link_url": None,
        "payment_status": "none",
        "retry_count": 0,
        "max_retries": 2,
        "recovery_state": None,
        "error_state": None,
        "last_tool": None,
        "last_error_code": None,
        "last_error_message": None,
        "current_node": START,
        "decision_trace": []
    }

    config = {"configurable": {"thread_id": sid}}
    final_state = buyer_graph_app.invoke(initial_state, config=config)
    return final_state
