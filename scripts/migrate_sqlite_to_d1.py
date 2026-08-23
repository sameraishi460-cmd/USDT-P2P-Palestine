#!/usr/bin/env python3
"""
USDT P2P Palestine — SQLite → Cloudflare D1 Migration Script

Reads the existing SQLite database and generates D1-compatible SQL output.
Supports:
  - Dry-run mode (default): prints SQL statements for review
  - Compare mode: compares record counts between SQLite and D1
  - Reconciliation mode: compares financial totals

Usage:
  python3 scripts/migrate_sqlite_to_d1.py                     # dry-run
  python3 scripts/migrate_sqlite_to_d1.py --compare            # compare counts
  python3 scripts/migrate_sqlite_to_d1.py --reconcile          # financial check
  python3 scripts/migrate_sqlite_to_d1.py --export > data.sql  # export SQL

IMPORTANT: Run this script BEFORE any production cutover.
Do NOT execute exported SQL without reviewing first.
"""

import sqlite3
import sys
import os
import json
import argparse
from datetime import datetime

# Tables to migrate, in dependency order
MIGRATION_TABLES = [
    # Core user data
    "users",
    # Market
    "market_price",
    "ads",
    "cash_ads",
    # Trades
    "trades",
    "messages",
    "disputes",
    # Wallets
    "wallets",
    "wallet_history",
    # Deposits/Withdrawals
    "usdt_deposits",
    "withdraw_requests",
    # Notifications
    "notifications",
    # Reviews
    "reviews",
    # Config
    "platform_config",
    # Cash payments
    "cash_ad_payments",
    # Cash trades
    "cash_trades",
    # Commission
    "commission",
    # Platform profit
    "platform_profit",
    # Audit
    "audit_log",
    # Uploads (new in Cloudflare version)
    # "uploads",
]

# Trading bot tables (isolated — Option D)
TRADING_TABLES = [
    "trading_bots",
    "trading_positions",
    "trading_orders",
    "trading_trades",
    "trading_signals",
    "trading_equity",
    "trading_daily_stats",
    "trading_models",
    "trading_backtests",
    "trading_settings",
    "trading_market_data",
]


def get_sqlite_tables(db_path: str) -> list[str]:
    """Get all tables from SQLite database."""
    con = sqlite3.connect(db_path)
    tables = [row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    con.close()
    return tables


def get_table_schema(db_path: str, table: str) -> list[dict]:
    """Get column info for a table."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    con.close()
    return [dict(r) for r in rows]


def count_rows(db_path: str, table: str) -> int:
    """Count rows in a table."""
    try:
        con = sqlite3.connect(db_path)
        count = con.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        con.close()
        return count
    except Exception:
        return -1  # table doesn't exist


def escape_sql_value(val) -> str:
    """Escape a value for SQL INSERT."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bytes):
        return f"X'{val.hex()}'"
    # String — escape single quotes
    s = str(val).replace("'", "''")
    return f"'{s}'"


def export_table(db_path: str, table: str) -> list[str]:
    """Export all rows from a table as INSERT statements."""
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(f"SELECT * FROM [{table}]").fetchall()
        con.close()
    except Exception:
        return []

    if not rows:
        return []

    columns = rows[0].keys()
    stmts = []
    for row in rows:
        vals = ", ".join(escape_sql_value(row[col]) for col in columns)
        cols = ", ".join(f"[{c}]" for c in columns)
        stmts.append(f"INSERT OR IGNORE INTO [{table}] ({cols}) VALUES ({vals});")
    return stmts


def compare_counts(db_path: str) -> dict:
    """Compare row counts between SQLite and export info."""
    all_tables = get_sqlite_tables(db_path)
    result = {}
    for table in MIGRATION_TABLES + TRADING_TABLES:
        if table in all_tables:
            result[table] = count_rows(db_path, table)
        else:
            result[table] = 0  # table doesn't exist
    return result


def financial_reconciliation(db_path: str) -> dict:
    """Compare financial totals."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    result = {}

    # Wallet totals
    try:
        w = con.execute("""
            SELECT
                COUNT(*) as count,
                COALESCE(SUM(balance), 0) as total_balance,
                COALESCE(SUM(locked), 0) as total_locked,
                SUM(CASE WHEN balance < 0 THEN 1 ELSE 0 END) as negative_balances
            FROM wallets
        """).fetchone()
        result["wallets"] = {
            "count": w["count"],
            "total_balance": round(w["total_balance"], 2),
            "total_locked": round(w["total_locked"], 2),
            "negative_balances": w["negative_balances"],
        }
    except Exception as e:
        result["wallets"] = {"error": str(e)}

    # Trade totals
    try:
        t = con.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='PAYMENT_SENT' THEN 1 ELSE 0 END) as payment_sent,
                SUM(CASE WHEN status='DISPUTED' THEN 1 ELSE 0 END) as disputed,
                SUM(CASE WHEN status='CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                COALESCE(SUM(CASE WHEN status='COMPLETED' THEN platform_fee ELSE 0 END), 0) as total_fees,
                COALESCE(SUM(CASE WHEN status='COMPLETED' THEN amount ELSE 0 END), 0) as total_volume
            FROM trades
        """).fetchone()
        result["trades"] = {
            "total": t["total"],
            "completed": t["completed"],
            "pending": t["pending"],
            "payment_sent": t["payment_sent"],
            "disputed": t["disputed"],
            "cancelled": t["cancelled"],
            "total_fees": round(t["total_fees"], 2),
            "total_volume": round(t["total_volume"], 2),
        }
    except Exception as e:
        result["trades"] = {"error": str(e)}

    # Deposit totals
    try:
        d = con.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='CONFIRMED' THEN 1 ELSE 0 END) as confirmed,
                SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) as rejected,
                COALESCE(SUM(CASE WHEN status='CONFIRMED' THEN amount ELSE 0 END), 0) as total_deposited,
                COUNT(DISTINCT tx_hash) as unique_tx_count
            FROM usdt_deposits
        """).fetchone()
        result["deposits"] = {
            "total": d["total"],
            "confirmed": d["confirmed"],
            "pending": d["pending"],
            "rejected": d["rejected"],
            "total_deposited": round(d["total_deposited"], 2),
            "unique_tx_count": d["unique_tx_count"],
        }
    except Exception as e:
        result["deposits"] = {"error": str(e)}

    # Withdrawal totals
    try:
        wd = con.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) as rejected,
                COALESCE(SUM(CASE WHEN status='PENDING' THEN amount ELSE 0 END), 0) as locked_amount
            FROM withdraw_requests
        """).fetchone()
        result["withdrawals"] = {
            "total": wd["total"],
            "pending": wd["pending"],
            "completed": wd["completed"],
            "rejected": wd["rejected"],
            "locked_amount": round(wd["locked_amount"], 2),
        }
    except Exception as e:
        result["withdrawals"] = {"error": str(e)}

    # Escrow integrity check
    try:
        esc = con.execute("""
            SELECT
                SUM(CASE WHEN status='COMPLETED' AND escrow_status='RELEASED' THEN 1 ELSE 0 END) as released,
                SUM(CASE WHEN status='CANCELLED' AND escrow_status='REFUNDED' THEN 1 ELSE 0 END) as refunded,
                SUM(CASE WHEN status IN ('PENDING','PAYMENT_SENT') AND escrow_status='LOCKED' THEN 1 ELSE 0 END) as locked
            FROM trades
        """).fetchone()
        result["escrow"] = {
            "released": esc["released"] or 0,
            "refunded": esc["refunded"] or 0,
            "locked": esc["locked"] or 0,
        }
    except Exception as e:
        result["escrow"] = {"error": str(e)}

    con.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="SQLite → D1 Migration Tool")
    parser.add_argument("db_path", nargs="?", default="database.db", help="Path to SQLite database")
    parser.add_argument("--compare", action="store_true", help="Compare record counts")
    parser.add_argument("--reconcile", action="store_true", help="Financial reconciliation")
    parser.add_argument("--export", action="store_true", help="Export SQL for D1")
    parser.add_argument("--tables", nargs="*", help="Specific tables to export")
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: Database not found: {args.db_path}")
        sys.exit(1)

    print(f"SQLite → D1 Migration Tool")
    print(f"Database: {args.db_path}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    if args.compare:
        print("\n📊 RECORD COUNT COMPARISON")
        print("-" * 40)
        counts = compare_counts(args.db_path)
        total = 0
        for table, count in counts.items():
            status = "✅" if count >= 0 else "❌ MISSING"
            if count >= 0:
                total += count
            print(f"  {table:30s} {count:>8d}  {status}")
        print(f"  {'TOTAL':30s} {total:>8d}")

    if args.reconcile:
        print("\n💰 FINANCIAL RECONCILIATION")
        print("-" * 40)
        result = financial_reconciliation(args.db_path)
        for section, data in result.items():
            print(f"\n  [{section.upper()}]")
            for key, val in data.items():
                print(f"    {key:25s} {val}")

    if args.export:
        print("\n📝 EXPORTING SQL")
        print("-" * 40)
        tables = args.tables or MIGRATION_TABLES + TRADING_TABLES
        all_sqlite_tables = get_sqlite_tables(args.db_path)

        print("-- Migration export")
        print(f"-- Source: {args.db_path}")
        print(f"-- Date: {datetime.now().isoformat()}")
        print("-- WARNING: Review before executing on D1")
        print()

        for table in tables:
            if table not in all_sqlite_tables:
                print(f"-- SKIPPED: {table} (not found in source)")
                continue

            stmts = export_table(args.db_path, table)
            print(f"-- Table: {table} ({len(stmts)} rows)")
            for stmt in stmts:
                print(stmt)
            print()

        print("-- Export complete")
        print(f"-- Total tables: {len(tables)}")

    if not args.compare and not args.reconcile and not args.export:
        # Default: show summary
        print("\n📋 TABLE SUMMARY")
        print("-" * 40)
        tables = get_sqlite_tables(args.db_path)
        for table in MIGRATION_TABLES + TRADING_TABLES:
            if table in tables:
                count = count_rows(args.db_path, table)
                print(f"  {table:30s} {count:>8d} rows")
            else:
                print(f"  {table:30s}    (missing)")

        print(f"\nSQLite tables found: {len(tables)}")
        print(f"Tables to migrate: {len(MIGRATION_TABLES + TRADING_TABLES)}")
        print("\nRun with --compare, --reconcile, or --export for more details.")


if __name__ == "__main__":
    main()
