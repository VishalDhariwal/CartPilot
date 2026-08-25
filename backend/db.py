import os
import json
import sqlite3
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("CARTPILOT_DB") or os.path.join(BASE_DIR, "cartpilot.db")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or os.environ.get("AZURE_POSTGRESQL_CONNECTIONSTRING")

# Optional psycopg2 import for PostgreSQL support
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class PostgresCursorWrapper:
    """
    Transparent cursor wrapper for PostgreSQL that provides SQLite-compatible
    parameter translation (? -> %s) and dictionary row access.
    """
    def __init__(self, raw_cursor, conn):
        self._cursor = raw_cursor
        self._conn = conn

    def _translate_query(self, query: str) -> str:
        # Translate '?' placeholders to '%s'
        # Also translate 'INSERT OR REPLACE INTO table' to PostgreSQL UPSERT if standard
        q = query
        if "?" in q:
            # Replace ? with %s safely
            q = re.sub(r'\?', '%s', q)
        if "INSERT OR REPLACE INTO" in q:
            # Replace with standard INSERT (tables have ON CONFLICT or fallback)
            q = q.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        return q

    def execute(self, query, params=None):
        translated = self._translate_query(query)
        if params is not None:
            if isinstance(params, (list, tuple)):
                # Convert list to tuple for psycopg2
                return self._cursor.execute(translated, tuple(params))
            return self._cursor.execute(translated, params)
        return self._cursor.execute(translated)

    def executemany(self, query, params_list):
        translated = self._translate_query(query)
        return self._cursor.executemany(translated, params_list)

    def executescript(self, script: str):
        # Execute semicolon separated statements
        for stmt in script.strip().split(";"):
            cleaned = stmt.strip()
            if cleaned:
                self._cursor.execute(cleaned)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    def close(self):
        return self._cursor.close()


class PostgresConnectionWrapper:
    """
    Transparent connection wrapper for PostgreSQL ensuring .commit(), .rollback(),
    and .cursor() match the sqlite3.Connection interface.
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor(cursor_factory=RealDictCursor), self._conn)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur


def is_postgres() -> bool:
    return bool(DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")))


def get_db():
    """
    Returns a unified database connection:
    - PostgreSQL connection when DATABASE_URL is configured.
    - SQLite connection with WAL mode when running locally.
    """
    if is_postgres():
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 is required for PostgreSQL. Run: pip install psycopg2-binary")
        raw_conn = psycopg2.connect(DATABASE_URL)
        return PostgresConnectionWrapper(raw_conn)

    # SQLite fallback with WAL and timeout
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Initializes database schema and baseline catalog / policy seeds.
    Automatically applies PostgreSQL DDL or SQLite DDL depending on the active engine.
    """
    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():
        migration_file = os.path.join(BASE_DIR, "ops", "migrations", "001_initial_schema.sql")
        if os.path.exists(migration_file):
            with open(migration_file, "r") as f:
                cursor.executescript(f.read())
            conn.commit()
    else:
        # SQLite Schema Initialization
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
          reversible INTEGER NOT NULL DEFAULT 1,
          order_status TEXT NOT NULL DEFAULT 'CREATED',
          cancellation_status TEXT NOT NULL DEFAULT 'NONE',
          fulfillment_status TEXT NOT NULL DEFAULT 'UNFULFILLED',
          return_status TEXT NOT NULL DEFAULT 'NONE',
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
          refund_status TEXT NOT NULL DEFAULT 'NONE',
          refund_amount_paise INTEGER NOT NULL DEFAULT 0,
          refunded_amount_paise INTEGER NOT NULL DEFAULT 0,
          razorpay_refund_id TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS refunds (
          id TEXT PRIMARY KEY,
          payment_id TEXT NOT NULL REFERENCES payment_mandates(id),
          cart_id TEXT NOT NULL REFERENCES cart_mandates(id),
          requested_amount_paise INTEGER NOT NULL,
          processed_amount_paise INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'REFUND_REQUESTED',
          razorpay_refund_id TEXT,
          reason TEXT,
          created_at TEXT NOT NULL,
          processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ref_type TEXT NOT NULL,
          ref_id TEXT NOT NULL,
          event TEXT NOT NULL,
          detail TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS historical_orders (
          order_id TEXT PRIMARY KEY,
          items TEXT NOT NULL,
          is_synthetic INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );

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

        CREATE TABLE IF NOT EXISTS chat_sessions (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          session_data TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS upsell_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cart_id TEXT NOT NULL,
          suggested_sku TEXT NOT NULL,
          accepted INTEGER NOT NULL,
          cart_total_before_paise INTEGER NOT NULL,
          cart_total_after_paise INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS category_compatibility (
          category_a TEXT NOT NULL,
          category_b TEXT NOT NULL,
          reasoning TEXT NOT NULL,
          editable INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          PRIMARY KEY (category_a, category_b)
        );

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

        CREATE TABLE IF NOT EXISTS promotion_experiments (
          id TEXT PRIMARY KEY,
          sku TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'ACTIVE',
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
          outcome_status TEXT,
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
        conn.commit()

    # ── Safe Column Alterations for Existing Databases ───────────────────
    for table_name, col_name, col_type in [
        ("catalog", "boosted", "INTEGER NOT NULL DEFAULT 0"),
        ("catalog", "image_url", "TEXT"),
        ("catalog", "description", "TEXT"),
        ("catalog", "tags", "TEXT"),
        ("catalog", "metadata", "TEXT"),
        ("catalog", "embedding", "TEXT"),
        ("catalog", "co_purchase_embedding", "TEXT"),
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
        ("cart_mandates", "order_status", "TEXT NOT NULL DEFAULT 'CREATED'"),
        ("cart_mandates", "cancellation_status", "TEXT NOT NULL DEFAULT 'NONE'"),
        ("cart_mandates", "fulfillment_status", "TEXT NOT NULL DEFAULT 'UNFULFILLED'"),
        ("cart_mandates", "return_status", "TEXT NOT NULL DEFAULT 'NONE'"),
        ("payment_mandates", "refund_status", "TEXT NOT NULL DEFAULT 'NONE'"),
        ("payment_mandates", "refund_amount_paise", "INTEGER NOT NULL DEFAULT 0"),
        ("payment_mandates", "refunded_amount_paise", "INTEGER NOT NULL DEFAULT 0"),
        ("payment_mandates", "razorpay_refund_id", "TEXT"),
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
    res = cursor.fetchone()
    count = list(res.values())[0] if isinstance(res, dict) else (res[0] if res else 0)
    if count == 0:
        cursor.execute(
            "INSERT INTO policy_config (id, spend_cap_paise, allowed_categories, autonomy_threshold_paise) VALUES (?, ?, ?, ?)",
            (1, 1000000, json.dumps(all_allowed), 500000)
        )
        conn.commit()

    # ── Seed Catalog ─────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM catalog")
    res = cursor.fetchone()
    count = list(res.values())[0] if isinstance(res, dict) else (res[0] if res else 0)
    if count == 0:
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
            conn.commit()

    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized and ready.")
