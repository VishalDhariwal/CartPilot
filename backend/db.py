import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "cartpilot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
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

    -- Market Basket Analysis pairs: derived from historical_orders lift/support calculations
    CREATE TABLE IF NOT EXISTS basket_pairs (
      sku_a TEXT NOT NULL,
      sku_b TEXT NOT NULL,
      lift REAL NOT NULL,
      support REAL NOT NULL,
      computed_at TEXT NOT NULL,
      muted INTEGER NOT NULL DEFAULT 0,
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
    ''')

    # ── Safe Column Alterations for Existing Databases ───────────────────
    for table_name, col_name, col_type in [
        ("catalog", "boosted", "INTEGER NOT NULL DEFAULT 0"),
        ("catalog", "image_url", "TEXT"),
        ("catalog", "description", "TEXT"),
        ("catalog", "tags", "TEXT"),
        ("catalog", "metadata", "TEXT"),
        ("catalog", "embedding", "TEXT"),
        ("policy_config", "autonomy_threshold_paise", "INTEGER NOT NULL DEFAULT 500000"),
        ("basket_pairs", "muted", "INTEGER NOT NULL DEFAULT 0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except Exception:
            pass

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
