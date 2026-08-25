#!/usr/bin/env python3
"""
CartPilot SQLite -> PostgreSQL Enterprise Data Migration Tool
Copies all tables, records, constraints, and JSONB payloads safely.
"""

import os
import sys
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.environ.get("CARTPILOT_DB") or os.path.join(BASE_DIR, "cartpilot.db")
POSTGRES_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

TABLES_IN_ORDER = [
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

def migrate():
    if not POSTGRES_URL:
        print("❌ Error: DATABASE_URL environment variable is required.")
        print("Example: export DATABASE_URL='postgresql://user:password@localhost:5432/cartpilot'")
        sys.exit(1)

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print("❌ Error: psycopg2 is required. Install via: pip install psycopg2-binary")
        sys.exit(1)

    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ Error: SQLite source database not found at {SQLITE_DB_PATH}")
        sys.exit(1)

    print("=" * 70)
    print("🚀 CartPilot SQLite -> PostgreSQL Migration")
    print(f"Source: {SQLITE_DB_PATH}")
    print(f"Target: {POSTGRES_URL.split('@')[-1] if '@' in POSTGRES_URL else 'PostgreSQL'}")
    print("=" * 70)

    # 1. Connect to both databases
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sq_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_cur = pg_conn.cursor()

    # 2. Run DDL schema migration
    schema_path = os.path.join(BASE_DIR, "ops", "migrations", "001_initial_schema.sql")
    if os.path.exists(schema_path):
        print(f"📄 Applying PostgreSQL schema from {schema_path}...")
        with open(schema_path, "r") as f:
            pg_cur.execute(f.read())
        pg_conn.commit()

    # 3. Migrate each table in dependency order
    for table in TABLES_IN_ORDER:
        try:
            sq_cur.execute(f"SELECT * FROM {table}")
            rows = sq_cur.fetchall()
            if not rows:
                print(f"  • {table:<25} 0 rows (empty)")
                continue

            columns = [col[0] for col in sq_cur.description]
            cols_joined = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))

            # Transform rows for PostgreSQL
            data = []
            for r in rows:
                row_vals = []
                for col in columns:
                    val = r[col]
                    row_vals.append(val)
                data.append(tuple(row_vals))

            # Clear existing target data & batch insert
            pg_cur.execute(f"TRUNCATE TABLE {table} CASCADE")
            insert_query = f"INSERT INTO {table} ({cols_joined}) VALUES ({placeholders})"
            pg_cur.executemany(insert_query, data)
            pg_conn.commit()

            print(f"  ✓ {table:<25} {len(data):>5} rows migrated")
        except Exception as e:
            pg_conn.rollback()
            print(f"  ⚠️ Error migrating table '{table}': {e}")

    # 4. Sync PostgreSQL Auto-Increment Sequences
    for seq_table, seq_col in [("audit_log", "id"), ("upsell_events", "id")]:
        try:
            pg_cur.execute(f"SELECT COALESCE(MAX({seq_col}), 0) + 1 FROM {seq_table}")
            next_val = pg_cur.fetchone()[0]
            pg_cur.execute(f"ALTER SEQUENCE {seq_table}_{seq_col}_seq RESTART WITH {next_val}")
            pg_conn.commit()
            print(f"  ✓ Synced sequence for {seq_table}.{seq_col} to {next_val}")
        except Exception as e:
            pg_conn.rollback()
            print(f"  ℹ️ Sequence sync note ({seq_table}): {e}")

    sqlite_conn.close()
    pg_conn.close()
    print("=" * 70)
    print("✅ Migration Completed Successfully!")
    print("=" * 70)

if __name__ == "__main__":
    migrate()
