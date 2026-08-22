import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "cartpilot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
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
      boosted INTEGER NOT NULL DEFAULT 0
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

    -- Pairing table: deterministic ground truth for cross-sell recommendations.
    -- sku_a is in the cart; sku_b is the complementary item to suggest.
    CREATE TABLE IF NOT EXISTS catalog_pairings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sku_a TEXT NOT NULL,
      sku_b TEXT NOT NULL,
      reason_template TEXT NOT NULL,
      boosted INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );

    -- Measurement table: every upsell/cross-sell offer, outcome, and AOV impact.
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

    # ── Add boosted column to existing catalog rows if it doesn't exist ──
    try:
        cursor.execute("ALTER TABLE catalog ADD COLUMN boosted INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # column already exists

    # ── Seed Policy Config ───────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM policy_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO policy_config (id, spend_cap_paise, allowed_categories) VALUES (?, ?, ?)",
            (1, 500000, json.dumps(["grocery", "kitchenware", "electronics", "fashion", "home"]))
        )
    else:
        # Upgrade spend cap if it's still at the old ₹1500 default
        cursor.execute("SELECT spend_cap_paise FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        if row and row[0] <= 150000:
            cursor.execute(
                "UPDATE policy_config SET spend_cap_paise = ? WHERE id = 1",
                (500000,)
            )

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
    # Mark items the merchant wants to move (cross-sell targets).
    # These will be preferred by the growth agent when multiple pairings match.
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

    # ── Seed Catalog Pairings ────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM catalog_pairings")
    if cursor.fetchone()[0] == 0:
        now = datetime.utcnow().isoformat() + "Z"
        # Format: (sku_a, sku_b, reason_template, boosted)
        pairings = [
            # Grocery → Grocery pairings
            ("BOO-GRO-0359", "BOO-GRO-0377", "Butter is the perfect companion for bread — great for toast or sandwiches", 1),
            ("BOO-GRO-0359", "SNE-GRO-0290", "Milk pairs naturally with bread for a quick, wholesome breakfast", 1),
            ("SNE-GRO-0293", "BOO-GRO-0377", "Butter elevates plain rice into a delicious side dish", 1),
            ("GAR-GRO-0921", "BOO-GRO-0377", "Wheat flour and butter are a classic baking combination", 0),
            ("SNE-GRO-0254", "BOO-GRO-0377", "Add butter to complement your wheat for richer flatbreads", 0),
            ("BOO-GRO-0364", "BOO-GRO-0359", "Eggs and bread make a quick, protein-packed breakfast", 1),
            ("GOU-GRO-0838", "BOO-GRO-0364", "Eggs pair perfectly with cheese for omelettes or sandwiches", 1),
            ("SNE-GRO-0282", "MUS-GRO-0692", "Bananas and milk blend into a perfect nutritious smoothie", 0),

            # Kitchenware → Kitchenware pairings
            ("PET-KIT-0440", "OFF-KIT-0136",  "A spatula is essential for working with your pan — great combo", 1),
            ("FAS-KIT-0226", "TOY-KIT-0640",  "A kettle alongside your blender covers both hot and cold drink prep", 1),
            ("GAM-KIT-0070", "TOY-KIT-0640",  "Pair your toaster with a kettle for a complete breakfast station", 0),
            ("JEW-KIT-0976", "PET-KIT-0440",  "An oven and a pan give you full stovetop-plus-oven cooking capability", 0),

            # Electronics → Electronics pairings
            ("AUT-ELE-0582", "GOU-ELE-0831",  "A keyboard is essential for getting the most out of your tablet", 1),
            ("AUT-ELE-0582", "AUT-ELE-0579",  "A mouse makes tablet navigation far faster and more precise", 1),
            ("GOU-ELE-0819", "GOU-ELE-0831",  "Add a keyboard to your monitor setup for a complete workstation", 1),
            ("GOU-ELE-0819", "AUT-ELE-0579",  "A mouse completes your monitor setup for seamless desktop use", 0),
            ("GOU-ELE-0802", "FIT-ELE-0711",  "Headphones pair beautifully with a smartwatch for music on the go", 1),
            ("GOU-ELE-0806", "GOU-ELE-0831",  "Keep your keyboard charged with this compatible charger nearby", 0),

            # Fashion → Fashion pairings
            ("TEC-FAS-0050", "HOM-FAS-0181",  "A belt completes the look with your jacket — great styling combo", 1),
            ("GAR-FAS-0920", "HOM-FAS-0181",  "Add a belt to your jeans for a polished, put-together outfit", 1),
            ("TEC-FAS-0024", "TEC-FAS-0031",  "Sunglasses are the perfect finishing touch for your jacket outfit", 0),
        ]
        for sku_a, sku_b, reason, boosted in pairings:
            cursor.execute(
                "INSERT INTO catalog_pairings (sku_a, sku_b, reason_template, boosted, created_at) VALUES (?, ?, ?, ?, ?)",
                (sku_a, sku_b, reason, boosted, now)
            )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded.")
