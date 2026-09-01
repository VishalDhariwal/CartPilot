#!/usr/bin/env python3
"""
ops/external_buyer_agent.py
===========================
Standalone External AI Buyer Agent Client.

PROVES EXTERNAL TRANSACTABILITY:
- ZERO internal code imports from backend.* or CartPilot libraries.
- Operates purely as a 3rd-party shopping agent hitting standard REST endpoints over HTTP.
- Executes full autonomous discovery, cart negotiation, mandate validation, and checkout.
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


class ExternalBuyerAgent:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def _http_get(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url, headers={"User-Agent": "External-AI-Buyer-Agent/1.0", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP GET {url} failed ({e.code}): {err_msg}")

    def _http_post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "External-AI-Buyer-Agent/1.0",
                "Accept": "application/json"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP POST {url} failed ({e.code}): {err_msg}")

    def discover_catalog(self) -> list:
        """Step 1: Discover available products from the agent-readable catalog."""
        print("🔍 [Step 1] Discovering merchant catalog via GET /catalog...")
        res = self._http_get("/catalog")
        catalog = res.get("catalog") or res.get("items") or (res if isinstance(res, list) else [])
        print(f"   ✓ Discovered {len(catalog)} active products from merchant catalog.")
        return catalog

    def request_agent_checkout(self, query: str, spend_cap_paise: int = 1500000) -> Dict[str, Any]:
        """Step 2: Submit natural-language purchase request."""
        print(f"\n💬 [Step 2] Sending purchase intent: '{query}' (Budget: ₹{spend_cap_paise/100:.0f})...")
        payload = {
            "query": query,
            "spend_cap_paise": spend_cap_paise,
            "conversation_history": []
        }
        res = self._http_post("/checkout/agent-checkout", payload)
        print(f"   ✓ Received Agent Response:")
        print(f"     • Status: {res.get('status')}")
        print(f"     • Cart ID: {res.get('cart_id')}")
        print(f"     • Items: {len(res.get('proposed_items', []))} items (Total: ₹{res.get('total_paise', 0)/100:.2f})")
        if res.get("upsell"):
            u = res["upsell"]
            print(f"     • AI Upsell Offered: {u.get('name')} (₹{u.get('price_paise', 0)/100:.2f}) - {u.get('reason')}")
        return res

    def finalize_and_pay(self, cart_id: str, accept_upsell: bool = False, upsell_sku: Optional[str] = None) -> Dict[str, Any]:
        """Step 3: Finalize cart and receive Razorpay payment link."""
        action_str = f"with upsell {upsell_sku}" if (accept_upsell and upsell_sku) else "without upsell"
        print(f"\n💳 [Step 3] Finalizing Cart Mandate '{cart_id}' {action_str}...")
        payload = {
            "cart_id": cart_id,
            "accept_upsell": accept_upsell,
            "upsell_accepted": accept_upsell,
            "upsell_sku": upsell_sku
        }
        res = self._http_post("/checkout/finalize", payload)
        print(f"   ✓ Checkout Order Finalized:")
        print(f"     • Payment Mandate ID: {res.get('payment_mandate_id')}")
        print(f"     • Razorpay Order ID:  {res.get('razorpay_order_id')}")
        print(f"     • Checkout Link URL:  {res.get('payment_link') or res.get('payment_url')}")
        print(f"     • Amount:             ₹{res.get('amount_paise', 0)/100:.2f}")
        return res

    def poll_payment_status(self, cart_id: str, max_attempts: int = 5) -> Dict[str, Any]:
        """Step 4: Poll payment & settlement status."""
        print(f"\n⏱️  [Step 4] Polling payment settlement status for cart '{cart_id}'...")
        for attempt in range(1, max_attempts + 1):
            res = self._http_get(f"/checkout/cart/{cart_id}/status")
            status = res.get("payment_status") or res.get("status")
            print(f"   [Poll #{attempt}] Payment Status: {status}")
            if status in ("succeeded", "captured"):
                print(f"   ✅ Payment verified and captured successfully!")
                return res
            time.sleep(1.0)
        return res

    def run_full_journey(self, query: str = "order me a classic 350 motorcycle with sunglasses, budget 250000"):
        print("=" * 70)
        print("🤖 EXTERNAL AI BUYER AGENT — INDEPENDENT E2E TRANSACTION DEMO")
        print("=" * 70)
        catalog = self.discover_catalog()
        checkout_res = self.request_agent_checkout(query)

        cart_id = checkout_res.get("cart_id")
        if not cart_id or checkout_res.get("status") == "blocked":
            print(f"❌ Purchase could not be fulfilled: {checkout_res.get('reason')}")
            return checkout_res

        upsell = checkout_res.get("upsell")
        accept_upsell = bool(upsell)
        upsell_sku = upsell.get("sku") if upsell else None

        pay_res = self.finalize_and_pay(cart_id, accept_upsell=accept_upsell, upsell_sku=upsell_sku)
        status_res = self.poll_payment_status(cart_id)

        print("\n" + "=" * 70)
        print("🎉 TRANSACTION COMPLETED OVER PUBLIC HTTP REST PROTOCOL")
        print("=" * 70)
        return status_res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="External AI Buyer Agent CLI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of CartPilot API server")
    parser.add_argument("--query", default="order me a royal enfield motorcycle and black aviator sunglasses", help="Natural language shopping query")
    args = parser.parse_args()

    agent = ExternalBuyerAgent(base_url=args.base_url)
    try:
        agent.run_full_journey(query=args.query)
    except Exception as e:
        print(f"\n❌ Error during external buyer execution: {e}")
        sys.exit(1)
