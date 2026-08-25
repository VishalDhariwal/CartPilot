#!/usr/bin/env python3
"""
CartPilot Cart Recovery Scanner Job (Azure Container Apps Job / Cron)
Periodically scans for idle abandoned carts exceeding merchant threshold,
evaluates recovery eligibility, and executes autonomous recovery links.
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()

from backend.db import get_db
from backend.agents.recovery_agent import detect_recoverable_carts, execute_recovery


def run_recovery_scanner():
    start_time = time.time()
    now_iso = datetime.utcnow().isoformat()
    print("=" * 70)
    print(f"🚀 Starting CartPilot Recovery Scanner Job at {now_iso}")
    print("=" * 70)

    # 1. Detect recoverable carts based on merchant policy idle thresholds
    carts = detect_recoverable_carts()
    print(f"🔍 Discovered {len(carts)} recoverable cart opportunities.")

    recovered_count = 0
    total_recovered_paise = 0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT growth_mode FROM policy_config WHERE id = 1")
    pol = cursor.fetchone()
    growth_mode = pol.get("growth_mode", "manual") if isinstance(pol, dict) else (pol[0] if pol else "manual")
    conn.close()

    print(f"⚙️ Merchant Growth Mode: {growth_mode.upper()}")

    # 2. In autonomous or scheduled execution, execute eligible recoveries
    for cart in carts:
        cart_id = cart["cart_id"]
        val_paise = cart["total_paise"]
        print(f"  • Cart {cart_id}: ₹{val_paise/100:.2f} ({cart['idle_minutes']:.1f}m idle)")

        if growth_mode == "autonomous" or os.getenv("AUTONOMOUS_RECOVERY", "false").lower() == "true":
            try:
                res = execute_recovery(cart_id)
                if res.get("status") == "success":
                    recovered_count += 1
                    total_recovered_paise += val_paise
                    print(f"    ✓ Reissued Razorpay recovery checkout link: {res.get('payment_link')}")
            except Exception as e:
                print(f"    ❌ Error executing recovery for cart {cart_id}: {e}")

    elapsed = round(time.time() - start_time, 2)
    print("=" * 70)
    print(f"✅ Recovery Scanner Finished in {elapsed}s. Actioned: {recovered_count} carts (₹{total_recovered_paise/100:.2f})")
    print("=" * 70)


if __name__ == "__main__":
    run_recovery_scanner()
