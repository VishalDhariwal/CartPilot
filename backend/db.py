import sqlite3
import json
import os

DB_PATH = "cartpilot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Create Tables
    cursor.executescript('''
    CREATE TABLE IF NOT EXISTS catalog (
      sku TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      price_paise INTEGER NOT NULL,
      stock INTEGER NOT NULL,
      category TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS policy_config (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      spend_cap_paise INTEGER NOT NULL,
      allowed_categories TEXT NOT NULL
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
    ''')

    # Seed Policy Config
    cursor.execute("SELECT COUNT(*) FROM policy_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO policy_config (id, spend_cap_paise, allowed_categories) VALUES (?, ?, ?)",
            (1, 150000, json.dumps(["grocery", "kitchenware"]))
        )

    # Seed Catalog
    cursor.execute("SELECT COUNT(*) FROM catalog")
    if cursor.fetchone()[0] == 0:
        seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed_catalog.json")
        if os.path.exists(seed_path):
            with open(seed_path, "r") as f:
                catalog = json.load(f)
                for item in catalog:
                    cursor.execute(
                        "INSERT INTO catalog (sku, name, price_paise, stock, category) VALUES (?, ?, ?, ?, ?)",
                        (item["sku"], item["name"], item["price_paise"], item["stock"], item["category"])
                    )
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded.")
