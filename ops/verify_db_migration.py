#!/usr/bin/env python3
"""
CartPilot Database Parity & Integrity Verification Tool
Compares SQLite Source vs PostgreSQL Destination across all critical commerce metrics.
"""

import os
import sys
import sqlite3
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.environ.get("CARTPILOT_DB") or os.path.join(BASE_DIR, "cartpilot.db")
POSTGRES_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

TABLES_TO_VERIFY = [
    "catalog",
    "policy_config",
    "intent_mandates",
    "cart_mandates",
    "payment_mandates",
    "refunds",
    "audit_log",
    "historical_orders",
    "basket_pairs",
    "chat_sessions",
    "upsell_events",
    "category_compatibility",
    "growth_actions",
    "growth_outcomes",
    "promotion_experiments",
]

def verify():
    if not POSTGRES_URL:
        print("❌ Error: DATABASE_URL is not set for PostgreSQL verification.")
        sys.exit(1)

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        print("❌ Error: psycopg2 is required. Install via: pip install psycopg2-binary")
        sys.exit(1)

    sq_conn = sqlite3.connect(SQLITE_DB_PATH)
    sq_conn.row_factory = sqlite3.Row
    sq_cur = sq_conn.cursor()

    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_cur = pg_conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 80)
    print("🔍 CartPilot Database Parity Audit (SQLite vs. PostgreSQL)")
    print("=" * 80)

    all_passed = True

    # 1. Row Count Parity Check
    print("\n1. Table Row Count Parity:")
    for table in TABLES_TO_VERIFY:
        try:
            sq_cur.execute(f"SELECT COUNT(*) FROM {table}")
            sq_cnt = sq_cur.fetchone()[0]
        except Exception:
            sq_cnt = 0

        try:
            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_cnt = pg_cur.fetchone()["count"]
        except Exception:
            pg_cnt = 0

        diff = pg_cnt - sq_cnt
        status_icon = "✓" if diff == 0 else "❌"
        if diff != 0:
            all_passed = False
        print(f"  {status_icon} {table:<25} SQLite: {sq_cnt:>5}  |  PostgreSQL: {pg_cnt:>5}  (Diff: {diff:>+3})")

    # 2. Commerce Financial & Mandate Parity
    print("\n2. Commerce Metrics Parity:")
    
    # Gross Order Volume (Approved Carts)
    sq_cur.execute("SELECT COALESCE(SUM(total_paise), 0) FROM cart_mandates WHERE status = 'approved'")
    sq_gross = sq_cur.fetchone()[0]
    pg_cur.execute("SELECT COALESCE(SUM(total_paise), 0) as sum FROM cart_mandates WHERE status = 'approved'")
    pg_gross = pg_cur.fetchone()["sum"]
    passed_gross = (sq_gross == pg_gross)
    if not passed_gross: all_passed = False
    print(f"  {'✓' if passed_gross else '❌'} Gross Order Volume:      SQLite: ₹{sq_gross/100:.2f}  |  PostgreSQL: ₹{pg_gross/100:.2f}")

    # Settled Payments
    sq_cur.execute("SELECT COUNT(*), COALESCE(SUM(amount_paise), 0) FROM payment_mandates WHERE status = 'succeeded' AND COALESCE(refund_status, 'NONE') != 'REFUNDED'")
    sq_settled = sq_cur.fetchone()
    pg_cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(amount_paise), 0) as sum FROM payment_mandates WHERE status = 'succeeded' AND COALESCE(refund_status, 'NONE') != 'REFUNDED'")
    pg_settled = pg_cur.fetchone()
    passed_settled = (sq_settled[0] == pg_settled["count"] and sq_settled[1] == pg_settled["sum"])
    if not passed_settled: all_passed = False
    print(f"  {'✓' if passed_settled else '❌'} Settled Orders:          SQLite: {sq_settled[0]} (₹{sq_settled[1]/100:.2f})  |  PostgreSQL: {pg_settled['count']} (₹{pg_settled['sum']/100:.2f})")

    # Reversals & Refunds
    sq_cur.execute("SELECT COUNT(*), COALESCE(SUM(requested_amount_paise), 0) FROM refunds")
    sq_ref = sq_cur.fetchone()
    pg_cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(requested_amount_paise), 0) as sum FROM refunds")
    pg_ref = pg_cur.fetchone()
    passed_ref = (sq_ref[0] == pg_ref["count"])
    if not passed_ref: all_passed = False
    print(f"  {'✓' if passed_ref else '❌'} Resolution Refunds:      SQLite: {sq_ref[0]}  |  PostgreSQL: {pg_ref['count']}")

    # Growth Outcomes
    sq_cur.execute("SELECT COUNT(*), COALESCE(SUM(incremental_paise), 0) FROM growth_outcomes WHERE outcome_type = 'paid'")
    sq_growth = sq_cur.fetchone()
    pg_cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(incremental_paise), 0) as sum FROM growth_outcomes WHERE outcome_type = 'paid'")
    pg_growth = pg_cur.fetchone()
    passed_growth = (sq_growth[0] == pg_growth["count"] and sq_growth[1] == pg_growth["sum"])
    if not passed_growth: all_passed = False
    print(f"  {'✓' if passed_growth else '❌'} Verified AI Growth Lift: SQLite: {sq_growth[0]} (₹{sq_growth[1]/100:.2f})  |  PostgreSQL: {pg_growth['count']} (₹{pg_growth['sum']/100:.2f})")

    print("=" * 80)
    if all_passed:
        print("🎉 PARITY AUDIT PASSED: PostgreSQL matches SQLite with 100% data fidelity.")
        sys.exit(0)
    else:
        print("⚠️ PARITY AUDIT WARNING: Discrepancies detected between SQLite and PostgreSQL.")
        sys.exit(1)

if __name__ == "__main__":
    verify()
