import sqlite3
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("CARTPILOT_DB") or os.path.join(BASE_DIR, "cartpilot.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ── Core tables ──────────────────────────────────────────────────────
    cursor.executescript('''
    CREATE TABLE IF NOT EXISTS catalog (
      sku TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      price_paise INTEGER NOT NULL,
      stock INTEGER NOT NULL,
      category TEXT NOT NULL,
      merchant TEXT NOT NULL,
      boosted INTEGER NOT NULL DEFAULT 0,
      image_url TEXT,
      description TEXT,
      tags TEXT,
      metadata TEXT,
      embedding TEXT
    );


    CREATE TABLE IF NOT EXISTS policy_config (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      spend_cap_paise INTEGER NOT NULL,
      allowed_categories TEXT NOT NULL,
      autonomy_threshold_paise INTEGER NOT NULL DEFAULT 500000
    );

    CREATE TABLE IF NOT EXISTS intent_mandates (
      id TEXT PRIMARY KEY,
      raw_request TEXT NOT NULL,
      goal TEXT NOT NULL,
      spend_cap_paise INTEGER NOT NULL,
      channel TEXT NOT NULL DEFAULT 'web_chat',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS cart_mandates (
      id TEXT PRIMARY KEY,
      intent_id TEXT NOT NULL REFERENCES intent_mandates(id),
      items TEXT NOT NULL,
      total_paise INTEGER NOT NULL,
      status TEXT NOT NULL,
      reason TEXT NOT NULL,
      reversible INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS payment_mandates (
      id TEXT PRIMARY KEY,
      cart_id TEXT NOT NULL REFERENCES cart_mandates(id),
      razorpay_order_id TEXT,
      razorpay_payment_id TEXT,
      amount_paise INTEGER NOT NULL,
      status TEXT NOT NULL,
      failure_reason TEXT,
      recovery_action TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ref_type TEXT NOT NULL,
      ref_id TEXT NOT NULL,
      event TEXT NOT NULL,
      detail TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    -- Historical orders table: seeded with synthetic orders and updated dynamically on real purchases
    CREATE TABLE IF NOT EXISTS historical_orders (
      order_id TEXT PRIMARY KEY,
      items TEXT NOT NULL,           -- JSON array of SKUs
      is_synthetic INTEGER NOT NULL, -- 1 = bootstrap data, 0 = real completed order
      created_at TEXT NOT NULL
    );

    -- Market Basket Analysis pairs: derived from LLM-seeded priors (ai_suggested, retired) or statistical lift (data_verified)
    CREATE TABLE IF NOT EXISTS basket_pairs (
      sku_a TEXT NOT NULL,
      sku_b TEXT NOT NULL,
      lift REAL,
      support REAL,
      confidence REAL,
      source TEXT NOT NULL DEFAULT 'ai_suggested',
      reasoning TEXT,
      co_occurrence_count INTEGER DEFAULT 0,
      computed_at TEXT NOT NULL,
      muted INTEGER NOT NULL DEFAULT 0,
      retired INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (sku_a, sku_b)
    );

    -- Cross-browser persistent chat sessions table
    CREATE TABLE IF NOT EXISTS chat_sessions (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      session_data TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );


    -- Measurement table: every upsell/cross-sell offer, outcome, and AOV impact
    CREATE TABLE IF NOT EXISTS upsell_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cart_id TEXT NOT NULL,
      suggested_sku TEXT NOT NULL,
      accepted INTEGER NOT NULL,
      cart_total_before_paise INTEGER NOT NULL,
      cart_total_after_paise INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );

    -- Scalable Layer 1: Category compatibility graph (LLM-generated, merchant-editable)
    -- editable=1 means LLM regeneration may overwrite; editable=0 means merchant has locked the row
    CREATE TABLE IF NOT EXISTS category_compatibility (
      category_a TEXT NOT NULL,
      category_b TEXT NOT NULL,
      reasoning TEXT NOT NULL,
      editable INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      PRIMARY KEY (category_a, category_b)
    );

    -- AI Growth Agent: Next Best Action & opportunity detection ledger
    CREATE TABLE IF NOT EXISTS growth_actions (
      id TEXT PRIMARY KEY,
      action_type TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'detected',
      opportunity_type TEXT NOT NULL,
      title TEXT NOT NULL,
      explanation TEXT NOT NULL,
      affected_ref TEXT,
      est_revenue_paise INTEGER DEFAULT 0,
      confidence REAL DEFAULT 0.0,
      recommended_action TEXT,
      execution_ref TEXT,
      mode TEXT DEFAULT 'manual',
      created_at TEXT NOT NULL,
      executed_at TEXT,
      dismissed_at TEXT,
      notes TEXT
    );

    -- AI Growth Agent: Verified empirical revenue attribution & learning store
    CREATE TABLE IF NOT EXISTS growth_outcomes (
      id TEXT PRIMARY KEY,
      action_id TEXT,
      outcome_type TEXT NOT NULL,
      before_paise INTEGER DEFAULT 0,
      after_paise INTEGER DEFAULT 0,
      incremental_paise INTEGER DEFAULT 0,
      revenue_type TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    -- AI Growth Agent: Managed promotion experiment lifecycle store
    CREATE TABLE IF NOT EXISTS promotion_experiments (
      id TEXT PRIMARY KEY,
      sku TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, COMPLETED, FAILED, RETIRED, NO_ACTION
      action_id TEXT,
      baseline_stock INTEGER NOT NULL,
      baseline_velocity_daily REAL NOT NULL,
      baseline_days_of_inventory REAL NOT NULL,
      baseline_orders_30d INTEGER NOT NULL,
      buyer_relevance_score REAL NOT NULL,
      experiment_horizon_days INTEGER NOT NULL DEFAULT 14,
      started_at TEXT NOT NULL,
      ends_at TEXT NOT NULL,
      cooldown_until TEXT NOT NULL,
      current_stock INTEGER,
      units_liquidated INTEGER DEFAULT 0,
      orders_during_experiment INTEGER DEFAULT 0,
      realized_revenue_paise INTEGER DEFAULT 0,
      outcome_status TEXT, -- 'effective', 'inconclusive', 'no_lift', 'pending'
      control_skus TEXT DEFAULT '[]',
      treatment_baseline_velocity REAL DEFAULT 0.0,
      control_baseline_velocity REAL DEFAULT 0.0,
      treatment_current_velocity REAL DEFAULT 0.0,
      control_current_velocity REAL DEFAULT 0.0,
      treatment_lift REAL,
      control_lift REAL,
      matched_control_lift_estimate REAL,
      zero_baseline_treatment INTEGER DEFAULT 0,
      opportunity_reason TEXT DEFAULT 'INVENTORY_RISK_WITH_DEMAND',
      product_state TEXT DEFAULT 'UNDER_DISCOVERED',
      stage1_score REAL DEFAULT 0.0,
      stage2_llm_decision TEXT DEFAULT 'ACCEPT_FALLBACK',
      stage2_llm_reasoning TEXT,
      final_suitability_score REAL DEFAULT 0.0,
      decision_confidence REAL DEFAULT 0.5,
      decision_confidence_reason TEXT,
      probability_source TEXT DEFAULT 'cold_start_heuristic',
      is_empirical_probability INTEGER DEFAULT 0,
      early_killed INTEGER DEFAULT 0,
      early_kill_reason TEXT,
      merchant_decision TEXT DEFAULT 'PENDING',
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (sku) REFERENCES catalog(sku)
    );
    ''')

    # ── Safe Column Alterations for Existing Databases ───────────────────
    for table_name, col_name, col_type in [
        ("catalog", "boosted", "INTEGER NOT NULL DEFAULT 0"),
        ("catalog", "image_url", "TEXT"),
        ("catalog", "description", "TEXT"),
        ("catalog", "tags", "TEXT"),
        ("catalog", "metadata", "TEXT"),
        ("catalog", "embedding", "TEXT"),
        ("catalog", "co_purchase_embedding", "TEXT"),  # Layer 2: item2vec co-purchase vectors
        ("intent_mandates", "channel", "TEXT NOT NULL DEFAULT 'web_chat'"),
        ("policy_config", "autonomy_threshold_paise", "INTEGER NOT NULL DEFAULT 500000"),
        ("policy_config", "growth_mode", "TEXT NOT NULL DEFAULT 'manual'"),
        ("policy_config", "recovery_idle_threshold_minutes", "INTEGER NOT NULL DEFAULT 120"),
        ("policy_config", "recovery_attribution_percent", "INTEGER NOT NULL DEFAULT 60"),
        ("policy_config", "max_active_promotions", "INTEGER NOT NULL DEFAULT 5"),
        ("payment_mandates", "recovery_action", "TEXT"),
        ("upsell_events", "action_id", "TEXT"),
        ("basket_pairs", "muted", "INTEGER NOT NULL DEFAULT 0"),
        ("basket_pairs", "retired", "INTEGER NOT NULL DEFAULT 0"),
        ("basket_pairs", "source", "TEXT NOT NULL DEFAULT 'ai_suggested'"),
        ("basket_pairs", "reasoning", "TEXT"),
        ("basket_pairs", "co_occurrence_count", "INTEGER DEFAULT 0"),
        ("basket_pairs", "confidence", "REAL"),
        ("promotion_experiments", "control_skus", "TEXT DEFAULT '[]'"),
        ("promotion_experiments", "treatment_baseline_velocity", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "control_baseline_velocity", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "treatment_current_velocity", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "control_current_velocity", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "treatment_lift", "REAL"),
        ("promotion_experiments", "control_lift", "REAL"),
        ("promotion_experiments", "matched_control_lift_estimate", "REAL"),
        ("promotion_experiments", "zero_baseline_treatment", "INTEGER DEFAULT 0"),
        ("promotion_experiments", "opportunity_reason", "TEXT DEFAULT 'INVENTORY_RISK_WITH_DEMAND'"),
        ("promotion_experiments", "product_state", "TEXT DEFAULT 'UNDER_DISCOVERED'"),
        ("promotion_experiments", "stage1_score", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "stage2_llm_decision", "TEXT DEFAULT 'ACCEPT_FALLBACK'"),
        ("promotion_experiments", "stage2_llm_reasoning", "TEXT"),
        ("promotion_experiments", "final_suitability_score", "REAL DEFAULT 0.0"),
        ("promotion_experiments", "decision_confidence", "REAL DEFAULT 0.5"),
        ("promotion_experiments", "decision_confidence_reason", "TEXT"),
        ("promotion_experiments", "probability_source", "TEXT DEFAULT 'cold_start_heuristic'"),
        ("promotion_experiments", "is_empirical_probability", "INTEGER DEFAULT 0"),
        ("promotion_experiments", "early_killed", "INTEGER DEFAULT 0"),
        ("promotion_experiments", "early_kill_reason", "TEXT"),
        ("promotion_experiments", "merchant_decision", "TEXT DEFAULT 'PENDING'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except Exception:
            pass

    # Ensure existing verified paid upsells are populated in growth_outcomes
    try:
        cursor.execute("DELETE FROM growth_outcomes WHERE id LIKE 'go_legacy_%' OR id LIKE 'go_paid_%' OR id LIKE 'go_recov_%'")
        cursor.execute("""
            SELECT 
                p.id as pay_id,
                p.cart_id,
                p.amount_paise as paid_paise,
                c.total_paise as cart_total_paise,
                min(u.cart_total_before_paise) as base_cart_paise,
                p.created_at
            FROM payment_mandates p
            JOIN cart_mandates c ON p.cart_id = c.id
            JOIN upsell_events u ON p.cart_id = u.cart_id AND u.accepted = 1
            WHERE p.status = 'succeeded' 
              AND (p.recovery_action IS NULL OR p.recovery_action != 'recovery_link_sent')
            GROUP BY p.id, p.cart_id, p.amount_paise, c.total_paise, p.created_at
        """)
        for row in cursor.fetchall():
            incremental = max(0, row["paid_paise"] - row["base_cart_paise"])
            cursor.execute("""
                INSERT OR REPLACE INTO growth_outcomes (id, action_id, outcome_type, before_paise, after_paise, incremental_paise, revenue_type, created_at)
                VALUES (?, ?, 'paid', ?, ?, ?, 'cross_sell', ?)
            """, (f"go_paid_{row['pay_id']}", None, row["base_cart_paise"], row["paid_paise"], incremental, row["created_at"]))

        # Also sync settled recovery orders with 60% attribution factor on idle carts
        cursor.execute("SELECT recovery_attribution_percent, recovery_idle_threshold_minutes FROM policy_config WHERE id = 1")
        pol_row = cursor.fetchone()
        rec_factor = (pol_row["recovery_attribution_percent"] if pol_row and pol_row["recovery_attribution_percent"] is not None else 60) / 100.0
        rec_idle_min = pol_row["recovery_idle_threshold_minutes"] if pol_row and pol_row["recovery_idle_threshold_minutes"] is not None else 120

        cursor.execute("""
            SELECT p.id as pay_id, p.amount_paise, p.created_at, p.updated_at, c.created_at as cart_created_at
            FROM payment_mandates p
            JOIN cart_mandates c ON p.cart_id = c.id
            WHERE p.status = 'succeeded' AND p.recovery_action = 'recovery_link_sent'
        """)
        for rrow in cursor.fetchall():
            # Check idle eligibility
            try:
                t_cart = datetime.fromisoformat(rrow["cart_created_at"].replace("Z", "+00:00"))
                t_rec = datetime.fromisoformat(rrow["created_at"].replace("Z", "+00:00"))
                idle_minutes = (t_rec - t_cart).total_seconds() / 60.0
            except Exception:
                idle_minutes = 999.0

            if idle_minutes >= rec_idle_min:
                recov_incremental = int(round(rrow["amount_paise"] * rec_factor))
                cursor.execute("""
                    INSERT OR REPLACE INTO growth_outcomes (id, action_id, outcome_type, before_paise, after_paise, incremental_paise, revenue_type, created_at)
                    VALUES (?, ?, 'paid', 0, ?, ?, 'recovery', ?)
                """, (f"go_recov_{rrow['pay_id']}", None, rrow["amount_paise"], recov_incremental, rrow["updated_at"]))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Error syncing verified paid growth outcomes: {e}")

    # Migrate legacy ai_suggested rows to retired = 1 (Retire per-SKU priors)
    try:
        cursor.execute("UPDATE basket_pairs SET retired = 1 WHERE source = 'ai_suggested' AND (retired IS NULL OR retired = 0)")
        conn.commit()
    except Exception as e:
        print(f"⚠️ Error retiring legacy basket pairs: {e}")

    # Ensure basket_pairs has nullable lift/support for Hybrid Growth Engine
    cursor.execute("PRAGMA table_info(basket_pairs)")
    bp_cols = {row["name"]: row for row in cursor.fetchall()}
    if bp_cols.get("lift") and bp_cols["lift"]["notnull"] == 1:
        cursor.execute("DROP TABLE basket_pairs")
        cursor.execute("""
        CREATE TABLE basket_pairs (
          sku_a TEXT NOT NULL,
          sku_b TEXT NOT NULL,
          lift REAL,
          support REAL,
          confidence REAL,
          source TEXT NOT NULL DEFAULT 'ai_suggested',
          reasoning TEXT,
          co_occurrence_count INTEGER DEFAULT 0,
          computed_at TEXT NOT NULL,
          muted INTEGER NOT NULL DEFAULT 0,
          retired INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (sku_a, sku_b)
        )
        """)
        conn.commit()

    # ── Seed Policy Config ───────────────────────────────────────────────
    all_allowed = [
        "beauty", "fragrances", "furniture", "groceries", "home-decoration",
        "kitchen-accessories", "laptops", "mens-shirts", "mens-shoes", "mens-watches",
        "mobile-accessories", "motorcycle", "skin-care", "smartphones", "sports-accessories",
        "sunglasses", "tablets", "tops", "vehicle", "womens-bags", "womens-dresses",
        "womens-jewellery", "womens-shoes", "womens-watches", "grocery", "fashion",
        "electronics", "kitchenware", "home"
    ]
    cursor.execute("SELECT COUNT(*) FROM policy_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO policy_config (id, spend_cap_paise, allowed_categories, autonomy_threshold_paise) VALUES (?, ?, ?, ?)",
            (1, 1000000, json.dumps(all_allowed), 500000)
        )
    else:
        cursor.execute("SELECT autonomy_threshold_paise FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        if row and (row["autonomy_threshold_paise"] is None or row["autonomy_threshold_paise"] == 0):
            cursor.execute("UPDATE policy_config SET autonomy_threshold_paise = 500000 WHERE id = 1")
            conn.commit()



    # ── Seed Catalog ─────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM catalog")
    if cursor.fetchone()[0] == 0:
        seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed_catalog.json")
        if os.path.exists(seed_path):
            with open(seed_path, "r") as f:
                catalog = json.load(f)
                for item in catalog:
                    cursor.execute(
                        "INSERT INTO catalog (sku, name, price_paise, stock, category, merchant, boosted) VALUES (?, ?, ?, ?, ?, ?, 0)",
                        (item["sku"], item["name"], item["price_paise"], item["stock"],
                         item["category"], item.get("merchant", "DefaultMerchant"))
                    )

    # ── Seed Boosted Items ───────────────────────────────────────────────
    boosted_skus = [
        "BOO-GRO-0377",   # Butter Classic 375 — grocery, ₹68
        "SNE-GRO-0290",   # Milk Plus 473       — grocery, ₹90
        "GOU-GRO-0838",   # Cheese Pro 497      — grocery, ₹47
        "BOO-GRO-0364",   # Eggs Pro 250        — grocery, ₹37
        "PET-KIT-0440",   # Pan Pro 856         — kitchenware, ₹131
        "OFF-KIT-0136",   # Spatula Premium 613 — kitchenware, ₹134
        "TOY-KIT-0640",   # Kettle Ultra 796    — kitchenware, ₹142
        "FAS-KIT-0226",   # Blender Premium 986 — kitchenware, ₹183
        "GOU-ELE-0831",   # Keyboard Ultra 766  — electronics, ₹538
        "AUT-ELE-0579",   # Mouse Vintage 495   — electronics, ₹582
        "FIT-ELE-0711",   # Headphones Vintage  — electronics, ₹636
        "HOM-FAS-0181",   # Belt Essential 615  — fashion, ₹224
    ]
    for sku in boosted_skus:
        cursor.execute("UPDATE catalog SET boosted = 1 WHERE sku = ?", (sku,))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded.")
